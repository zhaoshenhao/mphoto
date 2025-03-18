import argparse
import os
import zipfile
import numpy as np
import cv2
import logging
import faiss
import traceback
from typing import List, Optional
from config import config
from utils import setup_logging, get_event_dir
from database import Database
from config import DEFAULT_SEARCH_LIMIT

def prepare_image(face_path_or_img, logger):
    if isinstance(face_path_or_img, str):
        logger.debug(f"Processing face image: {face_path_or_img}")
        img = cv2.imread(face_path_or_img)
    else:
        logger.debug("Processing face image from array")
        img = face_path_or_img
    if img is None:
        return None
    height, width = img.shape[:2]
    if width > 800:
        scale = 800 / width
        new_width = 800
        new_height = int(height * scale)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
        logger.debug(f"Resized image from {width}x{height} to {new_width}x{new_height}")
    return img

def get_face_representation(img, logger, detect_conf, expected_dim):
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
        return None

    embedding = None
    for rep in representations:
        confidence = rep.get('face_confidence', 0.0)
        if confidence >= detect_conf:
            embedding = np.array(rep["embedding"])
            #embedding = np.array(rep["embedding"], dtype=np.float32).flatten()
            break

    if embedding is None:
        logger.warning(f"No faces with confidence >= {detect_conf} in image")
        return None

    if len(embedding) != expected_dim:
        logger.error(f"Query embedding dimension mismatch: expected {expected_dim}, got {len(embedding)}")
        return None

    logger.debug(f"Input embedding dimension: {embedding.shape}")
    return embedding

def zip_photos(zipfile, event_id, photo_paths):
    work_dir = get_event_dir(event_id, 'raw')
    with zipfile.ZipFile(zip_file, 'w') as zipf:
        for path in photo_paths:
            full_path = os.path.join(work_dir, path)
            zipf.write(full_path, path)
    logger.info(f"Created zip file: {zip_file}")

def extract_photos_core(
    logger: logging.Logger = None,
    db: Database = None,
    event_id: int = None,
    bib: Optional[str] = None,
    faces: Optional[List] = None,
    face_similarity: Optional[float] = None,
    face_detect_confidence: Optional[float] = None,
    sub_bib: bool = False,
    bib_confidence: Optional[float] = None
) -> List[str]:
    """
    核心提取照片逻辑，支持 bib 和人脸搜索，返回匹配的照片路径列表。

    Args:
        event_id: event ID
        bib: Bib number, optional
        faces: face image or cv2 image, optional
        face_similarity: face match minimal similarity, optional
        face_detect_confidence: face detect minial similarity, optional
        sub_bib: Sub string search, optional
        bib_confidence: Bib ocr minimal confidence, optional
        logger: logger instance
        db: db instance

    Returns:
        List[str]: Photo path list
    """
    face_conf = face_similarity or config['search']['face_similarity']
    detect_conf = face_detect_confidence or config['search']['face_detect_confidence']
    bib_conf = bib_confidence or config['search']['bib_confidence']

    if not (bib or faces):
        logger.error("Must provide either bib or face images")
        return []

    photo_paths = set()

    # Bib 搜索
    if bib:
        paths = db.search_bib_photo(event_id, bib, sub_bib, bib_conf)
        photo_paths.update(paths)
        logger.debug(f"Bib {bib}:")
        for path in paths:
            logger.debug(f"  {path}")

    # 人脸搜索
    if faces:
        expected_dim = config['deepface']['embedding_dim']
        c = db.conn.cursor()
        for face_path_or_img in faces:
            try:
                img = prepare_image(face_path_or_img, logger)
                if img is None:
                    logger.error(f"Failed to load face image: {face_path_or_img}")
                    continue

                embedding = get_face_representation(img, logger, detect_conf, expected_dim)

                if embedding is None:
                    continue

                logger.debug(f"Input embedding dimension: {embedding.shape}")

                paths = db.search_face_photo(event_id, embedding, detect_conf, face_conf)
                logger.debug(f"Face search return {len(paths)} rows")
                if (len(paths) == DEFAULT_SEARCH_LIMIT):
                    logger.debug(f"It reaches the search limit {DEFAULT_SEARCH_LIMIT}")
                
                p2 = set()
                for p in paths:
                    logger.info(f"  {p}")
                    p2.add(p)
                photo_paths.update(p2)
            except Exception as e:
                logger.error(f"Error processing face image: {str(e)}\n{traceback.format_exc()}")

    logger.info(f"Total unique photos: {len(photo_paths)}")
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
    parser.add_argument("-e", "--event-id", help="Bib number to search")
    parser.add_argument("-b", "--bib", help="Bib number to search")
    parser.add_argument("-f", "--faces", nargs='+', help="Face image paths")
    parser.add_argument("-fm", "--face-similarity", type=float, help="Face similarity threshold")
    parser.add_argument("-fd", "--face-detect-confidence", type=float, help="Face detect confidence threshold")
    parser.add_argument("-z", "--zip-file", help="Output zip file name")
    parser.add_argument("-l", "--like", action="store_true", help="Search bib like (substring)")
    parser.add_argument("-bd", "--bib-confidence", type=float, help="Bib confidence threshold")
    args = parser.parse_args()

    logger = setup_logging(config['logging']['get_prefix'])
    db = Database(logger)
    # 调用核心逻辑（命令行模式不使用全局状态）
    photo_paths = extract_photos_core(
        bib=args.bib,
        faces=args.faces,
        face_similarity=args.face_similarity,
        face_detect_confidence=args.face_detect_confidence,
        sub_bib=args.like,
        bib_confidence=args.bib_confidence,
        db=db,
        logger=logger,
        event_id=args.event_id,
    )

    # 命令行输出路径
    photo_paths.sort()
    for p in photo_paths:
        print(p)

    if args.zip_file:
        zip_photos(args.zipfile, event_id, photo_paths)
# 设置环境变量
os.environ["CUDA_VISIBLE_DEVICES"]=""
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # 抑制 TensorFlow 日志

if __name__ == "__main__":
    main()
