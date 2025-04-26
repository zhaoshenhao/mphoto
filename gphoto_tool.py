import os.path
import json
import argparse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from gphoto import GooglePhotos

SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']

def refresh_token():
    creds = None
    # Use absolute paths for the credentials and token files
    credentials_file = "gphoto_cred.json"  # Replace with the actual path
    token_file = "gphoto_token.json"          # Replace with the desired path

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('photoslibrary', 'v1', credentials=creds)
        print(f"Token tested.")
    except Exception as e:
        print(f"An error occurred: {e}")

def list_albums(shared: True):
    photo_api = GooglePhotos()
    print(json.dumps(photo_api.list_albums(shared),indent=2))

def main():
    parser = argparse.ArgumentParser(description="Google Photos/Drive Script")
    parser.add_argument(
        "-r", "--refresh-token",
        action="store_true",  # Stores True if the option is present
        help="Refresh the Google Photo access token"
    )
    parser.add_argument(
        "-a", "--albums",
        action="store_true",
        help="List all albums"
    )
    parser.add_argument(
        "-m", "--my-album",
        action="store_true",
        help="Only list 'my' albums (works only with -a/--albums)"
    )
    args = parser.parse_args()
    if args.refresh_token:
        refresh_token()
    if args.albums:
        list_albums(shared=not args.my_album)

if __name__ == '__main__':
    main()