import yaml
from pathlib import Path
from typing import Dict, Any

DEFAULT_CONFIG = {
    # ... 默认配置与yaml结构一致 ...
}

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        # 合并默认配置
        return {**DEFAULT_CONFIG, **config}
    except FileNotFoundError:
        return DEFAULT_CONFIG
