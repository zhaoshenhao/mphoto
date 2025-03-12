import os
from utils import load_config, setup_logging
from database import Database
from processor import ImageProcessor
import cv2
from multiprocessing import Process, Manager, set_start_method
import multiprocessing.queues
import traceback
import psutil
import time

def worker_process(worker_id, photo_queue, result_queue, config, worker_status):
    """Worker 进程：从照片队列读取照片，处理后放入结果队列"""
    logger = setup_logging(config, f"{config['logging']['scan_prefix']}_worker_{worker_id}")
    processor = ImageProcessor(config, logger)
    
    # 更新状态为运行中
    worker_status[worker_id] = 2
    logger.info(f"Worker {worker_id} started")
    
    while True:
        try:
            try:
                photo_path = photo_queue.get(timeout=1)
                if photo_path is None:  # 哨兵值，表示队列结束
                    logger.info(f"Worker {worker_id} received sentinel value, exiting")
                    break
            except multiprocessing.queues.Empty:
                logger.info(f"Worker {worker_id} found photo queue empty, exiting")
                break
            
            process = psutil.Process()
            mem_before = process.memory_info().rss / 1024 / 1024  # MB
            logger.info(f"Worker {worker_id} memory usage before processing {photo_path}: {mem_before:.2f} MB")
            
            # 读取图片
            img = cv2.imread(photo_path)
            if img is None:
                logger.error(f"Worker {worker_id} failed to load image: {photo_path}")
                result_queue.put((photo_path, [], []))
                continue
            
            # 检查并缩放图片
            height, width = img.shape[:2]
            if width > 2000:
                scale = 2000 / width
                new_width = 2000
                new_height = int(height * scale)
                img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
                logger.debug(f"Worker {worker_id} resized {photo_path} from {width}x{height} to {new_width}x{new_height}")
            
            img2 = img.copy()  # 缩放后的副本
            rel_path = os.path.relpath(photo_path, config['photo_dir'])
            face_embeddings = processor.process_faces(img, photo_path, logger)
            bibs = processor.process_bibs(img2, photo_path, logger)
            
            mem_after = process.memory_info().rss / 1024 / 1024  # MB
            logger.info(f"Worker {worker_id} memory usage after processing {photo_path}: {mem_after:.2f} MB")
            
            result_queue.put((rel_path, bibs, face_embeddings))
        
        except Exception as e:
            logger.error(f"Worker {worker_id} error for {photo_path}: {str(e)}\n{traceback.format_exc()}")
            result_queue.put((photo_path, [], []))
    
    # 更新状态为结束
    time.sleep(30)
    worker_status[worker_id] = 0
    logger.info(f"Worker {worker_id} completed and exiting")

def scan_photos():
    config = load_config()
    logger = setup_logging(config, config['logging']['scan_prefix'])
    db = Database(config, logger)
    
    logger.info("Starting photo scan")
    total_memory = psutil.virtual_memory().total / 1024 / 1024  # MB
    logger.info(f"Total system memory: {total_memory:.2f} MB")
    
    # 收集所有图片路径
    photo_paths = []
    for root, _, files in os.walk(config['photo_dir']):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                photo_path = os.path.join(root, file)
                photo_paths.append(photo_path)
    
    total_photos = len(photo_paths)
    logger.info(f"Found {total_photos} photos to process")
    
    # 使用 Manager 创建队列和共享字典
    manager = Manager()
    photo_queue = manager.Queue()
    result_queue = manager.Queue()
    worker_status = manager.dict()
    
    # 将照片路径放入队列，并添加哨兵值
    for photo_path in photo_paths:
        photo_queue.put(photo_path)
    parallel_workers = config.get('parallel', {}).get('workers', 4)
    for _ in range(parallel_workers):
        photo_queue.put(None)
    logger.info(f"Loaded {total_photos} photos into queue with {parallel_workers} sentinels")
    
    # 从配置中读取并行数
    available_cores = os.cpu_count()
    parallel_workers = min(parallel_workers, available_cores, total_photos or 1)
    logger.info(f"Starting {parallel_workers} worker processes (CPU cores: {available_cores}, images: {total_photos})")
    
    # 启动 worker 进程并初始化状态
    workers = []
    for i in range(parallel_workers):
        worker_status[i] = 1  # 初始状态
        p = Process(target=worker_process, args=(i, photo_queue, result_queue, config, worker_status))
        p.start()
        workers.append(p)
    
    # 主进程从结果队列读取数据并写入数据库
    processed_count = 0
    incomplete_count = 0  # 连续未完成计数
    while True:
        try:
            rel_path, bibs, face_embeddings = result_queue.get(timeout=5)
            processed_count += 1
            logger.debug(f"Processed {processed_count}/{total_photos} photos")
            for bib, confidence in bibs:
                db.add_bib(bib, rel_path, confidence)
                logger.info(f"Added bib {bib} with confidence {confidence} for {rel_path}")
            for embedding, confidence in face_embeddings:
                db.add_face(embedding, rel_path, confidence)
                logger.info(f"Added face with confidence {confidence} for {rel_path}")
            incomplete_count = 0  # 重置计数器
        
        except multiprocessing.queues.Empty:
            # 检查所有 worker 状态
            active_workers = sum(1 for status in worker_status.values() if status != 0)
            logger.debug(f"Queue empty, active workers: {active_workers}, processed: {processed_count}/{total_photos}")
            
            if active_workers == 0:
                if processed_count == total_photos:
                    logger.info("All photos processed, exiting")
                    break
                else:
                    incomplete_count += 1
                    logger.warning(f"Incomplete processing: {processed_count}/{total_photos} photos, check {incomplete_count}/3")
                    if incomplete_count >= 3:
                        logger.error(f"Processing failed: only {processed_count}/{total_photos} photos completed after 3 checks")
                        break
                    time.sleep(30)  # 等待 30 秒再检查
            else:
                time.sleep(1)  # 有活跃 worker，继续等待
    
    # 确保所有 worker 进程已结束
    for w in workers:
        w.join()
    
    logger.info("Photo scanning completed")

if __name__ == "__main__":
    try:
        set_start_method('spawn')
    except RuntimeError:
        pass
    scan_photos()
