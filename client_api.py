import requests
from config import config

class ClientAPI:
    def __init__(self):
        self.api_url = config['api']['api_url'].rstrip('/')
        self.api_key = config['api']['api_key']
        self.headers = {'X-API-KEY': self.api_key}

    def _post(self, url, data):
        response = requests.post(url, json=data, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def _get(self, url, params=None):
        if params:
            response = requests.get(url, headers=self.headers, params=params)
        else:
            response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def list_active_events(self, name=''):
        params = {'name': name}
        url = f"{self.api_url}/events/"
        return self._get(url, params)

    def get_event_detail(self, event_id):
        url = f"{self.api_url}/event/{event_id}/"
        return self._get(url)
    
    def get_cloud_storage_detail(self, cloud_storage_id):
        url = f"{self.api_url}/cloud_storage/{cloud_storage_id}/"
        return self._get(url)

    def list_photos(self, cloud_storage_id, fmt='compact', incomplete=False, rows=0):
        url = f"{self.api_url}/cloud_storage/{cloud_storage_id}/photos/"
        params = {'format': fmt, 'incomplete': incomplete, 'rows': rows}
        return self._get(url, params)
    
    def add_photos(self, cloud_storage_id, new_list):
        url = f"{self.api_url}/cloud_storage/{cloud_storage_id}/photos/add/"
        return self._post(url, new_list)

    def update_photos(self, cloud_storage_id, change):
        url = f"{self.api_url}/cloud_storage/{cloud_storage_id}/photos/update/"
        return self._post(url, change)
    
    def delete_photos(self, cloud_storage_id, missing):
        url = f"{self.api_url}/cloud_storage/{cloud_storage_id}/photos/delete/"
        return self._post(url, missing)

    def add_photo_result(self, photo_id, data):
        url = f"{self.api_url}/photo/{photo_id}/result/"
        return self._post(url, data)
