import logging
import os
import re
import urllib.parse
from typing import Optional
from datetime import datetime
from config import config

image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', 'heic']

def setup_logging(prefix):
    log_dir = config['logging']['dir']
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H_%M_%S.%f")[:-3]
    log_file = f"{log_dir}/{prefix}-{timestamp}.log"
    logger = logging.getLogger(__name__)
    level_str = config.get('logging', {}).get('level', 'INFO').upper()
    level = getattr(logging, level_str, logging.INFO)
    logger.setLevel(level)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    logger.handlers.clear()
    logger.addHandler(file_handler)
    if config['logging']['screen_print']:
        logger.addHandler(console_handler)
    
    return logger

def replace_parent_path(original_path, new_parent_path):
    file_name = os.path.basename(original_path)
    new_path = os.path.join(new_parent_path, file_name)
    return new_path

def compare_timestamps(timestamp1: str, timestamp2: str) -> int:
    dt1 = datetime.fromisoformat(timestamp1.replace('Z', '+00:00'))
    dt2 = datetime.fromisoformat(timestamp2.replace('Z', '+00:00'))
    if dt1 < dt2:
        return -1
    elif dt1 > dt2:
        return 1
    else:
        return 0

def extract_album_id(url):
    marker = "google.com/lr/album/"
    if marker in url:
        return url.split(marker, 1)[1]
    return None

def extract_folder_id(url: str) -> Optional[str]:
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    return query.get('id', [None])[0]

def is_image_file(name: str) -> bool:
    return any(name.lower().endswith(ext) for ext in image_exts)
