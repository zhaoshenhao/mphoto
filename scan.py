import argparse
import os
import cv2
import multiprocessing.queues
import traceback
import psutil
import time
import asyncio
import numpy as np
import json
from multiprocessing import Process, Manager, set_start_method
from utils import setup_logging
from datetime import datetime
from config import config
from client_api import ClientAPI
from gdrive import GoogleDrive
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()
tmp_dir = config.get('tmp_dir', './tmp')

def is_heic_file(file_path):
    extension = os.path.splitext(file_path)[1].lower()
    return extension == '.heic'

def load_heic_image(file_path):
    try:
        pil_image = Image.open(file_path).convert('RGB')
        img_array = np.array(pil_image)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        return img_bgr
    except Exception as e:
        print(f"Error loading HEIC image: {e}")
        return None
    
def open_image(f):
    print(f)
    if is_heic_file(f):
        return load_heic_image(f)
    else:
        return cv2.imread(f)

def worker_process(worker_id, photo_queue, result_queue):
    logger = setup_logging(f"{config['logging']['scan_prefix']}_worker_{worker_id}")
    from processor import ImageProcessor
    processor = ImageProcessor(config, logger)
    logger.info(f"Worker {worker_id} started")
    gclient = GoogleDrive()
    mclient = ClientAPI()
    
    while True:
        try:
            p = photo_queue.get(timeout=1)
            if p is None:
                logger.info(f"Worker {worker_id} received sentinel(None) value, exiting")
                break
            else:
                logger.info(f"Worker {worker_id} received photo: {p['name']} ({p['id']} / {p['gdid']})")
        except multiprocessing.queues.Empty:
            logger.info(f"Worker {worker_id} found photo queue empty, exiting")
            break
            
        try:
            process = psutil.Process()
            mem_before = process.memory_info().rss / 1024 / 1024
            logger.info(f"Worker {worker_id} memory usage before processing {p['name']}: {mem_before:.2f} MB")

            f = os.path.join(tmp_dir, p['name'])
            logger.info(f"Download file from google drive: {f}")
            gclient.download(p['gdid'], f)
            
            img = open_image(f)
            f_size = os.path.getsize(f)
            if img is None:
                logger.error(f"Worker {worker_id} failed to load image: {p['name']}")
                result_queue.put((p['name'], -1))
                continue
            
            height, width = img.shape[:2]
            if width > 2000:
                scale = 2000 / width
                new_width = 2000
                new_height = int(height * scale)
                img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
                logger.debug(f"Worker {worker_id} resized {f} from {width}x{height} to {new_width}x{new_height}")
            
            img2 = img.copy()
            face_embeddings = processor.process_faces(img, f, logger)
            bibs = processor.process_bibs(img2, f, logger)
            f_list = []
            for (embedding, confidence) in face_embeddings:
                f = {}
                f['embedding'] = embedding.tolist()
                f['confidence'] = confidence
                f_list.append(f)
            b_list = []
            for (bib_number, confidence) in bibs:
                b = {}
                b['bib_number'] = bib_number
                b['confidence'] = confidence
                b_list.append(b)
            data = {
                'bib_photos': b_list,
                'face_photos': f_list,
                'photo_size': f_size
            }
            logger.info(f"Add photo result:")
            logger.info(f"Worker {worker_id} Add photo result: {p['name']} ({p['id']} / {p['gdid']})")
            logger.info(f"  found bibs: {len(b_list)}")
            logger.info(f"  found faces: {len(f_list)}")
            mclient.add_photo_result(p['id'], data)
            mem_after = process.memory_info().rss / 1024 / 1024
            result_queue.put((p['name'], 0))
            logger.info(f"Worker {worker_id} memory usage after processing {p['name']}: {mem_after:.2f} MB")
        except Exception as e:
            logger.error(f"Worker {worker_id} error for {p['name']}: {str(e)}\n{traceback.format_exc()}")
            result_queue.put((p['name'], -1))
        logger.debug(f"Worker {worker_id}: Send status sync")
    logger.info(f"Worker {worker_id} completed and exiting")

class Scaner:
    def __init__(self, cloud_storage_id):
        self.logger = setup_logging(config['logging']['scan_prefix'])
        self.sync_timeout = config.get('sync_timeout', 60)
        self.cloud_storage_id = cloud_storage_id
        self.total_photos = 0
        self.processed_count = 0
        self.incomplete_count = 0
        self.update_list = []
        self.mclient = ClientAPI()

    def print_summary(self):
        print(f"Total batch photos: {self.total_photos}")
        print(f"Total processed photos: {self.processed_count}")
        print(f"Failed photos count: {self.incomplete_count}")
        print(json.dumps(self.mclient.get_cloud_storage_detail(self.cloud_storage_id), indent=2))

    async def scan_async(self):
        total_memory = psutil.virtual_memory().total / 1024 / 1024
        self.logger.info(f"Total system memory: {total_memory:.2f} MB")
    
        manager = Manager()
        photo_queue = manager.Queue()
        result_queue = manager.Queue()
    
        for p in self.update_list:
            photo_queue.put(p)
        
        parallel_workers = config.get('parallel', {}).get('workers', 4)
        available_cores = os.cpu_count()
        parallel_workers = min(parallel_workers, available_cores, int(self.total_photos / 2) or 1)
        for _ in range(parallel_workers):
            photo_queue.put(None)
        self.logger.info(f"Loaded {len(self.update_list)} photos into queue with {parallel_workers} sentinels")
    
        self.logger.info(f"Starting {parallel_workers} worker processes (CPU cores: {available_cores}, images: {self.total_photos})")
    
        os.makedirs(tmp_dir, exist_ok=True)
        worker_status = {}
        workers = {}
        for i in range(parallel_workers):
            p = Process(target=worker_process, args=(i, photo_queue, result_queue))
            p.start()
            workers[i] = p
            worker_status[i] = time.time() + config['master_wait_for']
    
        while True:
            await asyncio.sleep(1)  # Async sleep
            active_workers = sum(1 for p in workers.values() if p.is_alive())
            self.logger.debug(f"Active workers: {active_workers}, processed: {self.processed_count}, failed: {self.incomplete_count}, total: {len(self.update_list)}")
        
            # Check completion 
            current_time = time.time()
            completed = False
            if (photo_queue.qsize() <= 0 and active_workers <= 0) or (self.processed_count + self.incomplete_count >= len(self.update_list)):
                self.logger.info(f"All photos accounted for: processed {self.processed_count}, incomplete {self.incomplete_count}, total {len(self.update_list)}")
                completed = True
            if completed:
                await asyncio.sleep(5)
                for worker_id, p in workers.items():
                    if p.is_alive():
                        self.logger.info(f"Terminating worker {worker_id}")
                        p.kill()
                        p.join()
                break

            # Kill hanging worker and create new worker
            for worker_id, last_updated in list(worker_status.items()):
                if current_time - last_updated > self.sync_timeout:
                    last_update = datetime.fromtimestamp(last_updated).strftime('%c')
                    self.logger.warning(f"Worker {worker_id} timed out (last updated {last_update})")
                    workers[worker_id].kill()
                    workers[worker_id].join()
                    self.incomplete_count += 1
                
                    worker_status[worker_id] = time.time() + config['master_wait_for']
                    new_p = Process(target=worker_process, args=(worker_id, photo_queue, result_queue))
                    new_p.start()
                    workers[worker_id] = new_p
                    self.logger.info(f"Restarted worker {worker_id}")
            
            try:
                _, status = result_queue.get(timeout=1)
                self.processed_count += 1
                if status < 0:
                    self.incomplete_count += 1
                self.logger.debug(f"Processed {self.processed_count}/{len(self.update_list)} photos")

            except multiprocessing.queues.Empty:
                pass
            
        for w in workers.values():
            w.join()
    
        self.logger.info("Photo scanning completed")
        self.print_summary()

    def scan(self):
        self.logger.info("Getting cloud storage info...")
        cs = self.mclient.get_cloud_storage_detail(self.cloud_storage_id)
        self.logger.info(f"Cloud Storage: {cs}")

        self.logger.info("Getting photo list...")
        self.update_list = self.mclient.list_photos(cloud_storage_id=self.cloud_storage_id, incomplete=True)
        self.logger.info(f"Photos to update: {len(self.update_list)}")
        if not self.update_list or len(self.update_list) == 0:
            self.logger.info(f"No new or modified photo found.")
            exit(0)
        self.total_photos = len(self.update_list)
        asyncio.run(self.scan_async())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan photo for face and bib of an event")
    parser.add_argument("-c", "--cloud-storage-id", type=int, help="Cloud storage ID")
    args = parser.parse_args()
    try:
        set_start_method('spawn')
    except RuntimeError:
        pass
    scaner = Scaner(args.cloud_storage_id)
    scaner.scan()
