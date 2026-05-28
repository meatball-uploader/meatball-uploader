import os
import json
import shutil
import uuid
import threading
import secrets
import pickle
import html
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from google_auth_oauthlib.flow import Flow

from meatball_uploader import prepare_video_and_metadata, publish_prepared_video


app = FastAPI()

UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD", "meatball")
BASE_URL = os.getenv("BASE_URL", "https://meatball-uploader.onrender.com")

DATA_DIR = "/var/data"
JOBS_DIR = f"{DATA_DIR}/jobs"

CLIENT_SECRETS_FILE = f"{DATA_DIR}/client_secrets.json"
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", f"{DATA_DIR}/youtube_token.pickle")
STATE_FILE = f"{DATA_DIR}/oauth_state.txt"
CODE_VERIFIER_FILE = f"{DATA_DIR}/oauth_verifier.txt"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

MAX_UPLOAD_SIZE_MB = 100
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = [".mp4", ".mov", ".m4v"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def duration_seconds(started_at, completed_at):
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(completed_at)
        return round((end - start).total_seconds(), 2)
    except Exception:
        return None


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(JOBS_DIR, exist_ok=True)
    os.makedirs("uploads", exist_ok=True)


def job_file(job_id):
    return f"{JOBS_DIR}/{job_id}.json"


def write_job(job_id, data):
    ensure_dirs()
    with open(job_file(job_id), "w", encoding="utf-8") as f:
        json.dump(data, f)


def read_job(job_id):
    path = job_file(job_id)

    if not os.path.exists(path):
        return {
            "progress": 100,
            "status": "Job not found.",
            "done": True,
            "error": "Job not found.",
            "youtube_url": None,
            "title": None,
            "description": None,
        }

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_job(job_id, **kwargs):
    data = read_job(job_id)
    data.update(kwargs)
    write_job(job_id, data)


def ensure_google_secret():
    ensure_dirs()

    if os.path.exists(CLIENT_SECRETS_FILE):
        return

    secret = os.getenv("GOOGLE_CLIENT_SECRET_JSON")

    if not secret:
        raise Exception("Missing GOOGLE_CLIENT_SECRET_JSON")

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
            max-width: 860px;
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
        h3 {{
            margin-top: 26px;
        }}
        .sub {{
            color: #9ca3af;
            margin-bottom: 24px;
        }}
        .status, .metadata-box {{
            white-space: pre-wrap;
            background: #0f172a;
            padding: 16px;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.10);
            color: #e5e7eb;
            margin-bottom: 16px;
        }}
        label {{
            display: block;
            margin-top: 18px;
            margin-bottom: 8px;
            color: #d1d5db;
            font-weight: bold;
        }}
        input, textarea {{
            width: 100%;
            box-sizing: border-box;
            padding: 13px;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.15);
            background: #111827;
            color: white;
        }}
        textarea {{
            min-height: 160px;
        }}
        button, .button {{
            display: inline-block;
            margin-top: 14px;
            margin-right: 8px;
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
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            border-bottom: 1px solid rgba(255,255,255,0.12);
            padding: 12px 8px;
            vertical-align: top;
        }}
        a {{
            color: #93c5fd;
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
    ensure_dirs()

    connected = os.path.exists(YOUTUBE_TOKEN_FILE)
    youtube_status = "Connected" if connected else "Not connected"

    content = f"""
        <h1>Meatball Uploader</h1>
        <div class="sub">Upload a video, add the Meatball logo, generate metadata, preview it, then publish to YouTube.</div>

        <div class="status">
            <strong>YouTube:</strong> {youtube_status}<br>
            <a class="button secondary" href="/auth/youtube">Connect YouTube Account</a>
            <a class="button secondary" href="/disconnect/youtube">Reconnect YouTube</a>
            <a class="button secondary" href="/history">View Job History</a>
        </div>

        <form action="/upload" method="post" enctype="multipart/form-data">
            <label>Password</label>
            <input name="password" type="password" required />

            <label>Select video</label>
            <input name="video" type="file" accept="video/*" required />

            <button type="submit">Upload and Prepare Preview</button>
        </form>

        <p class="small">Allowed files: {", ".join(ALLOWED_EXTENSIONS)}. Max size: {MAX_UPLOAD_SIZE_MB} MB.</p>
    """

    return page_shell(content)


@app.get("/disconnect/youtube")
def disconnect_youtube():
    try:
        if os.path.exists(YOUTUBE_TOKEN_FILE):
            os.remove(YOUTUBE_TOKEN_FILE)
    except Exception:
        pass

    return RedirectResponse("/")


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

    with open(YOUTUBE_TOKEN_FILE, "wb") as token:
        pickle.dump(credentials, token)

    return page_shell("""
        <h1>YouTube connected</h1>
        <p>Your YouTube account is now connected.</p>
        <a class="button" href="/">Back to uploader</a>
    """)


def run_prepare_job(job_id, input_path):
    try:
        update_job(
            job_id,
            progress=10,
            status="Video received. Starting preview preparation...",
            started_at=now_iso(),
        )

        def progress_callback(percent, message):
            update_job(job_id, progress=percent, status=message)

        result = prepare_video_and_metadata(
            input_path,
            progress_callback=progress_callback,
        )

        completed_at = now_iso()
        job = read_job(job_id)
        duration = duration_seconds(job.get("started_at"), completed_at)

        update_job(
            job_id,
            progress=80,
            status="Preview ready.",
            done=True,
            preview_ready=True,
            processed_video_path=result.get("processed_video_path"),
            title=result.get("title"),
            description=result.get("description"),
            completed_at=completed_at,
            duration_seconds=duration,
        )

    except Exception as e:
        completed_at = now_iso()
        job = read_job(job_id)
        duration = duration_seconds(job.get("started_at"), completed_at)

        update_job(
            job_id,
            progress=100,
            status="Failed",
            done=True,
            error=str(e),
            completed_at=completed_at,
            duration_seconds=duration,
        )


def run_publish_job(job_id, title, description):
    try:
        update_job(
            job_id,
            progress=85,
            status="Publishing to YouTube as private...",
            done=False,
            error=None,
        )

        def progress_callback(percent, message):
            update_job(job_id, progress=percent, status=message)

        youtube_url = publish_prepared_video(
            title,
            description,
            progress_callback=progress_callback,
        )

        completed_at = now_iso()
        job = read_job(job_id)
        duration = duration_seconds(job.get("started_at"), completed_at)

        update_job(
            job_id,
            progress=100,
            status="Complete",
            done=True,
            published=True,
            youtube_url=youtube_url,
            title=title,
            description=description,
            completed_at=completed_at,
            duration_seconds=duration,
        )

    except Exception as e:
        completed_at = now_iso()
        job = read_job(job_id)
        duration = duration_seconds(job.get("started_at"), completed_at)

        update_job(
            job_id,
            progress=100,
            status="Publish failed",
            done=True,
            error=str(e),
            completed_at=completed_at,
            duration_seconds=duration,
        )


@app.post("/upload", response_class=HTMLResponse)
def upload(password: str = Form(...), video: UploadFile = File(...)):
    ensure_dirs()

    if password != UPLOAD_PASSWORD:
        return page_shell("<h1>Invalid password</h1><p>Please go back and try again.</p>")

    if not os.path.exists(YOUTUBE_TOKEN_FILE):
        return page_shell("""
            <h1>YouTube not connected</h1>
            <p>Please connect your YouTube account before uploading.</p>
            <a class="button" href="/auth/youtube">Connect YouTube Account</a>
        """)

    file_ext = os.path.splitext(video.filename)[1].lower()

    if file_ext not in ALLOWED_EXTENSIONS:
        return page_shell(f"""
            <h1>Unsupported file type</h1>
            <p>Please upload one of these file types:</p>
            <pre>{", ".join(ALLOWED_EXTENSIONS)}</pre>
            <a class="button" href="/">Back to uploader</a>
        """)

    video.file.seek(0, os.SEEK_END)
    file_size = video.file.tell()
    video.file.seek(0)

    if file_size > MAX_UPLOAD_SIZE_BYTES:
        size_mb = round(file_size / 1024 / 1024, 2)

        return page_shell(f"""
            <h1>Video is too large</h1>
            <p>Your file is {size_mb} MB.</p>
            <p>Maximum allowed size is {MAX_UPLOAD_SIZE_MB} MB.</p>
            <a class="button" href="/">Back to uploader</a>
        """)

    safe_filename = video.filename.replace(" ", "_")
    input_path = f"uploads/{uuid.uuid4()}_{safe_filename}"
    created_at = now_iso()

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)

    job_id = str(uuid.uuid4())

    write_job(job_id, {
        "progress": 5,
        "status": "Upload received.",
        "done": False,
        "error": None,
        "youtube_url": None,
        "title": None,
        "description": None,
        "input_filename": video.filename,
        "created_at": created_at,
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "preview_ready": False,
        "published": False,
        "processed_video_path": None,
    })

    thread = threading.Thread(target=run_prepare_job, args=(job_id, input_path))
    thread.daemon = True
    thread.start()

    content = f"""
        <h1>Preparing preview</h1>
        <p class="sub">Keep this page open while Meatball prepares your video and metadata.</p>

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
                        window.location.href = "/preview/{job_id}";
                    }}
                }}
            }}

            refreshStatus();
            setInterval(refreshStatus, 1500);
        </script>
    """

    return page_shell(content)


@app.get("/preview/{job_id}", response_class=HTMLResponse)
def preview(job_id: str):
    job = read_job(job_id)

    if job.get("error"):
        return page_shell(f"""
            <h1>Processing failed</h1>
            <pre>{html.escape(job.get("error", ""))}</pre>
            <a class="button" href="/">Try again</a>
        """)

    title = html.escape(job.get("title") or "")
    description = html.escape(job.get("description") or "")

    return page_shell(f"""
        <h1>Preview before publish</h1>
        <p class="sub">Review and edit the title or description before uploading to YouTube.</p>

        <form action="/publish/{job_id}" method="post">
            <label>Title</label>
            <input name="title" value="{title}" required />

            <label>Description</label>
            <textarea name="description" required>{description}</textarea>

            <button type="submit">Publish to YouTube as Private</button>
            <a class="button secondary" href="/">Cancel</a>
        </form>
    """)


@app.post("/publish/{job_id}", response_class=HTMLResponse)
def publish(job_id: str, title: str = Form(...), description: str = Form(...)):
    job = read_job(job_id)

    if not job.get("preview_ready"):
        return page_shell("""
            <h1>Preview not ready</h1>
            <p>This job is not ready to publish yet.</p>
            <a class="button" href="/history">Back to history</a>
        """)

    thread = threading.Thread(target=run_publish_job, args=(job_id, title, description))
    thread.daemon = True
    thread.start()

    content = f"""
        <h1>Publishing to YouTube</h1>
        <p class="sub">Uploading your reviewed video as private.</p>

        <div class="bar">
            <div id="fill" class="fill"></div>
        </div>

        <p id="status">Publishing...</p>

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
                                    <h1>Publishing failed</h1>
                                    <pre>${{data.error}}</pre>
                                    <a class="button" href="/preview/{job_id}">Back to preview</a>
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
    return JSONResponse(read_job(job_id))


@app.get("/history", response_class=HTMLResponse)
def history():
    ensure_dirs()

    rows = []

    for file_name in sorted(os.listdir(JOBS_DIR), reverse=True):
        if not file_name.endswith(".json"):
            continue

        job_id = file_name.replace(".json", "")
        job = read_job(job_id)

        status = job.get("status", "")
        progress = job.get("progress", 0)
        error = job.get("error")
        youtube_url = job.get("youtube_url")
        title = job.get("title") or ""
        duration = job.get("duration_seconds")
        duration_text = f"{duration}s" if duration is not None else "-"

        if error:
            result = f"<span style='color:#fca5a5;'>Failed</span><br><small>{html.escape(error)}</small>"
        elif youtube_url:
            result = f"<a href='{youtube_url}' target='_blank'>Open video</a>"
        elif job.get("preview_ready"):
            result = f"<a href='/preview/{job_id}'>Preview</a>"
        else:
            result = "In progress"

        rows.append(f"""
            <tr>
                <td><a href="/job/{job_id}">{job_id[:8]}</a></td>
                <td>{progress}%</td>
                <td>{duration_text}</td>
                <td>{html.escape(status)}<br><small>{html.escape(title)}</small></td>
                <td>{result}</td>
            </tr>
        """)

    table_rows = "\n".join(rows) if rows else """
        <tr>
            <td colspan="5">No jobs yet.</td>
        </tr>
    """

    return page_shell(f"""
        <h1>Job History</h1>
        <p class="sub">Recent uploads and processing results.</p>

        <table>
            <tr>
                <th align="left">Job</th>
                <th align="left">Progress</th>
                <th align="left">Duration</th>
                <th align="left">Status</th>
                <th align="left">Result</th>
            </tr>
            {table_rows}
        </table>

        <br>
        <a class="button secondary" href="/">Back to uploader</a>
    """)


@app.get("/complete/{job_id}", response_class=HTMLResponse)
def complete(job_id: str):
    job = read_job(job_id)

    if job.get("error"):
        return page_shell(f"""
            <h1>Processing failed</h1>
            <p>Something went wrong.</p>
            <pre>{html.escape(job.get("error"))}</pre>
            <a class="button" href="/">Try again</a>
        """)

    youtube_url = job.get("youtube_url")
    title = html.escape(job.get("title") or "No title saved.")
    description = html.escape(job.get("description") or "No description saved.")
    duration = job.get("duration_seconds")
    duration_text = f"{duration}s" if duration is not None else "-"

    content = f"""
        <h1>Upload complete</h1>
        <p>Your video has been uploaded to YouTube.</p>

        <div class="status">
            <strong>Duration:</strong> {duration_text}<br>
            <strong>Completed:</strong> {job.get("completed_at")}
        </div>

        <h3>Published Title</h3>
        <div class="metadata-box">{title}</div>

        <h3>Published Description</h3>
        <div class="metadata-box">{description}</div>

        <a class="button" href="{youtube_url}" target="_blank">Open YouTube Video</a>
        <br><br>
        <a class="button secondary" href="/">Upload another video</a>
        <a class="button secondary" href="/history">View Job History</a>
    """

    return page_shell(content)


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_detail(job_id: str):
    job = read_job(job_id)

    youtube_url = job.get("youtube_url")
    error = job.get("error")
    title = html.escape(job.get("title") or "No title saved.")
    description = html.escape(job.get("description") or "No description saved.")

    youtube_section = (
        f'<a class="button" href="{youtube_url}" target="_blank">Open YouTube Video</a>'
        if youtube_url
        else ""
    )

    preview_section = (
        f'<a class="button" href="/preview/{job_id}">Open Preview</a>'
        if job.get("preview_ready") and not youtube_url
        else ""
    )

    error_section = (
        f"<h3>Error</h3><pre>{html.escape(error)}</pre>"
        if error
        else ""
    )

    details = html.escape(json.dumps(job, indent=2))

    return page_shell(f"""
        <h1>Job Details</h1>

        <div class="status">
            <strong>Status:</strong> {html.escape(str(job.get("status")))}<br>
            <strong>Progress:</strong> {job.get("progress")}%<br>
            <strong>Input File:</strong> {html.escape(str(job.get("input_filename")))}<br>
            <strong>Created:</strong> {job.get("created_at")}<br>
            <strong>Started:</strong> {job.get("started_at")}<br>
            <strong>Completed:</strong> {job.get("completed_at")}<br>
            <strong>Duration:</strong> {job.get("duration_seconds")}s
        </div>

        <h3>Title</h3>
        <div class="metadata-box">{title}</div>

        <h3>Description</h3>
        <div class="metadata-box">{description}</div>

        {preview_section}
        {youtube_section}

        {error_section}

        <h3>Raw Job Data</h3>
        <pre>{details}</pre>

        <a class="button secondary" href="/history">Back to history</a>
        <a class="button secondary" href="/">Back to uploader</a>
    """)