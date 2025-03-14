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
from datetime import datetime

def worker_process(worker_id, photo_queue, result_queue, config):
    logger = setup_logging(config, f"{config['logging']['scan_prefix']}_worker_{worker_id}")
    processor = ImageProcessor(config, logger)
    
    # 开始启动时，迟滞检测
    logger.info(f"Worker {worker_id} started")
    
    while True:
        try:
            photo_path = photo_queue.get(timeout=1)
            if photo_path is None:
                logger.info(f"Worker {worker_id} received sentinel value, exiting")
                break
        except multiprocessing.queues.Empty:
            logger.info(f"Worker {worker_id} found photo queue empty, exiting")
            break
            
        try:
            process = psutil.Process()
            mem_before = process.memory_info().rss / 1024 / 1024
            logger.info(f"Worker {worker_id} memory usage before processing {photo_path}: {mem_before:.2f} MB")
            
            img = cv2.imread(photo_path)
            if img is None:
                logger.error(f"Worker {worker_id} failed to load image: {photo_path}")
                result_queue.put((photo_path, [], [], worker_id))
                continue
            
            height, width = img.shape[:2]
            if width > 2000:
                scale = 2000 / width
                new_width = 2000
                new_height = int(height * scale)
                img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
                logger.debug(f"Worker {worker_id} resized {photo_path} from {width}x{height} to {new_width}x{new_height}")
            
            img2 = img.copy()
            rel_path = os.path.relpath(photo_path, config['photo_dir'])
            face_embeddings = processor.process_faces(img, photo_path, logger)
            bibs = processor.process_bibs(img2, photo_path, logger)
            
            mem_after = process.memory_info().rss / 1024 / 1024
            logger.info(f"Worker {worker_id} memory usage after processing {photo_path}: {mem_after:.2f} MB")
            
            result_queue.put((rel_path, bibs, face_embeddings, worker_id))
        except Exception as e:
            logger.error(f"Worker {worker_id} error for {photo_path}: {str(e)}\n{traceback.format_exc()}")
            result_queue.put((photo_path, [], [], worker_id))
        logger.debug(f"Worker {worker_id}: Send status sync")
    
    logger.info(f"Worker {worker_id} completed and exiting")

def print_summary(config, db, total_photos, processed_count, incomplete_count):
    # 从数据库读取总数
    c = db.conn.cursor()
    c.execute(f"SELECT COUNT(*) FROM {config['database']['face_table']}")
    total_faces = c.fetchone()[0]
    c.execute(f"SELECT COUNT(*) FROM {config['database']['bib_table']}")
    total_bibs = c.fetchone()[0]
    
    print(f"Total photos: {total_photos}")
    print(f"Total faces: {total_faces}")
    print(f"Total bibs: {total_bibs}")
    print(f"Total processed photos: {processed_count}")
    print(f"Failed photos count: {incomplete_count}")

def scan_photos():
    config = load_config()
    logger = setup_logging(config, config['logging']['scan_prefix'])
    db = Database(config, logger)
    
    sync_timeout = config.get('sync_timeout', 60)  # 默认 60 秒
    
    logger.info("Starting photo scan")
    total_memory = psutil.virtual_memory().total / 1024 / 1024
    logger.info(f"Total system memory: {total_memory:.2f} MB")
    
    # 读取所有照片文件的相对路径和时间戳
    photo_info = {}
    for root, _, files in os.walk(config['photo_dir']):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                photo_path = os.path.join(root, file)
                rel_path = os.path.relpath(photo_path, config['photo_dir'])
                timestamp = os.path.getmtime(photo_path)
                photo_info[rel_path] = timestamp
    
    total_photos = len(photo_info)
    logger.info(f"Found {total_photos} photos to process")
    
    # 读取 Photo 表数据
    db_photos = db.get_photo_info()
    
    # 处理 photo_purge
    photo_purge = config.get('photo_purge', False)
    if not photo_purge:
        for db_path, (photo_id, _) in db_photos.items():
            if db_path not in photo_info:
                db.delete_photo_data(photo_id)
                logger.info(f"Purged photo_id {photo_id} for path {db_path} not found in file system")
    
    # 检查并生成更新列表
    update_list = []  # [(photo_id, rel_path)]
    for rel_path, file_timestamp in photo_info.items():
        if rel_path in db_photos:
            photo_id, db_timestamp = db_photos[rel_path]
            if db_timestamp >= file_timestamp:
                logger.debug(f"Skipping {rel_path}: database timestamp {db_timestamp} >= file timestamp {file_timestamp}")
                continue
            else:
                db.delete_by_photo_id(photo_id)
                update_list.append((photo_id, rel_path))
                logger.debug(f"Added {rel_path} to update list with photo_id {photo_id}")
        else:
            yesterday = file_timestamp - 24 * 3600
            photo_id = db.add_photo(rel_path, yesterday)
            update_list.append((photo_id, rel_path))
            logger.debug(f"Added new photo {rel_path} with photo_id {photo_id}")
    
    logger.info(f"Photos to update: {len(update_list)}")
    
    if len(update_list) <= 0:
        logger.info(f"Update list is empty")
        print_summary(config, db, 0, 0, [])
        return

    # 使用 Manager 创建队列和共享字典
    manager = Manager()
    photo_queue = manager.Queue()
    result_queue = manager.Queue()
    
    for _, photo_path in update_list:
        photo_queue.put(os.path.join(config['photo_dir'], photo_path))
    parallel_workers = config.get('parallel', {}).get('workers', 4)
    for _ in range(parallel_workers):
        photo_queue.put(None)
    logger.info(f"Loaded {len(update_list)} photos into queue with {parallel_workers} sentinels")
    
    available_cores = os.cpu_count()
    parallel_workers = min(parallel_workers, available_cores, total_photos or 1)
    logger.info(f"Starting {parallel_workers} worker processes (CPU cores: {available_cores}, images: {total_photos})")
    
    worker_status = {}
    workers = {}
    for i in range(parallel_workers):
        p = Process(target=worker_process, args=(i, photo_queue, result_queue, config))
        p.start()
        workers[i] = p
        worker_status[i] = time.time() + config['master_wait_for']
    
    processed_count = 0
    incomplete_count = 0
    empty_queue_time_stamp = None

    while True:
        time.sleep(1)
        active_workers = sum(1 for p in workers.values() if p.is_alive())
        logger.debug(f"Active workers: {active_workers}, processed: {processed_count}, failed: {incomplete_count}, total: {len(update_list)}")
        
        current_time = time.time()
        completed = False
        # 新退出条件：处理数 + 失败数 = 更新总数
        if photo_queue.qsize() <= 0:
            if empty_queue_time_stamp is None:
                empty_queue_time_stamp = time.time()
            elif current_time - empty_queue_time_stamp > sync_timeout:
                logger.info(f"Queue was empty over {sync_timeout} seconds.")
                completed = True
                

        if processed_count + incomplete_count >= len(update_list):
            logger.info(f"All photos accounted for: processed {processed_count}, incomplete {incomplete_count}, total {len(update_list)}")
            completed = True
        if completed:
            time.sleep(5)
            for worker_id, p in workers.items():
                if p.is_alive():
                    logger.info(f"Terminating worker {worker_id}")
                    #p.terminate()
                    p.kill()
                    p.join()
            break
        
        # 检查 worker 超时
        for worker_id, last_updated in list(worker_status.items()):
            if current_time - last_updated > sync_timeout:
                last_update = datetime.fromtimestamp(last_updated).strftime('%c')
                logger.warning(f"Worker {worker_id} timed out (last updated {last_update})")
                workers[worker_id].kill()
                #workers[worker_id].terminate()
                workers[worker_id].join()
                incomplete_count += 1
                
                # 重启 worker, 并迟滞状态检测
                worker_status[worker_id] = time.time() + config['master_wait_for']
                new_p = Process(target=worker_process, args=(worker_id, photo_queue, result_queue, config))
                new_p.start()
                workers[worker_id] = new_p
                logger.info(f"Restarted worker {worker_id}")
        
        try:
            # 处理结果
            rel_path, bibs, face_embeddings, worker_id = result_queue.get(timeout=1)
            processed_count += 1
            logger.debug(f"Processed {processed_count}/{len(update_list)} photos")
            
            photo_id = next(pid for pid, path in update_list if path == rel_path)
            logger.debug(f"Save data: worker: {worker_id}, photo({photo_id}): {rel_path}")
            
            for bib, confidence in bibs:
                db.add_bib(bib, photo_id, confidence)
                logger.info(f"Added bib {bib} with confidence {confidence} for photo_id {photo_id}")
            for embedding, confidence in face_embeddings:
                db.add_face(embedding, photo_id, confidence)
                logger.info(f"Added face with confidence {confidence} for photo_id {photo_id}")
            
            current_time = time.time()
            c = db.conn.cursor()
            c.execute(f"UPDATE {config['database']['photo_table']} SET last_updated = ? WHERE id = ?",
                      (current_time, photo_id))
            db.conn.commit()
            logger.debug(f"Updated timestamp for photo_id {photo_id} to {current_time}")
            worker_status[worker_id] = current_time
        
        except multiprocessing.queues.Empty:
            pass
    
    for w in workers.values():
        w.join()
    
    # 输出结果
    logger.info("Photo scanning completed")
    print_summary(config, db, total_photos, processed_count, incomplete_count)

if __name__ == "__main__":
    try:
        set_start_method('spawn')
    except RuntimeError:
        pass
    scan_photos()
