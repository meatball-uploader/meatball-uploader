import os
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from google_auth_oauthlib.flow import Flow

from meatball_uploader import process_and_upload


app = FastAPI()

UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD", "meatball")

BASE_URL = os.getenv("BASE_URL", "https://meatball-uploader.onrender.com")
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE", "client_secrets.json")
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "/var/data/youtube_token.pickle")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home():
    youtube_connected = Path(YOUTUBE_TOKEN_FILE).exists()

    youtube_status = (
        "? YouTube connected"
        if youtube_connected
        else "? YouTube not connected"
    )

    return f"""
    <html>
        <body style="font-family: Arial; max-width: 650px; margin: 40px auto;">
            <h2>Meatball YouTube Uploader</h2>

            <p><strong>Status:</strong> {youtube_status}</p>

            <p>
                <a href="/auth/youtube">
                    Connect YouTube Account
                </a>
            </p>

            <hr>

            <form action="/upload" method="post" enctype="multipart/form-data">
                <p>Password:</p>
                <input type="password" name="password" style="width: 100%; padding: 8px;" />

                <p>Select video:</p>
                <input type="file" name="video" accept="video/*" />

                <br><br>
                <button type="submit" style="padding: 10px 16px;">
                    Upload & Process
                </button>
            </form>
        </body>
    </html>
    """


@app.get("/auth/youtube")
def auth_youtube():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=f"{BASE_URL}/oauth2callback"
    )

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )

    os.makedirs("/var/data", exist_ok=True)

    with open("/var/data/oauth_state.txt", "w") as f:
        f.write(state)

    return RedirectResponse(authorization_url)


@app.get("/oauth2callback")
def oauth2callback(request: Request):
    state_file = "/var/data/oauth_state.txt"

    if not os.path.exists(state_file):
        return HTMLResponse("Missing OAuth state. Please try connecting YouTube again.")

    with open(state_file, "r") as f:
        state = f.read()

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=f"{BASE_URL}/oauth2callback"
    )

    flow.fetch_token(authorization_response=str(request.url))

    credentials = flow.credentials

    os.makedirs(os.path.dirname(YOUTUBE_TOKEN_FILE), exist_ok=True)

    import pickle
    with open(YOUTUBE_TOKEN_FILE, "wb") as token:
        pickle.dump(credentials, token)

    return HTMLResponse("""
    <html>
        <body style="font-family: Arial; max-width: 600px; margin: 40px auto;">
            <h2>YouTube connected ?</h2>
            <p>You can now return to the uploader.</p>
            <p><a href="/">Back to uploader</a></p>
        </body>
    </html>
    """)


@app.post("/upload", response_class=HTMLResponse)
def upload_video(
    password: str = Form(...),
    video: UploadFile = File(...)
):
    if password != UPLOAD_PASSWORD:
        return HTMLResponse("<h3>Invalid password</h3>")

    if not Path(YOUTUBE_TOKEN_FILE).exists():
        return HTMLResponse("""
        <h3>YouTube is not connected yet.</h3>
        <p><a href="/auth/youtube">Connect YouTube Account</a></p>
        """)

    os.makedirs("uploads", exist_ok=True)

    safe_filename = video.filename.replace(" ", "_")
    input_path = f"uploads/{safe_filename}"

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)

    youtube_url = process_and_upload(input_path)

    return HTMLResponse(f"""
    <html>
        <body style="font-family: Arial; max-width: 600px; margin: 40px auto;">
            <h2>Upload complete ?</h2>
            <p>Your video was uploaded to YouTube.</p>
            <p><a href="{youtube_url}" target="_blank">{youtube_url}</a></p>
            <p><a href="/">Upload another video</a></p>
        </body>
    </html>
    """)