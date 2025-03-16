from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlite3
import yaml
import cv2
import numpy as np
import base64
from datetime import datetime
import os
import io
import zipfile
import sys
sys.path.append('..')
from mphoto import extract
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve

app = FastAPI()

# 加载配置文件
with open("app.yaml", "r") as f:
    config = yaml.safe_load(f)

# 设置默认 base_path
BASE_PATH = "./data/"

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="pages"), name="static")

# 挂载 thumb 目录，但不允许目录浏览
app.mount("/file", StaticFiles(directory=BASE_PATH, html=False, follow_symlink=True), name="file")

# SQLite 数据库连接
def get_db():
    conn = sqlite3.connect(config["db"]["path"])
    conn.row_factory = sqlite3.Row  # 返回字典格式的行
    return conn

# 初始化数据库
if not os.path.exists(config["db"]["path"]):
    with get_db() as conn:
        with open("db.sql", "r") as f:
            conn.executescript(f.read())

class BibRequest(BaseModel):
    code: str

class ThumsRequest(BaseModel):
    images: list[str]
    code: str

class DownloadRequest(BaseModel):
    thumbs: list[str]
    code: str

def ensure_event_dirs(event_id: int):
    """确保 event-id 的存储目录存在"""
    event_dir = os.path.join(BASE_PATH, str(event_id))
    raw_dir = os.path.join(event_dir, "raw")
    thumb_dir = os.path.join(event_dir, "thumb")
    return event_dir, raw_dir, thumb_dir

def validate_code(code: str):
    """验证 code 并返回合并的 event 和 bib 数据，或错误信息"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT b.event_id, b.bib, b.code, b.expiry AS bib_expiry, b.name,
                   e.name AS event_name, e.enabled, e.expiry AS event_expiry
            FROM bib b
            JOIN event e ON b.event_id = e.id
            WHERE b.code = ?
            """,
            (code,)
        )
        result = cursor.fetchone()
        
        if not result:
            return {"error": "No matching bib found for the provided code"}
        
        result_dict = dict(result)
        now = datetime.now().isoformat()
        
        if not result_dict["enabled"]:
            return {"error": "Event is disabled"}
        
        if result_dict["event_expiry"] < now:
            return {"error": "Event has expired"}
        if result_dict["bib_expiry"] < now:
            return {"error": "Bib has expired"}
        
        return result_dict

def check_download_limit(bib: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(total_size) as total FROM download_history WHERE bib_number = ? AND timestamp > ?",
            (bib, datetime.now().strftime("%Y-%m-%d"))
        )
        result = cursor.fetchone()
    return result["total"] or 0

def log_download(bib_info, num_files, total_size):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO download_history (event_id, bib_number, timestamp, files, total_size) VALUES (?, ?, ?, ?, ?)",
            (bib_info["event_id"], bib_info["bib"], datetime.now().isoformat(), num_files, total_size)
        )
        conn.commit()

@app.post("/bib")
async def get_bib(request: BibRequest):
    result = validate_code(request.code)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return result

@app.post("/thumb")
async def get_thumbs(request: ThumsRequest):
    bib_info = validate_code(request.code)
    if "error" in bib_info:
        return JSONResponse(status_code=400, content=bib_info)
    
    event_dir, _, thumb_dir = ensure_event_dirs(bib_info["event_id"])
    
    # 将图像解码为 numpy 数组
    images = [cv2.imdecode(np.frombuffer(base64.b64decode(img.split(",")[1]), np.uint8), cv2.IMREAD_COLOR) for img in request.images]
    
    config_path = os.path.join(event_dir, "config.yaml")
    # 调用 extract 函数，传入 event 子目录
    thumbs = extract(bib_info["bib"], images, config_path)
   
    # 保存缩略图到 thumb 目录
    thum_paths = []
    for thumb in thumbs:
        full_path = os.path.join(thumb_dir, thumb)
        thum_paths.append(f"{bib_info['event_id']}/thumb/{thumb}")
    
    return {"main-url": config["storage"]["base_url"], "thumbs": thum_paths}

@app.post("/download")
async def download_files(request: DownloadRequest):
    bib_info = validate_code(request.code)
    if "error" in bib_info:
        return JSONResponse(status_code=400, content=bib_info)
    
    # 检查下载限制，使用配置文件中的值或默认值
    max_total_download_size = config["storage"].get("max_total_download_size", 2147483648)  # 默认 2GB
    total_size = check_download_limit(bib_info["bib"])
    if total_size > max_total_download_size:
        return JSONResponse(status_code=400, content={"error": "Download limit exceeded"})
    
    # 获取 raw 目录
    _, raw_dir, thumb_dir = ensure_event_dirs(bib_info["event_id"])
    
    # 计算 raw 目录下对应文件的总大小
    total_raw_size = 0
    raw_files = {}
    for thumb in request.thumbs:
        # 从 thumb 路径提取文件名
        thumb_filename = thumb.split("/")[-1]
        raw_file_path = os.path.join(raw_dir, thumb_filename)
        if os.path.exists(raw_file_path):
            file_size = os.path.getsize(raw_file_path)
            total_raw_size += file_size
            raw_files[thumb_filename] = raw_file_path
        else:
            return JSONResponse(status_code=404, content={"error": f"Raw file for {thumb_filename} not found"})
    
    # 检查是否超过单个 zip 文件大小限制，使用配置文件中的值或默认值
    max_zip_size = config["storage"].get("max_zip_size", 1073741824)  # 默认 1GB
    if total_raw_size > max_zip_size:
        return JSONResponse(status_code=400, content={"error": "Selected files exceed the maximum zip size limit. Please select fewer images."})
    
    # 创建 zip 文件流
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for thumb_filename, raw_file_path in raw_files.items():
            with open(raw_file_path, "rb") as f:
                zip_file.writestr(thumb_filename, f.read())
    
    zip_buffer.seek(0)
    zip_size = zip_buffer.getbuffer().nbytes
    
    # 记录下载历史
    log_download(bib_info, len(request.thumbs), zip_size)
    
    # 返回文件流，提示浏览器下载
    return StreamingResponse(
        io.BytesIO(zip_buffer.getvalue()),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=photo.zip"
        }
    )

@app.get("/")
async def serve_index():
    return FileResponse("pages/index.html")

# 使用 Hypercorn 运行 FastAPI
async def main():
    hypercorn_config = Config()
    hypercorn_config.bind = ["0.0.0.0:8000"]
    await serve(app, hypercorn_config)

if __name__ == "__main__":
    asyncio.run(main())
