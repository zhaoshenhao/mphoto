# config.py
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

# Default path
CONFIG_PATH = Path(__file__).parent / "config.yaml"

DEFAULT_CONFIG = {
}

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    try:
        with open(config_path, 'r') as f:
            mconfig = yaml.safe_load(f)
        return {**DEFAULT_CONFIG, **mconfig}
    except FileNotFoundError:
        return DEFAULT_CONFIG

config = load_config(CONFIG_PATH)

#LOG_LEVEL = config['logging']['level']
FORMAT = config['logging']['format']
