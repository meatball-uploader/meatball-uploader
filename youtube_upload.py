import os
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

VIDEO_FILE = "output.mp4"

TITLE = "Meatballs with souls"
DESCRIPTION = "Mashup of funny French Bulldog videos"
PRIVACY_STATUS = "public"  # private, unlisted, or public


def get_youtube_service():
    credentials = None

    if os.path.exists("youtube_token.pickle"):
        with open("youtube_token.pickle", "rb") as token:
            credentials = pickle.load(token)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secrets.json",
                SCOPES
            )
            credentials = flow.run_local_server(port=0)

        with open("youtube_token.pickle", "wb") as token:
            pickle.dump(credentials, token)

    return build("youtube", "v3", credentials=credentials)


def upload_video():
    youtube = get_youtube_service()

    request_body = {
        "snippet": {
            "title": TITLE,
            "description": DESCRIPTION,
            "categoryId": "22"
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False
        }
    }

    media_file = MediaFileUpload(
        VIDEO_FILE,
        chunksize=-1,
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media_file
    )

    print("Uploading video...")
    response = request.execute()

    video_id = response.get("id")
    print("Upload complete!")
    print(f"YouTube video ID: {video_id}")
    print(f"https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    upload_video()