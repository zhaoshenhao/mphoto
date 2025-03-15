import argparse
import os
import zipfile
import numpy as np
from utils import load_config, setup_logging
from database import Database
import cv2

def extract_photos():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bib", help="Bib number to search")
    parser.add_argument("--faces", nargs='+', help="Face image paths")
    parser.add_argument("--face-match-confidence", type=float)
    parser.add_argument("--face-detect-confidence", type=float)
    parser.add_argument("--zip-file", help="Output zip file name")
    parser.add_argument("--sub-bib", action="store_true")
    parser.add_argument("--bib-confidence", type=float)
    args = parser.parse_args()

    config = load_config()
    logger = setup_logging(config, config['logging']['get_prefix'])
    db = Database(config, logger)

    face_conf = args.face_match_confidence or config['search']['face_match_confidence']
    detect_conf = args.face_detect_confidence or config['search']['face_detect_confidence']
    bib_conf = args.bib_confidence or config['search']['bib_confidence']

    if not (args.bib or args.faces):
        logger.error("Must provide either bib or face images")
        return

    photo_paths = set()
    
    if args.bib:
        paths = db.search_bib(args.bib, args.sub_bib, bib_conf)
        photo_paths.update(paths)
        logger.debug(f"Bib {args.bib}:")
        for path in paths:
            logger.debug(f"  {path}")

    if args.faces:
        db.build_faiss_index()
        if db.faiss_index is None:
            logger.warning("No face data in database, skipping face search")
        else:
            import faiss
            logger.debug(f"FAISS index dimension: {db.faiss_index.d}")
            logger.debug(f"FAISS index contains {db.faiss_index.ntotal} embeddings")

            from deepface import DeepFace
            expected_dim = config.get('deepface', {}).get('embedding_dim', 512)
            c = db.conn.cursor()
            for face_path in args.faces:
                try:
                    logger.debug(f"Processing face image: {face_path}")
                    img = cv2.imread(face_path)
                    if img is None:
                        logger.error(f"Failed to load face image: {face_path}")
                        continue
                    
                    height, width = img.shape[:2]
                    if width > 800:
                        scale = 800 / width
                        new_width = 800
                        new_height = int(height * scale)
                        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
                        logger.debug(f"Resized {face_path} from {width}x{height} to {new_width}x{new_height}")

                    representations = DeepFace.represent(
                        img_path=img,
                        model_name=config['deepface']['model'],
                        #detector_backend='yunet',
                        detector_backend=config['deepface']['detector'],
                        align=config['deepface']['alignment']
                    )
                    if not representations:
                        logger.warning(f"No faces detected in {face_path}")
                        continue
                    
                    embedding = None
                    for rep in representations:
                        confidence = rep.get('face_confidence', 0.0)
                        if confidence >= detect_conf:
                            embedding = np.array(rep["embedding"], dtype=np.float32).flatten()
                            break
                    
                    if embedding is None:
                        logger.warning(f"No faces with confidence >= {detect_conf} in {face_path}")
                        continue

                    if len(embedding) != expected_dim:
                        logger.error(f"Query embedding dimension mismatch for {face_path}: expected {expected_dim}, got {len(embedding)}")
                        continue

                    logger.debug(f"Input embedding dimension for {face_path}: {embedding.shape}")

                    query_embedding = embedding.copy()
                    if config['search']['similarity_metric'] == 'cosine':
                        faiss.normalize_L2(query_embedding.reshape(1, -1))

                    D, I = db.faiss_index.search(query_embedding.reshape(1, -1), k=100)
                    logger.debug(f"FAISS search results for {face_path}:")
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
                            c.execute(f"SELECT photo_path FROM {config['database']['photo_table']} p "
                                     f"JOIN {config['database']['face_table']} f ON p.id = f.photo_id "
                                     f"WHERE f.embedding = (SELECT embedding FROM {config['database']['face_table']} LIMIT 1 OFFSET {i})")
                            path = c.fetchone()[0]
                            paths.add(path)
                            logger.debug(f"Add path: {path}")
                    photo_paths.update(paths)
                    logger.info(f"Face {face_path}:")
                    for path in paths:
                        logger.info(f"  {path}")
                except Exception as e:
                    logger.error(f"Error processing face image {face_path}: {str(e)}")

    logger.info(f"Total unique photos: {len(photo_paths)}")
    for p in photo_paths:
        print(p)

    if args.zip_file:
        with zipfile.ZipFile(args.zip_file, 'w') as zipf:
            for path in photo_paths:
                full_path = os.path.join(config['photo_dir'], path)
                zipf.write(full_path, path)
        logger.info(f"Created zip file: {args.zip_file}")

import os
#os.environ["CUDA_VISIBLE_DEVICES"]=""
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # or any {'0', '1', '2'}

if __name__ == "__main__":
    extract_photos()
