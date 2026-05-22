import os
import shutil
import secrets
import pickle
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from google_auth_oauthlib.flow import Flow

from meatball_uploader import process_and_upload


app = FastAPI()

UPLOAD_PASSWORD = os.getenv(
    "UPLOAD_PASSWORD",
    "meatball"
)

BASE_URL = os.getenv(
    "BASE_URL",
    "https://meatball-uploader.onrender.com"
)

CLIENT_SECRETS_FILE = "/var/data/client_secrets.json"

YOUTUBE_TOKEN_FILE = os.getenv(
    "YOUTUBE_TOKEN_FILE",
    "/var/data/youtube_token.pickle"
)

STATE_FILE = "/var/data/oauth_state.txt"

CODE_VERIFIER_FILE = "/var/data/oauth_verifier.txt"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]


def ensure_google_secret():

    if os.path.exists(
        CLIENT_SECRETS_FILE
    ):
        return

    secret = os.getenv(
        "GOOGLE_CLIENT_SECRET_JSON"
    )

    if not secret:
        raise Exception(
            "Missing GOOGLE_CLIENT_SECRET_JSON"
        )

    os.makedirs(
        "/var/data",
        exist_ok=True
    )

    with open(
        CLIENT_SECRETS_FILE,
        "w"
    ) as f:

        f.write(secret)


@app.get("/health")
def health():

    return {
        "status": "ok"
    }


@app.get(
    "/",
    response_class=HTMLResponse
)
def home():

    connected = os.path.exists(
        YOUTUBE_TOKEN_FILE
    )

    status = (
        "? Connected"
        if connected
        else
        "? Not Connected"
    )

    return f"""
<html>

<body
style="
font-family:Arial;
max-width:700px;
margin:40px auto;
">

<h1>
?? Meatball Uploader
</h1>

<p>
YouTube:
{status}
</p>

<p>

<a href="/auth/youtube">

Connect YouTube

</a>

</p>

<hr>

<form
action="/upload"
method="post"
enctype="multipart/form-data"
>

Password

<br>

<input
name="password"
type="password"
style="width:100%;padding:8px;"
>

<br><br>

Video

<br>

<input
name="video"
type="file"
accept="video/*"
>

<br><br>

<button>

Upload

</button>

</form>

</body>

</html>
"""


@app.get("/auth/youtube")
def auth_youtube():

    ensure_google_secret()

    verifier = (
        secrets.token_urlsafe(
            64
        )
    )

    flow = (
        Flow
        .from_client_secrets_file(

            CLIENT_SECRETS_FILE,

            scopes=
            SCOPES,

            redirect_uri=
            f"{BASE_URL}/oauth2callback",

            code_verifier=
            verifier
        )
    )

    auth_url, state = (
        flow.authorization_url(

            access_type=
            "offline",

            prompt=
            "consent",

            include_granted_scopes=
            "true",

            code_challenge_method=
            "S256"
        )
    )

    with open(
        STATE_FILE,
        "w"
    ) as f:

        f.write(
            state
        )

    with open(
        CODE_VERIFIER_FILE,
        "w"
    ) as f:

        f.write(
            verifier
        )

    return RedirectResponse(
        auth_url
    )


@app.get(
    "/oauth2callback",
    response_class=HTMLResponse
)
def callback(
    request: Request
):

    ensure_google_secret()

    with open(
        STATE_FILE
    ) as f:

        state = (
            f.read()
        )

    with open(
        CODE_VERIFIER_FILE
    ) as f:

        verifier = (
            f.read()
        )

    flow = (
        Flow
        .from_client_secrets_file(

            CLIENT_SECRETS_FILE,

            scopes=
            SCOPES,

            state=
            state,

            redirect_uri=
            f"{BASE_URL}/oauth2callback",

            code_verifier=
            verifier
        )
    )

    flow.fetch_token(
        authorization_response=
        str(
            request.url
        )
    )

    credentials = (
        flow.credentials
    )

    with open(
        YOUTUBE_TOKEN_FILE,
        "wb"
    ) as token:

        pickle.dump(
            credentials,
            token
        )

    return """
<html>

<body
style="
font-family:Arial;
max-width:700px;
margin:40px auto;
">

<h2>

YouTube connected ?

</h2>

<p>

Return to uploader

</p>

<a href="/">

Home

</a>

</body>

</html>
"""


@app.post(
    "/upload",
    response_class=HTMLResponse
)
def upload(
    password: str = Form(...),
    video: UploadFile = File(...)
):

    if password != UPLOAD_PASSWORD:

        return """
        Invalid password
        """

    if not os.path.exists(
        YOUTUBE_TOKEN_FILE
    ):

        return """
        Connect YouTube first
        """

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

    url = (
        process_and_upload(
            path
        )
    )

    return f"""

<html>

<body>

<h2>

Upload Complete ?

</h2>

<a
href="{url}"
target="_blank"
>

View Video

</a>

</body>

</html>

"""