import argparse
import os
import cv2
import multiprocessing.queues
import traceback
import psutil
import time
from multiprocessing import Process, Manager, set_start_method
from utils import setup_logging, get_event_dir
from datetime import datetime
from config import config
from database import Database

def worker_process(worker_id, photo_queue, result_queue, config, work_dir):
    logger = setup_logging(f"{config['logging']['scan_prefix']}_worker_{worker_id}")
    from processor import ImageProcessor
    processor = ImageProcessor(config, logger)
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
            rel_path = os.path.relpath(photo_path, work_dir)
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

class Scaner:
    def __init__(self, event_id):
        self.logger = setup_logging(config['logging']['scan_prefix'])
        self.db = Database(self.logger)
        self.sync_timeout = config.get('sync_timeout', 60)
        self.event_id = event_id
        self.work_dir = get_event_dir(self.event_id, 'raw')
        self.total_photos = 0
        self.processed_count = 0
        self.incomplete_count = 0
        self.photo_info = {}
        self.image_ext = ('.png', '.jpg', '.jpeg')
        self.update_list = []

    def print_summary(self):
        total_bibs, total_bib_photos, total_faces = self.db.get_event_count(self.event_id)
        print(f"Total bibs: {total_bibs}")
        print(f"Total photos: {self.total_photos}")
        print(f"Total faces: {total_faces}")
        print(f"Total bibs photos: {total_bib_photos}")
        print(f"Total processed photos: {self.processed_count}")
        print(f"Failed photos count: {self.incomplete_count}")

    def get_photo_list(self):
        self.photo_info = {}
        self.logger.debug(f"Workdir: {self.work_dir}")
        for root, _, files in os.walk(self.work_dir):
            for file in files:
                if file.lower().endswith(self.image_ext):
                    photo_path = os.path.join(root, file)
                    rel_path = os.path.relpath(photo_path, self.work_dir)
                    timestamp = os.path.getmtime(photo_path)
                    self.photo_info[rel_path] = timestamp

        self.total_photos = len(self.photo_info)
        self.logger.info(f"Found {self.total_photos} photos to process")

    def get_update_list(self):
        # Get all photos from event raw folder with timestamp
        self.get_photo_list()
        # Get all phots in photo table for event
        db_photos = self.db.get_event_photo_info(self.event_id)
        # photo purge
        photo_purge = config.get('photo_purge', False)
        if not photo_purge:
            for db_path, (photo_id, _) in db_photos.items():
                if db_path not in self.photo_info:
                    self.db.delete_photo(photo_id)
                    self.logger.info(f"Purged photo_id {photo_id} for path {db_path} not found in file system")

        # Create the update list
        for rel_path, file_timestamp in self.photo_info.items():
            if rel_path in db_photos:
                photo_id, db_timestamp = db_photos[rel_path]
                if db_timestamp.timestamp() >= file_timestamp:
                    self.logger.debug(f"Skipping {rel_path}: database timestamp {db_timestamp} >= file timestamp {file_timestamp}")
                    continue
                else:
                    self.db.delete_photo_ref(photo_id)
                    self.update_list.append((photo_id, rel_path))
                    self.logger.debug(f"Added {rel_path} to update list with photo_id {photo_id}")
            else:
                yesterday = datetime.fromtimestamp(file_timestamp - 24 * 3600)
                photo_id = self.db.add_photo(self.event_id, rel_path, yesterday)
                self.update_list.append((photo_id, rel_path))
                self.logger.debug(f"Added new photo {rel_path} with photo_id {photo_id}")

        self.db.conn.commit()
        self.logger.info(f"Photos to update: {len(self.update_list)}")

    def scan(self):
        self.logger.info(f"Starting photo scan for event: {self.event_id}")
        total_memory = psutil.virtual_memory().total / 1024 / 1024
        self.logger.info(f"Total system memory: {total_memory:.2f} MB")
        self.get_update_list()
    
        if len(self.update_list) <= 0:
            self.logger.info(f"Update list is empty")
            self.print_summary()
            return

        # 使用 Manager 创建队列和共享字典
        manager = Manager()
        photo_queue = manager.Queue()
        result_queue = manager.Queue()
    
        for _, photo_path in self.update_list:
            photo_queue.put(os.path.join(self.work_dir, photo_path))
        parallel_workers = config.get('parallel', {}).get('workers', 4)
        for _ in range(parallel_workers):
            photo_queue.put(None)
        self.logger.info(f"Loaded {len(self.update_list)} photos into queue with {parallel_workers} sentinels")
    
        available_cores = os.cpu_count()
        parallel_workers = min(parallel_workers, available_cores, self.total_photos / 2 or 1)
        self.logger.info(f"Starting {parallel_workers} worker processes (CPU cores: {available_cores}, images: {self.total_photos})")
    
        worker_status = {}
        workers = {}
        for i in range(parallel_workers):
            p = Process(target=worker_process, args=(i, photo_queue, result_queue, config, self.work_dir))
            p.start()
            workers[i] = p
            worker_status[i] = time.time() + config['master_wait_for']
    
        empty_queue_time_stamp = None

        while True:
            time.sleep(1)
            active_workers = sum(1 for p in workers.values() if p.is_alive())
            self.logger.debug(f"Active workers: {active_workers}, processed: {self.processed_count}, failed: {self.incomplete_count}, total: {len(self.update_list)}")
        
            current_time = time.time()
            completed = False
            if photo_queue.qsize() <= 0:
                if empty_queue_time_stamp is None:
                    empty_queue_time_stamp = time.time()
                elif current_time - empty_queue_time_stamp > self.sync_timeout:
                    self.logger.info(f"Queue was empty over {self.sync_timeout} seconds.")
                    completed = True
            if self.processed_count + self.incomplete_count >= len(self.update_list):
                self.logger.info(f"All photos accounted for: processed {self.processed_count}, incomplete {self.incomplete_count}, total {len(self.update_list)}")
                completed = True
            if completed:
                time.sleep(5)
                for worker_id, p in workers.items():
                    if p.is_alive():
                        self.logger.info(f"Terminating worker {worker_id}")
                        #p.terminate()
                        p.kill()
                        p.join()
                break

            # Check worker timeout
            for worker_id, last_updated in list(worker_status.items()):
                if current_time - last_updated > self.sync_timeout:
                    last_update = datetime.fromtimestamp(last_updated).strftime('%c')
                    self.logger.warning(f"Worker {worker_id} timed out (last updated {self.last_update})")
                    workers[worker_id].kill()
                    #workers[worker_id].terminate()
                    workers[worker_id].join()
                    self.incomplete_count += 1
                
                    # Restart worker and delay the staus check
                    worker_status[worker_id] = time.time() + config['master_wait_for']
                    new_p = Process(target=worker_process, args=(worker_id, photo_queue, result_queue, config))
                    new_p.start()
                    workers[worker_id] = new_p
                    self.logger.info(f"Restarted worker {worker_id}")
        
            # Handle the return
            try:
                rel_path, bibs, face_embeddings, worker_id = result_queue.get(timeout=1)
                self.processed_count += 1
                self.logger.debug(f"Processed {self.processed_count}/{len(self.update_list)} photos")
            
                photo_id = next(pid for pid, path in self.update_list if path == rel_path)
                self.logger.debug(f"Save data: worker: {worker_id}, photo({photo_id}): {rel_path}")
            
                for bib, confidence in bibs:
                    self.db.add_bib_photo(self.event_id, bib, photo_id, confidence)
                    self.logger.info(f"Added bib {bib} with confidence {confidence} for photo_id {photo_id}")
                for embedding, confidence in face_embeddings:
                    self.db.add_face_photo(self.event_id, photo_id, embedding, confidence)
                    self.logger.info(f"Added face with confidence {confidence} for photo_id {photo_id}")
                self.db.update_photo(photo_id, datetime.now())
                self.db.conn.commit()
                self.logger.debug(f"Updated timestamp for photo_id {photo_id} to {current_time}")
                worker_status[worker_id] = current_time
        
            except multiprocessing.queues.Empty:
                pass
    
        for w in workers.values():
            w.join()
    
        # 输出结果
        self.logger.info("Photo scanning completed")
        self.print_summary()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan photo for face and bib of an event")
    parser.add_argument("-e", "--event-id", help="Event-ID")
    args = parser.parse_args()
    try:
        set_start_method('spawn')
    except RuntimeError:
        pass
    scaner = Scaner(args.event_id)
    scaner.scan()

