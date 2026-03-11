"""
4-upload.py
Uploads a processed episode to Transistor.fm via their API.

Three-step Transistor upload process:
  1. POST /v1/episodes — create draft, receive authorized S3 upload URL
  2. PUT {s3_url}      — stream audio file directly to S3
  3. PATCH /v1/episodes/{id} — set metadata and publish time
"""

import json
import os
import io
import tempfile
import requests
from google import genai
from google.genai import types as genai_types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
TOKEN_FILE = BASE_DIR / "token.json"
AUDIO_DIR = BASE_DIR / "data" / "audio"

TRANSISTOR_API_KEY = os.getenv("TRANSISTOR_API_KEY")
TRANSISTOR_SHOW_ID = os.getenv("TRANSISTOR_SHOW_ID")
TRANSISTOR_BASE = "https://api.transistor.fm/v1"

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Eastern timezone offset
EASTERN = timezone(timedelta(hours=-5))  # EST (adjust to -4 for EDT)

GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [UPLOAD] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Google Drive ──────────────────────────────────────────────────────────────
def get_drive_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), DRIVE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def download_from_drive(drive_file_id: str) -> bytes:
    """Download audio file from Google Drive into memory."""
    log(f"Downloading audio from Drive: {drive_file_id}")
    service = get_drive_service()
    request = service.files().get_media(fileId=drive_file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    log(f"  Downloaded {len(buffer.getvalue()) // 1024}KB from Drive")
    return buffer.getvalue()


# ── Transistor API ────────────────────────────────────────────────────────────
def transistor_headers() -> dict:
    return {
        "x-api-key": TRANSISTOR_API_KEY,
        "Content-Type": "application/json",
    }


def authorize_upload(filename: str) -> tuple[str, str, str]:
    """
    Step 1: Get a presigned S3 upload URL from Transistor.
    Returns (upload_url, content_type, audio_url).
    """
    log(f"Getting upload authorization from Transistor...")
    resp = requests.get(
        f"{TRANSISTOR_BASE}/episodes/authorize_upload",
        headers=transistor_headers(),
        params={"filename": filename},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()["data"]["attributes"]
    return data["upload_url"], data["content_type"], data["audio_url"]


def upload_audio_to_s3(upload_url: str, content_type: str, audio_bytes: bytes):
    """Step 2: PUT audio bytes directly to the presigned S3 URL."""
    log(f"Uploading audio to S3 ({len(audio_bytes) // 1024}KB)...")
    resp = requests.put(
        upload_url,
        data=audio_bytes,
        headers={"Content-Type": content_type},
        timeout=300,
    )
    resp.raise_for_status()
    log("  Audio uploaded to S3 successfully")


def create_and_publish_episode(
    audio_url: str,
    title: str,
    description: str,
    tags: str,
    publish_at: datetime,
    transcript: str | None = None,
) -> dict:
    """Step 3: Create draft, attach transcript, then schedule via PATCH /publish."""
    log(f"Creating episode on Transistor: {title[:60]}")

    # Create draft episode
    resp = requests.post(
        f"{TRANSISTOR_BASE}/episodes",
        headers=transistor_headers(),
        json={
            "episode": {
                "show_id": TRANSISTOR_SHOW_ID,
                "title": title,
                "description": description,
                "keywords": tags,
                "audio_url": audio_url,
            }
        },
        timeout=30,
    )
    resp.raise_for_status()
    episode_id = resp.json()["data"]["id"]
    log(f"  Draft created — ID: {episode_id}")

    # If transcript, attach it via a separate PATCH to /episodes/{id} first
    if transcript:
        log(f"  Attaching transcript ({len(transcript)} chars)...")
        transcript_resp = requests.patch(
            f"{TRANSISTOR_BASE}/episodes/{episode_id}",
            headers=transistor_headers(),
            json={"episode": {"transcript_text": transcript}},
            timeout=60,
        )
        if transcript_resp.ok:
            log("  Transcript attached")
        else:
            log(f"  Transcript attach failed ({transcript_resp.status_code}) — continuing without it")

    # Schedule the episode via publish endpoint
    patch_resp = requests.patch(
        f"{TRANSISTOR_BASE}/episodes/{episode_id}/publish",
        headers=transistor_headers(),
        json={"episode": {"status": "scheduled", "published_at": publish_at.isoformat()}},
        timeout=60,
    )
    patch_resp.raise_for_status()
    log(f"  Scheduled for: {publish_at.strftime('%Y-%m-%d %H:%M %Z')}")
    return patch_resp.json()


def transcribe_audio(audio_bytes: bytes, title: str) -> str | None:
    """
    Send audio to Gemini Flash for transcription.
    Returns transcript text, or None if transcription fails or API key missing.
    """
    if not GOOGLE_AI_API_KEY:
        log("  No GOOGLE_AI_API_KEY set — skipping transcription")
        return None

    log("  Transcribing audio with Gemini Flash...")
    try:
        client = genai.Client(api_key=GOOGLE_AI_API_KEY)

        # Write bytes to a temp file (Gemini File API needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            audio_file = client.files.upload(
                file=tmp_path,
                config=genai_types.UploadFileConfig(mime_type="audio/mp4"),
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    f"Transcribe this podcast episode titled '{title}' verbatim. "
                    "Return only the transcript text. No timestamps, no speaker labels, no commentary.",
                    audio_file,
                ],
            )
            # Clean up the Gemini uploaded file
            client.files.delete(name=audio_file.name)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        transcript = response.text.strip()
        log(f"  Transcript: {len(transcript)} chars")
        return transcript

    except Exception as e:
        log(f"  Transcription failed: {e}")
        return None


def upload_transcript_to_drive(article_id: str, title: str, transcript: str) -> str | None:
    """Upload transcript as a .txt file to Google Drive. Returns Drive file ID."""
    try:
        service = get_drive_service()
        drive_folder_id = os.getenv("GOOGLE_DRIVE_TRANSCRIPTS_FOLDER_ID") or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        safe_title = title[:50].replace("/", "-")
        filename = f"{article_id}_{safe_title}_transcript.txt"
        file_metadata = {"name": filename, "parents": [drive_folder_id]}
        content = transcript.encode("utf-8")
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype="text/plain")
        file = service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()
        drive_id = file.get("id")
        log(f"  Transcript saved to Drive — ID: {drive_id}")
        return drive_id
    except Exception as e:
        log(f"  Could not save transcript to Drive: {e}")
        return None


def get_next_publish_time(published_today: int) -> datetime:
    """
    Calculate the next publish slot.
    20 episodes/day starting 8am Eastern, every 45 minutes.
    """
    now = datetime.now(EASTERN)
    base = now.replace(hour=8, minute=0, second=0, microsecond=0)
    slot = base + timedelta(minutes=45 * published_today)
    # If we're past today's slots, start tomorrow
    if slot < now:
        slot += timedelta(days=1)
        slot = slot.replace(hour=8, minute=0) + timedelta(minutes=45 * published_today)
    return slot


# ── Main ──────────────────────────────────────────────────────────────────────
def upload_episode(article: dict, published_today: int = 0) -> dict:
    """
    Upload one episode to Transistor.fm.
    article must have: seoTitle, seoDescription, seoTags, driveAudioId
    Returns updated article dict with Transistor episode ID.
    """
    title = article["seoTitle"]
    description = article["seoDescription"]
    tags = article["seoTags"]
    drive_audio_id = article.get("driveAudioId")

    if not drive_audio_id:
        raise ValueError(f"No driveAudioId found for article {article['id']}")

    # Step 1: Get presigned S3 upload URL
    # Ensure filename always uses .m4a extension regardless of article id format
    base_id = str(article['id']).split('.')[0]  # strip any existing extension
    upload_url, content_type, audio_url = authorize_upload(f"{base_id}.m4a")

    # Step 2: Download audio from Drive and upload to S3
    audio_bytes = download_from_drive(drive_audio_id)
    upload_audio_to_s3(upload_url, content_type, audio_bytes)

    # Step 2.5: Transcribe audio with Gemini (reuse the bytes already in memory)
    transcript = transcribe_audio(audio_bytes, title)
    drive_transcript_id = None
    if transcript:
        drive_transcript_id = upload_transcript_to_drive(
            str(article.get("id", base_id)), title, transcript
        )

    # Step 3: Create episode with audio, schedule, and attach transcript
    publish_time = get_next_publish_time(published_today)
    result_data = create_and_publish_episode(
        audio_url, title, description, tags, publish_time, transcript
    )
    episode_id = result_data["data"]["id"]

    log(f"Episode live on Transistor — ID: {episode_id}")

    return {
        **article,
        "status": "published",
        "transistorEpisodeId": episode_id,
        "publishedAt": publish_time.isoformat(),
        "uploadedAt": datetime.now().isoformat(),
        "driveTranscriptId": drive_transcript_id,
    }


# Allow running standalone for testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python 4-upload.py <path/to/article.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        article = json.load(f)

    result = upload_episode(article)
    print(json.dumps(result, indent=2))
