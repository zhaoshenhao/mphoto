import argparse
import json
from client_api import ClientAPI
from core import refresh, scan

client = ClientAPI()

def main():
    parser = argparse.ArgumentParser(description="Event Photo CLI Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list-events
    parser_list = subparsers.add_parser("list-events", help="List events with optional name filter")
    parser_list.add_argument("-n", "--name", default="", help="Event name filter")

    # get-event
    parser_get = subparsers.add_parser("get-event", help="Get details of a specific event")
    parser_get.add_argument("-i", "--event-id", required=True, type=int, help="Event ID")

    # get-cloud-storage
    parser_get = subparsers.add_parser("get-cloud-storage", help="Get details of a specific cloud storage")
    parser_get.add_argument("-c", "--cloud_storage_id", required=True, type=int, help="Cloud Storage ID")

    # list-photos
    parser_list_photos = subparsers.add_parser("list-photos", help="List photos in a cloud storage")
    parser_list_photos.add_argument("-c", "--cloud_storage_id", required=True, type=int, help="Cloud Storage ID")
    parser_list_photos.add_argument("-r", "--rows", required=False, default=0, type=int, help="Return number of row")
    parser_list_photos.add_argument("-i", "--incomplete", required=False, action='store_true', help="Return incomplet photos only")

    # refresh
    parser_refresh = subparsers.add_parser("refresh", help="Refresh cloud storage metadata")
    parser_refresh.add_argument("-c", "--cloud_storage_id", required=True, type=int, help="Cloud Storage ID")

    # scan
    parser_scan = subparsers.add_parser("scan", help="Scan cloud storage for new images")
    parser_scan.add_argument("-c", "--cloud_storage_id", required=True, type=int, help="Cloud Storage ID")

    args = parser.parse_args()

    # Dispatch commands
    if args.command == "list-events":
        print(json.dumps(client.list_active_events(args.name), indent=2))
    elif args.command == "get-event":
        print(json.dumps(client.get_event_detail(args.event_id), indent=2))
    elif args.command == "get-cloud-storage":
        print(json.dumps(client.get_cloud_storage_detail(args.cloud_storage_id), indent=2))
    elif args.command == "list-photos":
        print(json.dumps(client.list_photos(args.cloud_storage_id, incomplete=args.incomplete, rows=args.rows), indent=2))
    elif args.command == "refresh":
        refresh(args.cloud_storage_id)
    elif args.command == "scan":
        scan(args.cloud_storage_id)

if __name__ == "__main__":
    main()
