# config.py
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

# Default path
CONFIG_PATH = Path(__file__).parent / "config.yaml"

DEFAULT_CONFIG = {
    # ... 默认配置与yaml结构一致 ...
}

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    try:
        with open(config_path, 'r') as f:
            mconfig = yaml.safe_load(f)
        # 合并默认配置
        return {**DEFAULT_CONFIG, **mconfig}
    except FileNotFoundError:
        return DEFAULT_CONFIG

config = load_config(CONFIG_PATH)

DB_HOST = config['database']['host']
DB_PORT = config['database']['port']
DB_USER = config['database']['username']
DB_PASS = config['database']['password']
DB_NAME = config['database']['database']
TABLES = config['table_names']
LOG_LEVEL = config['logging']['level']
FORMAT = config['logging']['format']
DEFAULT_SEARCH_LIMIT = config.get("database", {}).get("default_search_limit", 100)
