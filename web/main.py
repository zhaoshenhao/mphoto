from pydantic import BaseModel
import yaml
import cv2
import numpy as np
import base64
from datetime import datetime
import os
import io
import zipfile
import sys
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
sys.path.append('.')
from mphoto import extract
from config import config
from database import Database, DatabasePool
from utils import setup_logging, get_event_dir

app = FastAPI()

logger = setup_logging(config['logging']['web_prefix'])

BASE_PATH = config['photo_dir']

app.mount("/static", StaticFiles(directory="web/pages"), name="static")
app.mount("/file", StaticFiles(directory=BASE_PATH, follow_symlink=True, html=False), name="file")

class BibRequest(BaseModel):
    code: str

class ThumsRequest(BaseModel):
    images: list[str]
    code: str

class DownloadRequest(BaseModel):
    thumbs: list[str]
    code: str

def ensure_event_dirs(event_id: int):
    event_dir = os.path.join(BASE_PATH, str(event_id))
    raw_dir = get_event_dir(event_id, config['storage']['raw_path'])
    thumb_dir = get_event_dir(event_id, config['storage']['thumb_path'])
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(thumb_dir, exist_ok=True)
    return raw_dir, thumb_dir

async def validate_code(code: str, db: Database):
    result = await db.get_event_bib_by_code(code)
    if "error" in result:
        return result
    
    now = datetime.now()
    if not result["event_enabled"]:
        return {"error": "Event is disabled"}
    if result["event_expiry"] < now:
        return {"error": "Event has expired"}
    if not result["bib_enabled"]:
        return {"error": "Bib is disabled"}
    if result["bib_expiry"] < now:
        return {"error": "Bib has expired"}
    return result

@app.post("/bib")
async def get_bib(request: BibRequest):
    db = Database(logger)
    result = await validate_code(request.code, db)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return result

@app.post("/thumb")
async def get_thumbs(request: ThumsRequest):
    db = Database(logger)
    bib_info = await validate_code(request.code, db)
    if "error" in bib_info:
        return JSONResponse(status_code=400, content=bib_info)
        
    _, thumb_dir = ensure_event_dirs(bib_info["event_id"])
        
    images = [cv2.imdecode(np.frombuffer(base64.b64decode(img.split(",")[1]), np.uint8), cv2.IMREAD_COLOR) 
             for img in request.images]
    
    thumbs = await asyncio.get_event_loop().run_in_executor(None, extract, bib_info["event_id"], bib_info["bib"], images, logger, db)
   
    thum_paths = []
    for thumb in thumbs:
        full_path = os.path.join(thumb_dir, thumb)
        thum_paths.append(f"{bib_info['event_id']}/thumb/{thumb}")
        
    return {"main-url": config["storage"]["base_url"], "thumbs": thum_paths}

@app.post("/download")
async def download_files(request: DownloadRequest):
    db = Database(logger)
    bib_info = await validate_code(request.code, db)
    if "error" in bib_info:
        return JSONResponse(status_code=400, content=bib_info)
        
    max_total_download_size = config["storage"].get("max_total_download_size", 2147483648)
    total_size = await db.get_download_limit(bib_info['bib_id'])
    if total_size > max_total_download_size:
        return JSONResponse(status_code=400, content={"error": "Download limit exceeded"})
        
    raw_dir, thumb_dir = ensure_event_dirs(bib_info["event_id"])
        
    total_raw_size = 0
    raw_files = {}
    for thumb in request.thumbs:
        thumb_filename = thumb.split("/")[-1]
        raw_file_path = os.path.join(raw_dir, thumb_filename.replace("thumb_", ""))
        if os.path.exists(raw_file_path):
            file_size = os.path.getsize(raw_file_path)
            total_raw_size += file_size
            raw_files[thumb_filename] = raw_file_path
        else:
            return JSONResponse(status_code=404, content={"error": f"Raw file for {thumb_filename} not found"})
        
    max_zip_size = config["storage"].get("max_zip_size", 1073741824)
    if total_raw_size > max_zip_size:
        return JSONResponse(status_code=400, content={"error": "Selected files exceed the maximum zip size limit."})
        
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for thumb_filename, raw_file_path in raw_files.items():
            with open(raw_file_path, "rb") as f:
                zip_file.writestr(thumb_filename.replace("thumb_", ""), f.read())
        
    zip_buffer.seek(0)
    zip_size = zip_buffer.getbuffer().nbytes
    
    await db.log_download(bib_info['bib_id'], zip_size)
    
    return StreamingResponse(
        io.BytesIO(zip_buffer.getvalue()),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=photo.zip"}
    )

@app.get("/")
async def serve_index():
    return FileResponse("web/pages/index.html")

async def main():
    await DatabasePool.initialize(logger)  # Initialize pool at startup
    hypercorn_config = Config()
    hypercorn_config.bind = ["0.0.0.0:8000"]
    await serve(app, hypercorn_config)

if __name__ == "__main__":
    asyncio.run(main())
