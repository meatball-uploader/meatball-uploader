import os
import shutil
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse

from meatball_uploader import process_and_upload

app = FastAPI()

UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD", "meatball")


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <body style="font-family: Arial; max-width: 600px; margin: 40px auto;">
            <h2>Meatball YouTube Uploader</h2>

            <form action="/upload" method="post" enctype="multipart/form-data">
                <p>Password:</p>
                <input type="password" name="password" />

                <p>Select video:</p>
                <input type="file" name="video" accept="video/*" />

                <br><br>
                <button type="submit">Upload & Process</button>
            </form>
        </body>
    </html>
    """


@app.post("/upload")
def upload_video(
    password: str = Form(...),
    video: UploadFile = File(...)
):
    if password != UPLOAD_PASSWORD:
        return {"error": "Invalid password"}

    os.makedirs("uploads", exist_ok=True)

    input_path = f"uploads/{video.filename}"

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)

    result = process_and_upload(input_path)

    return {
        "status": "complete",
        "youtube_url": result
    }