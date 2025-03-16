import argparse
import os
import zipfile
import numpy as np
from utils import load_config, setup_logging
from database import Database
import cv2
from typing import List, Optional
import logging
import faiss

# 全局状态，用于服务模式
class ExtractorState:
    def __init__(self):
        self.config = None
        self.logger = None
        self.db = None
        self.faiss_index = None
        self.initialized = False

    def initialize(self, config_path: str = '.'):
        """初始化数据库和 FAISS 索引"""
        if not self.initialized:
            self.config = load_config(config_path=config_path)
            self.logger = setup_logging(self.config, self.config['logging']['get_prefix'])
            self.db = Database(self.config, self.logger)
            self.faiss_index = self.db.build_faiss_index()
            if self.faiss_index:
                self.logger.info(f"FAISS index loaded with {self.faiss_index.ntotal} embeddings")
            else:
                self.logger.warning("No FAISS index available")
            self.initialized = True

# 全局状态实例
extractor_state = ExtractorState()

def extract_photos_core(
    bib: Optional[str] = None,
    faces: Optional[List] = None,
    face_match_confidence: Optional[float] = None,
    face_detect_confidence: Optional[float] = None,
    zip_file: Optional[str] = None,
    sub_bib: bool = False,
    bib_confidence: Optional[float] = None,
    logger: Optional[logging.Logger] = None,
    db: Optional[Database] = None,
    faiss_index: Optional[faiss.Index] = None
) -> List[str]:
    """
    核心提取照片逻辑，支持 bib 和人脸搜索，返回匹配的照片路径列表。

    Args:
        bib: Bib 号码
        faces: 人脸图片路径或 cv2 图像列表
        face_match_confidence: 人脸匹配置信度阈值
        face_detect_confidence: 人脸检测置信度阈值
        zip_file: 输出 zip 文件路径（可选）
        sub_bib: 是否搜索子 bib
        bib_confidence: Bib 搜索置信度阈值
        logger: 日志记录器（可选）
        db: 数据库实例（可选）
        faiss_index: FAISS 索引（可选）

    Returns:
        List[str]: 匹配的照片路径列表
    """
    config = extractor_state.config if extractor_state.initialized else load_config()
    if logger is None:
        logger = extractor_state.logger if extractor_state.initialized else setup_logging(config, config['logging']['get_prefix'])
    if db is None:
        db = extractor_state.db if extractor_state.initialized else Database(config, logger)
    if faiss_index is None and not extractor_state.initialized:
        faiss_index = db.build_faiss_index()

    face_conf = face_match_confidence or config['search']['face_match_confidence']
    detect_conf = face_detect_confidence or config['search']['face_detect_confidence']
    bib_conf = bib_confidence or config['search']['bib_confidence']

    if not (bib or faces):
        logger.error("Must provide either bib or face images")
        return []

    photo_paths = set()

    # Bib 搜索
    if bib:
        paths = db.search_bib(bib, sub_bib, bib_conf)
        photo_paths.update(paths)
        logger.debug(f"Bib {bib}:")
        for path in paths:
            logger.debug(f"  {path}")

    # 人脸搜索
    if faces:
        if faiss_index is None:
            logger.warning("No face data in database, skipping face search")
        else:
            logger.debug(f"FAISS index dimension: {faiss_index.d}")
            logger.debug(f"FAISS index contains {faiss_index.ntotal} embeddings")

            expected_dim = config.get('deepface', {}).get('embedding_dim', 512)
            c = db.conn.cursor()
            for face_path_or_img in faces:
                try:
                    # 支持传入文件路径或 cv2 图像
                    if isinstance(face_path_or_img, str):
                        logger.debug(f"Processing face image: {face_path_or_img}")
                        img = cv2.imread(face_path_or_img)
                    else:
                        logger.debug("Processing face image from array")
                        img = face_path_or_img

                    if img is None:
                        logger.error(f"Failed to load face image: {face_path_or_img}")
                        continue

                    height, width = img.shape[:2]
                    if width > 800:
                        scale = 800 / width
                        new_width = 800
                        new_height = int(height * scale)
                        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
                        logger.debug(f"Resized image from {width}x{height} to {new_width}x{new_height}")

                    from deepface import DeepFace
                    representations = DeepFace.represent(
                        img_path=img,
                        model_name=config['deepface']['model'],
                        detector_backend=config['deepface']['detector'],
                        #detector_backend='yunet',
                        #detector_backend='retinaface',
                        align=config['deepface']['alignment']
                    )
                    if not representations:
                        logger.warning(f"No faces detected in image")
                        continue

                    embedding = None
                    for rep in representations:
                        confidence = rep.get('face_confidence', 0.0)
                        if confidence >= detect_conf:
                            embedding = np.array(rep["embedding"], dtype=np.float32).flatten()
                            break

                    if embedding is None:
                        logger.warning(f"No faces with confidence >= {detect_conf} in image")
                        continue

                    if len(embedding) != expected_dim:
                        logger.error(f"Query embedding dimension mismatch: expected {expected_dim}, got {len(embedding)}")
                        continue

                    logger.debug(f"Input embedding dimension: {embedding.shape}")

                    query_embedding = embedding.copy()
                    if config['search']['similarity_metric'] == 'cosine':
                        faiss.normalize_L2(query_embedding.reshape(1, -1))

                    D, I = faiss_index.search(query_embedding.reshape(1, -1), k=100)
                    logger.debug(f"FAISS search results:")
                    logger.debug(f"  Raw scores (D): {D[0][:10]}")
                    logger.debug(f"  Indices (I): {I[0][:10]}")

                    paths = set()
                    for i, score in zip(I[0], D[0]):
                        if config['search']['similarity_metric'] == 'cosine':
                            similarity = score
                        else:
                            similarity = 1 - (score / 2)
                        logger.debug(f"Match index {i}, raw score {score:.4f}, similarity {similarity:.4f}")
                        if similarity >= face_conf:
                            c.execute(
                                f"SELECT photo_path FROM {config['database']['photo_table']} p "
                                f"JOIN {config['database']['face_table']} f ON p.id = f.photo_id "
                                f"WHERE f.embedding = (SELECT embedding FROM {config['database']['face_table']} LIMIT 1 OFFSET {i})"
                            )
                            path = c.fetchone()[0]
                            paths.add(path)
                            logger.debug(f"Add path: {path}")
                    photo_paths.update(paths)
                    logger.info(f"Face search results:")
                    for path in paths:
                        logger.info(f"  {path}")
                except Exception as e:
                    logger.error(f"Error processing face image: {str(e)}")

    logger.info(f"Total unique photos: {len(photo_paths)}")

    # 如果指定了 zip 文件，则打包
    if zip_file:
        with zipfile.ZipFile(zip_file, 'w') as zipf:
            for path in photo_paths:
                full_path = os.path.join(config['photo_dir'], path)
                zipf.write(full_path, path)
        logger.info(f"Created zip file: {zip_file}")

    return list(photo_paths)

def extract(bib: str, images: List[np.ndarray], config_path: str ='config.yaml') -> List[np.ndarray]:
    """
    FastAPI 调用的提取函数，接收 bib 和图像数组，返回匹配的照片图像数组。
    首次调用时初始化全局状态，后续调用直接使用内存中的资源。

    Args:
        bib: Bib 号码
        images: cv2 格式的图像数组

    Returns:
        List[np.ndarray]: 匹配的照片图像列表
    """
    # 首次调用时初始化
    extractor_state.initialize(config_path=config_path)

    # 调用核心逻辑，使用全局状态
    return extract_photos_core(
        bib=bib,
        faces=images,
        logger=extractor_state.logger,
        db=extractor_state.db,
        faiss_index=extractor_state.faiss_index
    )

def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="Extract photos by bib or face images")
    parser.add_argument("--bib", help="Bib number to search")
    parser.add_argument("--faces", nargs='+', help="Face image paths")
    parser.add_argument("--face-match-confidence", type=float, help="Face match confidence threshold")
    parser.add_argument("--face-detect-confidence", type=float, help="Face detect confidence threshold")
    parser.add_argument("--zip-file", help="Output zip file name")
    parser.add_argument("--sub-bib", action="store_true", help="Search sub-bib")
    parser.add_argument("--bib-confidence", type=float, help="Bib confidence threshold")
    args = parser.parse_args()

    # 调用核心逻辑（命令行模式不使用全局状态）
    photo_paths = extract_photos_core(
        bib=args.bib,
        faces=args.faces,
        face_match_confidence=args.face_match_confidence,
        face_detect_confidence=args.face_detect_confidence,
        zip_file=args.zip_file,
        sub_bib=args.sub_bib,
        bib_confidence=args.bib_confidence
    )

    # 命令行输出路径
    photo_paths.sort()
    for p in photo_paths:
        print(p)

# 设置环境变量
os.environ["CUDA_VISIBLE_DEVICES"]=""
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # 抑制 TensorFlow 日志

if __name__ == "__main__":
    main()
