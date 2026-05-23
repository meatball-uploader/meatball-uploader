import os
import shutil
import uuid
import threading
import secrets
import pickle
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from google_auth_oauthlib.flow import Flow

from meatball_uploader import process_and_upload


app = FastAPI()

UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD", "meatball")
BASE_URL = os.getenv("BASE_URL", "https://meatball-uploader.onrender.com")

CLIENT_SECRETS_FILE = "/var/data/client_secrets.json"
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "/var/data/youtube_token.pickle")
STATE_FILE = "/var/data/oauth_state.txt"
CODE_VERIFIER_FILE = "/var/data/oauth_verifier.txt"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

jobs = {}


def ensure_google_secret():
    if os.path.exists(CLIENT_SECRETS_FILE):
        return

    secret = os.getenv("GOOGLE_CLIENT_SECRET_JSON")

    if not secret:
        raise Exception("Missing GOOGLE_CLIENT_SECRET_JSON")

    os.makedirs("/var/data", exist_ok=True)

    with open(CLIENT_SECRETS_FILE, "w", encoding="utf-8") as f:
        f.write(secret)


def page_shell(content):
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Meatball Uploader</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
        body {{
            margin: 0;
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #111827, #1f2937);
            color: #f9fafb;
        }}

        .wrap {{
            max-width: 760px;
            margin: 0 auto;
            padding: 36px 18px;
        }}

        .card {{
            background: rgba(17, 24, 39, 0.92);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 24px;
            padding: 28px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.35);
        }}

        h1 {{
            margin: 0 0 8px 0;
            font-size: 34px;
        }}

        .sub {{
            color: #9ca3af;
            margin-bottom: 24px;
        }}

        .status {{
            padding: 12px 14px;
            background: #0f172a;
            border-radius: 14px;
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.08);
        }}

        label {{
            display: block;
            margin-top: 18px;
            margin-bottom: 8px;
            color: #d1d5db;
            font-weight: bold;
        }}

        input {{
            width: 100%;
            box-sizing: border-box;
            padding: 13px;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.15);
            background: #111827;
            color: white;
        }}

        button, .button {{
            display: inline-block;
            margin-top: 22px;
            padding: 13px 18px;
            border-radius: 12px;
            border: none;
            background: #3b82f6;
            color: white;
            font-weight: bold;
            text-decoration: none;
            cursor: pointer;
        }}

        .button.secondary {{
            background: #374151;
        }}

        .bar {{
            height: 28px;
            background: #374151;
            border-radius: 999px;
            overflow: hidden;
            margin-top: 24px;
        }}

        .fill {{
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #3b82f6, #60a5fa);
            transition: width 0.4s ease;
        }}

        pre {{
            white-space: pre-wrap;
            background: #111827;
            padding: 16px;
            border-radius: 12px;
            color: #fecaca;
            border: 1px solid rgba(248,113,113,0.35);
        }}

        .small {{
            color: #9ca3af;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            {content}
        </div>
    </div>
</body>
</html>
"""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home():
    connected = os.path.exists(YOUTUBE_TOKEN_FILE)
    youtube_status = "Connected" if connected else "Not connected"

    content = f"""
        <h1>Meatball Uploader</h1>
        <div class="sub">Upload a video, add the Meatball logo, generate metadata, and send it to YouTube.</div>

        <div class="status">
            <strong>YouTube:</strong> {youtube_status}
            <br>
            <a class="button secondary" href="/auth/youtube">Connect YouTube Account</a>
        </div>

        <form action="/upload" method="post" enctype="multipart/form-data">
            <label>Password</label>
            <input name="password" type="password" required />

            <label>Select video</label>
            <input name="video" type="file" accept="video/*" required />

            <button type="submit">Upload and Process</button>
        </form>

        <p class="small">Uploads are processed in the background so the page does not time out.</p>
    """

    return page_shell(content)


@app.get("/auth/youtube")
def auth_youtube():
    ensure_google_secret()

    verifier = secrets.token_urlsafe(64)

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=f"{BASE_URL}/oauth2callback",
        code_verifier=verifier,
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        code_challenge_method="S256",
    )

    os.makedirs("/var/data", exist_ok=True)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(state)

    with open(CODE_VERIFIER_FILE, "w", encoding="utf-8") as f:
        f.write(verifier)

    return RedirectResponse(auth_url)


@app.get("/oauth2callback", response_class=HTMLResponse)
def oauth_callback(request: Request):
    ensure_google_secret()

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = f.read()

    with open(CODE_VERIFIER_FILE, "r", encoding="utf-8") as f:
        verifier = f.read()

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=f"{BASE_URL}/oauth2callback",
        code_verifier=verifier,
    )

    flow.fetch_token(authorization_response=str(request.url))

    credentials = flow.credentials

    os.makedirs(os.path.dirname(YOUTUBE_TOKEN_FILE), exist_ok=True)

    with open(YOUTUBE_TOKEN_FILE, "wb") as token:
        pickle.dump(credentials, token)

    content = """
        <h1>YouTube connected</h1>
        <p>Your YouTube account is now connected.</p>
        <a class="button" href="/">Back to uploader</a>
    """

    return page_shell(content)


def run_job(job_id, input_path):
    try:
        jobs[job_id]["progress"] = 15
        jobs[job_id]["status"] = "Video received. Starting processing..."

        jobs[job_id]["progress"] = 35
        jobs[job_id]["status"] = "Adding Meatball logo and preparing video..."

        youtube_url = process_and_upload(input_path)

        jobs[job_id]["progress"] = 100
        jobs[job_id]["status"] = "Complete"
        jobs[job_id]["done"] = True
        jobs[job_id]["youtube_url"] = youtube_url

    except Exception as e:
        jobs[job_id]["progress"] = 100
        jobs[job_id]["status"] = "Failed"
        jobs[job_id]["done"] = True
        jobs[job_id]["error"] = str(e)


@app.post("/upload", response_class=HTMLResponse)
def upload(password: str = Form(...), video: UploadFile = File(...)):
    if password != UPLOAD_PASSWORD:
        return page_shell("<h1>Invalid password</h1><p>Please go back and try again.</p>")

    if not os.path.exists(YOUTUBE_TOKEN_FILE):
        return page_shell("""
            <h1>YouTube not connected</h1>
            <p>Please connect your YouTube account before uploading.</p>
            <a class="button" href="/auth/youtube">Connect YouTube Account</a>
        """)

    os.makedirs("uploads", exist_ok=True)

    safe_filename = video.filename.replace(" ", "_")
    input_path = f"uploads/{uuid.uuid4()}_{safe_filename}"

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)

    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "progress": 5,
        "status": "Upload received.",
        "done": False,
        "error": None,
        "youtube_url": None,
    }

    thread = threading.Thread(target=run_job, args=(job_id, input_path))
    thread.daemon = True
    thread.start()

    content = f"""
        <h1>Processing video</h1>
        <p class="sub">Keep this page open while Meatball works his magic.</p>

        <div class="bar">
            <div id="fill" class="fill"></div>
        </div>

        <p id="status">Starting...</p>

        <script>
            async function refreshStatus() {{
                const response = await fetch("/status/{job_id}");
                const data = await response.json();

                document.getElementById("fill").style.width = data.progress + "%";
                document.getElementById("status").innerText = data.status;

                if (data.done) {{
                    if (data.error) {{
                        document.body.innerHTML = `
                            <div class="wrap">
                                <div class="card">
                                    <h1>Processing failed</h1>
                                    <p>Something went wrong.</p>
                                    <pre>${{data.error}}</pre>
                                    <a class="button" href="/">Try again</a>
                                </div>
                            </div>
                        `;
                    }} else {{
                        window.location.href = "/complete/{job_id}";
                    }}
                }}
            }}

            refreshStatus();
            setInterval(refreshStatus, 1500);
        </script>
    """

    return page_shell(content)


@app.get("/status/{job_id}")
def status(job_id: str):
    return JSONResponse(jobs.get(job_id, {
        "progress": 0,
        "status": "Job not found",
        "done": True,
        "error": "Job not found",
    }))


@app.get("/complete/{job_id}", response_class=HTMLResponse)
def complete(job_id: str):
    job = jobs.get(job_id)

    if not job:
        return page_shell("<h1>Job not found</h1><a class='button' href='/'>Back</a>")

    youtube_url = job.get("youtube_url")

    content = f"""
        <h1>Upload complete</h1>
        <p>Your video has been uploaded to YouTube.</p>
        <a class="button" href="{youtube_url}" target="_blank">Open YouTube Video</a>
        <br><br>
        <a class="button secondary" href="/">Upload another video</a>
    """

    return page_shell(content)