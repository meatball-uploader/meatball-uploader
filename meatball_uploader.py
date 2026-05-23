import os
import json
import base64
import pickle
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request


OUTPUT_VIDEO = "output.mp4"
LOGO_IMAGE = "meatball.png"
FRAME_IMAGE = "frame.jpg"

PRIVACY_STATUS = "public"

YOUTUBE_TOKEN_FILE = os.getenv(
    "YOUTUBE_TOKEN_FILE",
    "/var/data/youtube_token.pickle"
)

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def add_logo_to_video(input_video_path):
    print("Adding logo with FFmpeg...")

    command = [
        "ffmpeg",
        "-y",
        "-i", input_video_path,
        "-i", LOGO_IMAGE,
        "-filter_complex",
        "[1:v]scale=110:-1,format=rgba,colorchannelmixer=aa=0.60[logo];[0:v][logo]overlay=W-w-20:H-h-20",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-c:a", "aac",
        "-movflags", "+faststart",
        OUTPUT_VIDEO
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise Exception(result.stderr)

    print("Logo added successfully.")


def extract_frame():
    print("Extracting frame with FFmpeg...")

    command = [
        "ffmpeg",
        "-y",
        "-i", OUTPUT_VIDEO,
        "-ss", "00:00:03",
        "-frames:v", "1",
        FRAME_IMAGE
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise Exception(result.stderr)

    print("Frame extracted successfully.")


def generate_metadata():
    extract_frame()

    image_bytes = Path(FRAME_IMAGE).read_bytes()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """
You are a viral YouTube Shorts strategist.

Review this dog video frame.

Generate metadata that attracts views.

Return ONLY valid JSON.

{
  "title": "",
  "description": ""
}

Rules:
- Catchy
- Funny
- Emotional
- Mention Frenchie
- Include hashtags
- No markdown
"""
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{image_base64}"
                    }
                ]
            }
        ]
    )

    raw = response.output_text.strip()

    print("\nAI RESPONSE:")
    print(raw)

    if raw.startswith("```json"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    elif raw.startswith("```"):
        raw = raw.replace("```", "").strip()

    try:
        metadata = json.loads(raw)
    except Exception:
        print("\nBad JSON. Using fallback metadata.")
        metadata = {
            "title": "Meatball The Frenchie Being Adorable",
            "description": "Watch Meatball being adorable. #Frenchie #FrenchBulldog #Dogs #DogShorts"
        }

    return metadata["title"], metadata["description"]


def get_youtube_service():
    if not os.path.exists(YOUTUBE_TOKEN_FILE):
        raise FileNotFoundError(
            f"YouTube token not found at {YOUTUBE_TOKEN_FILE}. "
            "Connect YouTube from the web app first."
        )

    with open(YOUTUBE_TOKEN_FILE, "rb") as token:
        credentials = pickle.load(token)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

        with open(YOUTUBE_TOKEN_FILE, "wb") as token:
            pickle.dump(credentials, token)

    if not credentials or not credentials.valid:
        raise Exception("YouTube credentials are not valid. Reconnect YouTube.")

    return build(
        "youtube",
        "v3",
        credentials=credentials
    )


def upload_video(title, description):
    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22"
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(
        OUTPUT_VIDEO,
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    print("\nUploading to YouTube...")

    response = request.execute()

    video_id = response["id"]
    youtube_url = f"https://youtube.com/watch?v={video_id}"

    print("\nDONE")
    print(youtube_url)

    return youtube_url


def process_and_upload(input_video_path):
    print("\nAdding logo...")
    add_logo_to_video(input_video_path)

    print("\nGenerating metadata...")
    title, description = generate_metadata()

    print("\nTITLE:")
    print(title)

    print("\nDESCRIPTION:")
    print(description)

    youtube_url = upload_video(title, description)

    return youtube_url


if __name__ == "__main__":
    process_and_upload("input.mp4")