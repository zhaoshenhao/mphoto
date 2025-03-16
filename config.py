# config.py
import yaml
import logging
from pathlib import Path

# Default path
CONFIG_PATH = Path(__file__).parent / "config.yaml"

# Load the config
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

# Database
DB_CONFIG = config.get("database", {})
TABLES = {
    "event": DB_CONFIG.get("table_event", "event"),
    "bib": DB_CONFIG.get("table_bib", "bib"),
    "download_history": DB_CONFIG.get("table_download_history", "download_history"),
    "photo": DB_CONFIG.get("table_photo", "photo"),
    "bib_photo": DB_CONFIG.get("table_bib_photo", "bib_photo"),
    "face_photo": DB_CONFIG.get("table_face_photo", "face_photo"),
}

# PostgreSQL
DB_HOST = DB_CONFIG.get("host", "localhost")
DB_PORT = DB_CONFIG.get("port", 5432)
DB_NAME = DB_CONFIG.get("name", "mphoto")
DB_USER = DB_CONFIG.get("user", "postgres")
DB_PASSWORD = DB_CONFIG.get("password", "your_password")

# 日志配置
LOG_CONFIG = config.get("logging", {})
logging.basicConfig(
    level=LOG_CONFIG.get("level", "INFO"),
    format=LOG_CONFIG.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    filename=LOG_CONFIG.get("file", "mphoto.log")
)
logger = logging.getLogger(__name__)

# Others（从 app.yaml 合并）
PHOTO_DIR = config.get("photo_dir", "/path/to/photos")
