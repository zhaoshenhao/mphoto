import os
import io
import re
import urllib.parse
from typing import List, Dict, Optional, Tuple
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from tqdm import tqdm
from datetime import datetime

class GoogleDrive:
    def __init__(self, service_account_path: str = "gdrive_svc_account.json", image_exts: Optional[List[str]] = None):
        self.service_account_path = service_account_path
        self.image_exts = image_exts or ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', 'heic']
        self.image_exts = set([ext.lower() for ext in self.image_exts])

        creds = service_account.Credentials.from_service_account_file(
            self.service_account_path,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        self.service = build('drive', 'v3', credentials=creds)

    def _extract_folder_id(self, url: str) -> Optional[str]:
        match = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        return query.get('id', [None])[0]

    def _extract_file_id_from_link(self, link: str) -> Optional[str]:
        parsed = urllib.parse.urlparse(link)
        if 'drive.google.com' not in link:
            return None
        match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', link)
        if match:
            return match.group(1)
        query = urllib.parse.parse_qs(parsed.query)
        return query.get('id', [None])[0]

    def _is_image_file(self, name: str) -> bool:
        return any(name.lower().endswith(ext) for ext in self.image_exts)

    def _scan_folder(self, folder_id: str, recursive: bool = False) -> List[Dict]:
        results = []
        query = f"'{folder_id}' in parents and trashed = false"
        page_token = None

        while True:
            response = self.service.files().list(
                q=query,
                spaces='drive',
                fields=(
                    'nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, '
                    'thumbnailLink, webViewLink, webContentLink)'
                ),
                pageToken=page_token
            ).execute()

            for f in response.get('files', []):
                if f['mimeType'] == 'application/vnd.google-apps.folder' and recursive:
                    results += self._scan_folder(f['id'], recursive=True)
                elif self._is_image_file(f['name']):
                    results.append({
                        'gdid': f['id'],
                        'name': f['name'],
                        'size': int(f.get('size', 0)),
                        'created_time': f.get('createdTime'),
                        'modified_time': f.get('modifiedTime'),
                        'thumb_link': f.get('thumbnailLink'),
                        'web_content_link': f.get('webContentLink'),
                    })

            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return results

    def scan_folder(self, folder_url: str, recursive: bool = False) -> List[Dict]:
        folder_id = self._extract_folder_id(folder_url)
        if not folder_id:
            raise ValueError("Can't extract folder ID from share link")
        return self._scan_folder(folder_id, recursive)

    def download(self, gdid: str, file_path: str) -> Optional[str]:
        try:
            file_metadata = self.service.files().get(fileId=gdid, fields='name').execute()
            file_name = file_metadata['name']
            request = self.service.files().get_media(fileId=gdid)
            with io.FileIO(file_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            return file_path
        except Exception as e:
            print(f"Download failed：{gdid} -> {e}")
            return None

    def download_list(self, gdids: List[str], target_dir: str) -> List[str]:
        downloaded = []
        for gdid in tqdm(gdids, desc="Downloading"):
            path = self.download_by_share_link(gdid, target_dir)
            if path:
                downloaded.append(path)
        return downloaded

    def compare(self, drive_file_list: List[Dict], other_file_list: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        other_lookup = {f['gdid']: f for f in other_file_list}
        only_new, changed, missing = [], [], []
        for f in drive_file_list:
            gdid = f['gdid']
            if gdid not in other_lookup:
                only_new.append(f)
            else:
                other = other_lookup[gdid]
                if f['size'] != other.get('size') or compare_timestamps(f['modified_time'], other.get('modified_time')) !=0:
                    changed.append(f)
        drive_gdids = {f['gdid'] for f in drive_file_list}
        for f in other_file_list:
            if f['gdid'] not in drive_gdids:
                missing.append(f)
        return only_new, changed, missing

def compare_timestamps(timestamp1: str, timestamp2: str) -> int:
    # Parse timestamps to datetime objects
    dt1 = datetime.fromisoformat(timestamp1.replace('Z', '+00:00'))
    dt2 = datetime.fromisoformat(timestamp2.replace('Z', '+00:00'))
    
    if dt1 < dt2:
        return -1
    elif dt1 > dt2:
        return 1
    else:
        return 0