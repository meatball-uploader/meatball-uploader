import os
import json
import base64
import pickle
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from moviepy import (
    VideoFileClip,
    ImageClip,
    CompositeVideoClip
)

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request


# -------------------------
# CONFIG
# -------------------------

INPUT_VIDEO = "input.mp4"
OUTPUT_VIDEO = "output.mp4"

LOGO_IMAGE = "meatball.png"
FRAME_IMAGE = "frame.jpg"

PRIVACY_STATUS = "public"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


# -------------------------
# VIDEO PROCESSING
# -------------------------

def add_logo_to_video():

    video = VideoFileClip(INPUT_VIDEO)

    logo = (
        ImageClip(LOGO_IMAGE)
        .resized(width=110)
        .with_opacity(0.60)
        .with_duration(video.duration)
        .with_position(
            (
                video.w - 130,
                video.h - 130
            )
        )
    )

    final = CompositeVideoClip([
        video,
        logo
    ])

    final.write_videofile(
        OUTPUT_VIDEO,
        codec="libx264",
        audio_codec="aac",
        fps=video.fps
    )

    video.close()
    final.close()


# -------------------------
# EXTRACT FRAME
# -------------------------

def extract_frame():

    video = VideoFileClip(OUTPUT_VIDEO)

    timestamp = min(
        3,
        video.duration / 2
    )

    video.save_frame(
        FRAME_IMAGE,
        t=timestamp
    )

    video.close()


# -------------------------
# OPENAI METADATA
# -------------------------

def generate_metadata():

    extract_frame()

    image_bytes = Path(
        FRAME_IMAGE
    ).read_bytes()

    image_base64 = (
        base64.b64encode(
            image_bytes
        )
        .decode("utf-8")
    )

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
"title":"",
"description":""
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

                        "image_url":
                        f"data:image/jpeg;base64,{image_base64}"
                    }

                ]
            }

        ]
    )

    raw = response.output_text.strip()

    print("\nAI RESPONSE:")
    print(raw)

    if raw.startswith("```json"):

        raw = (
            raw
            .replace(
                "```json",
                ""
            )
            .replace(
                "```",
                ""
            )
            .strip()
        )

    elif raw.startswith("```"):

        raw = (
            raw
            .replace(
                "```",
                ""
            )
            .strip()
        )

    try:

        metadata = json.loads(raw)

    except:

        print(
            "\nBad JSON. Using fallback."
        )

        metadata = {

            "title":
            "Meatball The Frenchie Being Adorable",

            "description":
            """
Watch Meatball being adorable.

#Frenchie
#FrenchBulldog
#Dogs
"""
        }

    return (
        metadata["title"],
        metadata["description"]
    )


# -------------------------
# YOUTUBE AUTH
# -------------------------

def get_youtube_service():

    credentials = None

    if os.path.exists(
        "youtube_token.pickle"
    ):

        with open(
            "youtube_token.pickle",
            "rb"
        ) as token:

            credentials = pickle.load(
                token
            )

    if (
        not credentials
        or
        not credentials.valid
    ):

        if (
            credentials
            and
            credentials.expired
            and
            credentials.refresh_token
        ):

            credentials.refresh(
                Request()
            )

        else:

            flow = (
                InstalledAppFlow
                .from_client_secrets_file(
                    "client_secrets.json",
                    SCOPES
                )
            )

            credentials = (
                flow.run_local_server(
                    port=0
                )
            )

        with open(
            "youtube_token.pickle",
            "wb"
        ) as token:

            pickle.dump(
                credentials,
                token
            )

    return build(
        "youtube",
        "v3",
        credentials=credentials
    )


# -------------------------
# UPLOAD
# -------------------------

def upload_video(
    title,
    description
):

    youtube = (
        get_youtube_service()
    )

    body = {

        "snippet": {

            "title":
            title,

            "description":
            description,

            "categoryId":
            "22"

        },

        "status": {

            "privacyStatus":
            PRIVACY_STATUS,

            "selfDeclaredMadeForKids":
            False

        }

    }

    media = (
        MediaFileUpload(
            OUTPUT_VIDEO,
            resumable=True
        )
    )

    request = (
        youtube
        .videos()
        .insert(

            part=
            "snippet,status",

            body=
            body,

            media_body=
            media
        )
    )

    print(
        "\nUploading..."
    )

    response = (
        request.execute()
    )

    video_id = (
        response["id"]
    )

    print(
        "\nDONE"
    )

    print(
        f"https://youtube.com/watch?v={video_id}"
    )


# -------------------------
# MAIN
# -------------------------

if __name__ == "__main__":

    print(
        "\nAdding logo..."
    )

    add_logo_to_video()

    print(
        "\nGenerating metadata..."
    )

    title, description = (
        generate_metadata()
    )

    print(
        "\nTITLE:"
    )

    print(
        title
    )

    print(
        "\nDESCRIPTION:"
    )

    print(
        description
    )

    upload_video(
        title,
        description
    )