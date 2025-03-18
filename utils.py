import yaml
import logging
from datetime import datetime
import os
from config import config

def setup_logging(prefix):
    # 创建日志目录
    log_dir = config['logging']['dir']
    os.makedirs(log_dir, exist_ok=True)
    
    # 生成带时间戳的日志文件名
    timestamp = datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")[:-3]
    log_file = f"{log_dir}/{prefix}-{timestamp}.log"
    
    # 创建日志器
    logger = logging.getLogger(__name__)
    level_str = config.get('logging', {}).get('level', 'INFO').upper()
    level = getattr(logging, level_str, logging.INFO)
    logger.setLevel(level)
    
    # 创建日志格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # 创建文件处理器
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    
    # 创建屏幕处理器（如果配置允许）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # 清除任何现有的处理器
    logger.handlers.clear()
    
    # 添加处理器
    logger.addHandler(file_handler)
    if config['logging']['screen_print']:
        logger.addHandler(console_handler)
    
    return logger

def get_event_dir(event_id, sub_dir):
    p = os.path.join(config['photo_dir'], event_id)
    return os.path.join(p, sub_dir)

