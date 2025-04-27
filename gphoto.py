import os
from typing import List, Dict, Optional, Tuple
from google.oauth2 import credentials
from googleapiclient.discovery import build
import requests
import shutil
from utils import compare_timestamps, extract_album_id, is_image_file

class GooglePhotos:
    def __init__(self, credentials_file: str = "gphoto_token.json", image_exts: Optional[List[str]] = None):
        self.credentials_file = credentials_file
        try:
            creds = credentials.Credentials.from_authorized_user_file(self.credentials_file, scopes=['https://www.googleapis.com/auth/photoslibrary.readonly'])
        except FileNotFoundError:
            print(f"Error: Credentials file not found at {self.credentials_file}.  You need to obtain OAuth 2.0 credentials.")
            raise  # Re-raise the exception to stop execution
        self.service = build('photoslibrary', 'v1', credentials=creds, static_discovery=False)

    def get_base_url_by_id(self, media_id):
        ret = self.service.mediaItems().get(mediaItemId=media_id).execute()
        return ret['baseUrl']

    def list_shared_album_photos(self, album_id):
        try:
            photos = []
            next_page_token = None
            while True:
                if next_page_token:
                    results = self.service.mediaItems().search(
                        body={'albumId': album_id,
                              'pageSize': 100,
                              'pageToken': next_page_token
                              }
                    ).execute()
                else:
                    results = self.service.mediaItems().search(
                        body={'albumId': album_id, 'pageSize': 100}
                    ).execute()
                items = results.get('mediaItems', [])
                if not items:
                    break  # No more photos in the album

                for item in items:
                    if not is_image_file(item.get('filename')):
                        continue
                    photo_data = {
                        'gdid': item.get('id'),  # Google Photos ID
                        'name': item.get('filename'),
                        'size': item.get('mediaMetadata.fileSize') if item.get('mediaMetadata.fileSize') else 0,
                        'created_time': item.get('mediaMetadata', {}).get('creationTime'),
                        'modified_time': item.get('mediaMetadata', {}).get('creationTime'),
                        'base_url': item.get('productUrl') 
                    }
                    photos.append(photo_data)
                next_page_token = results.get('nextPageToken')
                if not next_page_token:
                    break  # No more pages
            return photos

        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def get_media_by_id(self, mediaId):
        ret = self.service.mediaItems().get(mediaItemId=mediaId).execute()
        return ret

    def scan_photos(self, url) -> List[Dict]:
        album_id = extract_album_id(url)
        print(f'url: {url}')
        print(f"album id: {album_id}")
        if not album_id:
            return []
        return self.list_shared_album_photos(album_id)

    def download(self, id: str, file_path: str) -> Optional[str]:
        try:
            #  Get the download URL (baseUrl)
            baseUrl = self.get_base_url_by_id(id)
            download_url = baseUrl + "=d"
            print(f"URL: {download_url}")
            #  Download the file using requests
            response = requests.get(download_url, stream=True)
            response.raise_for_status()  # Raise an exception for bad status codes
            with open(file_path, 'wb') as out_file:
                shutil.copyfileobj(response.raw, out_file)
            return file_path
        except requests.exceptions.RequestException as e:
            print(f"Download failed (HTTP error): {download_url} -> {e}")
            return None
        except Exception as e:
            print(f"Download failed: {download_url} -> {e}")
            return None

    def download_list(self, gdids: List[str], target_dir: str) -> List[str]:
        downloaded = []
        for gdid in gdids:
            try:
                media_item = self.service.mediaItems().get(mediaItemId=gdid, fields='filename').execute()
                filename = media_item.get('filename') or gdid + ".jpg"  # Default to gdid.jpg if no filename
            except Exception:
                filename = gdid + ".jpg" # Default to gdid.jpg if can't get filename

            file_path = os.path.join(target_dir, filename)
            path = self.download(gdid, file_path)
            if path:
                downloaded.append(path)
        return downloaded

    def compare(self, photos_list1: List[Dict], photos_list2: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        photos_lookup = {photo['gdid']: photo for photo in photos_list2}
        only_new, changed, missing = [], [], []

        for photo in photos_list1:
            gdid = photo['gdid']
            if gdid not in photos_lookup:
                only_new.append(photo)
            else:
                other_photo = photos_lookup[gdid]
                if compare_timestamps(photo.get('modified_time'), other_photo.get('modified_time')):
                    changed.append(photo)

        photos_ids = {photo['gdid'] for photo in photos_list1}
        for photo in photos_list2:
            if photo['gdid'] not in photos_ids:
                missing.append(photo)
        return only_new, changed, missing

    def list_albums(self, shared=True):
        try:
            albums = []
            next_page_token = None
            while True:
                if shared:
                    results = self.service.sharedAlbums().list(
                        pageSize=50,
                        pageToken=next_page_token
                    ).execute()
                    items = results.get('sharedAlbums', [])
                else:
                    results = self.service.albums().list(
                        pageSize=50,
                        pageToken=next_page_token
                    ).execute()
                    items = results.get('albums', [])
                if not items:
                    break  # No more albums

                for item in items:
                    album_data = {
                        'id': item.get('id'),
                        'title': item.get('title'),
                        'totalMediaItems': item.get('totalMediaItems'),
                        'productUrl': item.get('productUrl')
                    }
                    albums.append(album_data)

                next_page_token = results.get('nextPageToken')
                if not next_page_token:
                    break  # No more pages

            return albums

        except Exception as e:
            print(f"An error occurred: {e}")
            return None
