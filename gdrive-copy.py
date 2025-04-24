import argparse
import os
import logging
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from urllib.parse import urlparse, parse_qs

IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']

def setup_logger(output_dir):
    log_path = os.path.join(output_dir, 'download.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, mode='w'),
            logging.StreamHandler()
        ]
    )

def log(msg):
    logging.info(msg)

def extract_folder_id(shared_url):
    parsed = urlparse(shared_url)
    if 'folders' in parsed.path:
        return parsed.path.split('/')[-1]
    qs = parse_qs(parsed.query)
    return qs.get('id', [None])[0]

def should_download(file_name, file_type, file_exts):
    ext = os.path.splitext(file_name)[1].lower()
    if file_exts:
        return ext in [f".{e.lower().lstrip('.')}" for e in file_exts]
    if file_type == 'image':
        return ext in IMAGE_EXTS
    return True

def download_folder(drive, folder_id, local_path, level, max_depth, file_type, file_exts):
    if not os.path.exists(local_path):
        os.makedirs(local_path)
        log(f"📁 Created folder: {local_path}")

    log(f"📂 Entering folder: {local_path}")
    file_list = drive.ListFile({'q': f"'{folder_id}' in parents and trashed=false"}).GetList()

    for f in file_list:
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            if max_depth == -1 or level < max_depth:
                subfolder_path = os.path.join(local_path, f['title'])
                download_folder(drive, f['id'], subfolder_path, level+1, max_depth, file_type, file_exts)
        else:
            if should_download(f['title'], file_type, file_exts):
                dest_path = os.path.join(local_path, f['title'])
                log(f"📥 Downloading: {f['title']} → {dest_path}")
                try:
                    f.GetContentFile(dest_path)
                except Exception as e:
                    log(f"❌ Failed to download {f['title']}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Download files from a shared Google Drive folder")
    parser.add_argument('-u', '--url', required=True, help='Shared Google Drive folder URL')
    parser.add_argument('-r', '--recursive', type=int, default=0, help='Recursion level: 0 (default), -1 (full), or n levels')
    parser.add_argument('-t', '--file-type', choices=['image', 'all'], default='image', help='Type of files to download')
    parser.add_argument('-e', '--file-ext', nargs='*', help='Specific extensions to download (e.g. jpg png pdf)')
    parser.add_argument('-o', '--output-dir', default='output', help='Output directory (default: output)')

    args = parser.parse_args()
    service_json_path = 'service_account.json'

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    setup_logger(args.output_dir)

    folder_id = extract_folder_id(args.url)
    if not folder_id:
        log("❌ Could not extract folder ID from the URL.")
        return

    log("🔐 Authenticating with Google Drive...")
    gauth = GoogleAuth()
    gauth.LoadServiceConfigFile(service_json_path)
    gauth.ServiceAuth()
    drive = GoogleDrive(gauth)

    log("🚀 Starting download...")
    download_folder(
        drive=drive,
        folder_id=folder_id,
        local_path=os.path.abspath(args.output_dir),
        level=0,
        max_depth=args.recursive,
        file_type=args.file_type,
        file_exts=args.file_ext
    )

    log(f"✅ Download complete. Files saved to: {os.path.abspath(args.output_dir)}")

if __name__ == '__main__':
    main()

