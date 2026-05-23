import os
import shutil
import uuid
import threading

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse

from meatball_uploader import process_and_upload


app = FastAPI()

UPLOAD_PASSWORD = os.getenv(
    "UPLOAD_PASSWORD",
    "meatball"
)

jobs = {}


def run_job(job_id, input_path):

    try:

        jobs[job_id] = {
            "progress": 10,
            "status": "Starting...",
            "done": False
        }

        jobs[job_id]["progress"] = 25
        jobs[job_id]["status"] = "Processing video..."

        youtube_url = process_and_upload(
            input_path
        )

        jobs[job_id]["progress"] = 100

        jobs[job_id]["status"] = "Complete"

        jobs[job_id]["done"] = True

        jobs[job_id]["youtube_url"] = youtube_url

    except Exception as e:

        jobs[job_id] = {

            "progress": 100,

            "status": "Failed",

            "done": True,

            "error": str(e)
        }


@app.get("/", response_class=HTMLResponse)
def home():

    return """
<html>

<head>

<style>

body{
font-family:Arial;
background:#111827;
color:white;
max-width:700px;
margin:40px auto;
}

.card{
background:#1f2937;
padding:30px;
border-radius:16px;
}

button{
padding:12px 18px;
background:#2563eb;
color:white;
border:none;
border-radius:8px;
}

input{
width:100%;
padding:10px;
margin-top:8px;
}

</style>

</head>

<body>

<div class="card">

<h1>
?? Meatball Uploader
</h1>

<form
action="/upload"
method="post"
enctype="multipart/form-data"
>

<p>Password</p>

<input
name="password"
type="password"
/>

<p>Video</p>

<input
name="video"
type="file"
accept="video/*"
/>

<br><br>

<button>

Upload

</button>

</form>

</div>

</body>

</html>
"""


@app.post("/upload")
def upload(
    password: str = Form(...),
    video: UploadFile = File(...)
):

    if password != UPLOAD_PASSWORD:

        return HTMLResponse(
            "<h2>Invalid password</h2>"
        )

    os.makedirs(
        "uploads",
        exist_ok=True
    )

    path = (
        f"uploads/{video.filename}"
    )

    with open(
        path,
        "wb"
    ) as buffer:

        shutil.copyfileobj(
            video.file,
            buffer
        )

    job_id = str(
        uuid.uuid4()
    )

    thread = threading.Thread(
        target=run_job,
        args=(
            job_id,
            path
        )
    )

    thread.start()

    return HTMLResponse(
f"""
<html>

<head>

<style>

body{{
font-family:Arial;
background:#111827;
color:white;
max-width:700px;
margin:40px auto;
}}

.bar{{
height:30px;
background:#374151;
border-radius:8px;
overflow:hidden;
}}

.fill{{
height:100%;
width:0%;
background:#2563eb;
transition:all .5s;
}}

</style>

</head>

<body>

<h1>

Processing...

</h1>

<div class="bar">

<div
id="fill"
class="fill"
>

</div>

</div>

<p
id="status"
>

Starting

</p>

<script>

async function refresh(){{

const r=
await fetch(
"/status/{job_id}"
)

const d=
await r.json()

document
.getElementById(
"fill"
)
.style.width=
d.progress+"%"

document
.getElementById(
"status"
)
.innerHTML=
d.status

if(d.done){{

if(d.error){{

document.body.innerHTML=
"<h1>? Error</h1><pre>"+d.error+"</pre>"

}}

else{{

window.location=
"/complete/{job_id}"

}}

}}

}}

setInterval(
refresh,
1000
)

</script>

</body>

</html>
"""
    )


@app.get("/status/{job_id}")
def status(
    job_id
):

    return jobs.get(
        job_id,
        {}
    )


@app.get(
"/complete/{job_id}",
response_class=HTMLResponse
)
def complete(
    job_id
):

    job = jobs[
        job_id
    ]

    return f"""

<html>

<body
style="
font-family:Arial;
background:#111827;
color:white;
max-width:700px;
margin:40px auto;
">

<h1>

? Upload Complete

</h1>

<a
href="{job['youtube_url']}"
target="_blank"
>

Open Video

</a>

</body>

</html>

"""