import os
import json
import base64
import pickle
import subprocess
import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request


JOB_ID = str(uuid.uuid4())

OUTPUT_VIDEO = f"/tmp/output_{JOB_ID}.mp4"
FRAME_IMAGE = f"/tmp/frame_{JOB_ID}.jpg"
LOGO_IMAGE = "meatball.png"

PRIVACY_STATUS = "public"

YOUTUBE_TOKEN_FILE = os.getenv(
    "YOUTUBE_TOKEN_FILE",
    "/var/data/youtube_token.pickle"
)

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def friendly_service_error(error):
    text = str(error).lower()

    if "api_key" in text or "incorrect api key" in text:
        return "OpenAI API key is missing or invalid. Check OPENAI_API_KEY in Render."

    if "insufficient_quota" in text or "quota" in text or "billing" in text:
        return "OpenAI billing or quota issue. Check your OpenAI credits and usage limits."

    if "401" in text or "unauthorized" in text:
        return "Authentication failed. You may need to reconnect YouTube."

    if "403" in text and "quota" in text:
        return "YouTube upload quota was exceeded. Try again later or check your Google Cloud quota."

    if "invalid_grant" in text or "token" in text:
        return "YouTube authorization expired or is invalid. Reconnect your YouTube account."

    if "youtube" in text:
        return "YouTube upload failed. Check your YouTube connection and Google Cloud settings."

    return "A service call failed. Check the technical details below."

def report(progress_callback, percent, message):
    print(message)
    if progress_callback:
        progress_callback(percent, message)


def friendly_ffmpeg_error(stderr):
    error_text = stderr.lower()

    if "no such file or directory" in error_text:
        return "A required file was missing. Please check that the uploaded video and meatball.png exist."

    if "invalid data found" in error_text:
        return "The video file could not be read. Try exporting it as MP4 and uploading again."

    if "error while decoding" in error_text:
        return "FFmpeg had trouble decoding this video. This can happen with some iPhone MOV files."

    if "cannot allocate memory" in error_text or "out of memory" in error_text:
        return "Video processing ran out of memory. Try a shorter or smaller video."

    if "unknown encoder" in error_text:
        return "The server is missing a required video encoder."

    return "Video processing failed. Check Render logs for full FFmpeg details."


def run_ffmpeg(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        friendly_message = friendly_ffmpeg_error(result.stderr)

        raise Exception(
            f"{friendly_message}\n\nFFmpeg details:\n{result.stderr[-2000:]}"
        )

    return result


def add_logo_to_video(input_video_path):
    command = [
        "ffmpeg",
        "-y",
        "-threads", "1",
        "-i", input_video_path,
        "-i", LOGO_IMAGE,
        "-filter_complex",
        "[0:v]scale='min(720,iw)':-2[base];"
        "[1:v]scale=90:-1,format=rgba,colorchannelmixer=aa=0.55[logo];"
        "[base][logo]overlay=W-w-18:H-h-18,format=yuv420p",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "30",
        "-c:a", "aac",
        "-b:a", "96k",
        "-movflags", "+faststart",
        OUTPUT_VIDEO
    ]

    run_ffmpeg(command)


def extract_frame():
    command = [
        "ffmpeg",
        "-y",
        "-threads", "1",
        "-ss", "00:00:03",
        "-i", OUTPUT_VIDEO,
        "-frames:v", "1",
        "-q:v", "3",
        FRAME_IMAGE
    ]

    run_ffmpeg(command)


def generate_metadata(progress_callback=None):
    report(progress_callback, 55, "Extracting a frame from the video...")
    extract_frame()

    report(progress_callback, 65, "Sending video frame to AI...")

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
        metadata = {
            "title": "Meatball The Frenchie Being Adorable",
            "description": "Watch Meatball being adorable. #Frenchie #FrenchBulldog #Dogs #DogShorts"
        }

    report(progress_callback, 75, "AI title and description generated.")

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

    return build("youtube", "v3", credentials=credentials)


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

    response = request.execute()

    video_id = response["id"]
    return f"https://youtube.com/watch?v={video_id}"


def cleanup_files(input_video_path=None):
    for file_path in [OUTPUT_VIDEO, FRAME_IMAGE, input_video_path]:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass


def process_and_upload(input_video_path, progress_callback=None):
    try:
        report(progress_callback, 20, "Starting video processing...")

        report(progress_callback, 35, "Adding Meatball logo...")
        add_logo_to_video(input_video_path)

        report(progress_callback, 50, "Logo added successfully.")

        report(progress_callback, 60, "Generating title and description...")
         try:
            title, description = generate_metadata(progress_callback)
        except Exception as e:
            raise Exception(
                f"{friendly_service_error(e)}\n\nDetails:\n{str(e)}"
            )

        print("\nTITLE:")
        print(title)

        print("\nDESCRIPTION:")
        print(description)

        report(progress_callback, 85, "Uploading video to YouTube as private...")
        try:
            youtube_url = upload_video(title, description)
        except Exception as e:
            raise Exception(
                f"{friendly_service_error(e)}\n\nDetails:\n{str(e)}"
            )

        report(progress_callback, 100, "Upload complete.")

        return {
            "youtube_url": youtube_url,
            "title": title,
            "description": description
        }

    finally:
        cleanup_files(input_video_path)


if __name__ == "__main__":
    process_and_upload("input.mp4")