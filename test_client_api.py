from client_api import ClientAPI
import json

api = ClientAPI()

# List events
events = api.list_active_events(name='91Camp')
print(json.dumps(events, indent=4))

# Get details of the first event
if events:
    event_id = events[0]['id']
    detail = api.get_event_detail(event_id)
    print(json.dumps(detail, indent=4))

    # List photos under first cloud storage
    if detail['cloudstorage']:
        cloud_id = detail['cloudstorage'][0]['id']
        photos = api.list_photos(cloud_id)
        print("Photos:", photos[:3])
