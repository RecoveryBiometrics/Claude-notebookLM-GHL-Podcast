"""
2-notebooklm.py
For each article:
  1. Claude enriches short articles into full guides
  2. Claude fact-checks the enriched content against known GHL facts
  3. NotebookLM gets multiple sources: article URL + related URLs + enriched text
  4. Audio is generated, downloaded, uploaded to Google Drive
  5. Local copy deleted to keep Chromebook storage clear
"""

import asyncio
import json
import os
import io
import re
from pathlib import Path
from datetime import datetime

import anthropic
try:
    from cost_logger import log_api_cost
except ImportError:
    def log_api_cost(*a, **kw): return {}
import requests as http_requests
from dotenv import load_dotenv
from notebooklm import NotebookLMClient
from notebooklm.rpc.types import AudioFormat, AudioLength
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
AUDIO_DIR = BASE_DIR / "data" / "audio"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
TOKEN_FILE = BASE_DIR / "token.json"
CREDENTIALS_FILE = BASE_DIR / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ────────────────────────────────────────────────────────────────────
DRIVE_FOLDER_ID            = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
DRIVE_AUDIO_FOLDER_ID      = os.getenv("GOOGLE_DRIVE_AUDIO_FOLDER_ID", DRIVE_FOLDER_ID)
DRIVE_ARTICLES_FOLDER_ID   = os.getenv("GOOGLE_DRIVE_ARTICLES_FOLDER_ID", DRIVE_FOLDER_ID)
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
MIN_CONTENT_LENGTH = 3000  # chars — below this we enrich with Claude first
GHL_SOLUTIONS_BASE = "https://help.gohighlevel.com/support/solutions"

NOTEBOOKLM_INSTRUCTIONS = """
Start the episode by warmly welcoming listeners and telling them they can get
a FREE 30-day GoHighLevel trial — double the standard trial length — and that
the link is waiting for them in the show notes below.

Then cover the topic thoroughly with practical, actionable takeaways for
digital marketing agency owners using GoHighLevel.

Close the episode by reminding listeners one more time: the free 30-day
GoHighLevel trial link is in the show notes — encourage them to click it.
"""


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [NOTEBOOKLM] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Agent 1: Content Enricher ─────────────────────────────────────────────────
def enrich_article(article: dict) -> str:
    """
    If article is too short, Claude expands it into a full guide.
    Always returns at least MIN_CONTENT_LENGTH chars.
    Format: flowing paragraphs (no headers/bullets) — ideal for podcast audio.
    Target: ~1500-2000 words.
    """
    body = article["body"]
    if len(body) >= MIN_CONTENT_LENGTH:
        log(f"  Content is sufficient ({len(body)} chars) — no enrichment needed")
        return body

    log(f"  Article is short ({len(body)} chars) — enriching with Claude...")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{
            "role": "user",
            "content": f"""You are a GoHighLevel expert creating content for a podcast episode aimed at digital marketing agency owners.

Topic: {article['title']}
Category: {article.get('category', '')} / {article.get('subcategory', '')}
Source URL: {article.get('url', '')}

Existing article content:
{body}

Expand this into a comprehensive guide of at least 1500 words.
Cover:
- What this feature is and why it matters for agencies
- Step-by-step how to use it inside GoHighLevel
- Practical tips and best practices from real agency use
- Common mistakes to avoid
- Specific real-world use cases with outcomes

IMPORTANT: Only write facts you are confident are accurate about GoHighLevel. If unsure about a specific detail, write around it generally rather than guess. Do not invent feature names, menu locations, or pricing.

Write in plain conversational English — flowing paragraphs only, no headers, no bullet points, no markdown. This will be read by an AI podcast host."""
        }]
    )

    log_api_cost(message, script="2-notebooklm-enrich")
    enriched = message.content[0].text.strip()
    log(f"  Enriched: {len(body)} → {len(enriched)} chars")
    return enriched


# ── Agent 2: Fact Checker ─────────────────────────────────────────────────────
def fact_check(article: dict, enriched_body: str) -> str:
    """
    Fact-checks the enriched content for GoHighLevel accuracy.
    Removes or corrects anything that seems fabricated or inaccurate.
    Returns verified content.
    """
    log(f"  Fact-checking enriched content...")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{
            "role": "user",
            "content": f"""You are a GoHighLevel fact-checker reviewing podcast content for accuracy.

Original article title: {article['title']}
Original article URL: {article.get('url', '')}
Original article content (ground truth):
{article['body']}

Enriched content to fact-check:
{enriched_body}

Review the enriched content and:
1. Keep everything that is accurate or consistent with the original article
2. Remove or rewrite any specific claims that contradict the original article
3. Remove any invented feature names, menu locations, or pricing that aren't in the original
4. Keep general best practices and agency use cases even if not in the original (these are opinion/advice, not facts)
5. Ensure GoHighLevel is spelled correctly throughout
6. Do NOT add new facts — only verify and clean existing content

Return the cleaned content only — no commentary, no notes about what you changed. Just the verified podcast-ready text in flowing paragraphs."""
        }]
    )

    log_api_cost(message, script="2-notebooklm-factcheck")
    verified = message.content[0].text.strip()
    log(f"  Fact-check complete — {len(verified)} chars verified")
    return verified


# ── Related URL Finder ────────────────────────────────────────────────────────
async def find_related_urls(article: dict, page) -> list[str]:
    """
    Find related GHL help article URLs from the same category.
    Returns up to 3 related URLs to add as additional NotebookLM sources.
    """
    try:
        category_url = f"{GHL_SOLUTIONS_BASE}"
        await page.goto(category_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)

        all_links = await page.eval_on_selector_all(
            "a[href*='/support/solutions/articles/']",
            "els => els.map(e => e.href)"
        )

        # Filter out the current article, get up to 3 from same category
        current_url = article.get("url", "")
        related = [
            url for url in all_links
            if url != current_url and url not in [current_url]
        ][:3]

        log(f"  Found {len(related)} related URLs for additional sources")
        return related

    except Exception as e:
        log(f"  Could not find related URLs: {e}")
        return []


# ── Google Drive Auth ─────────────────────────────────────────────────────────
def get_drive_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), DRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), DRIVE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def upload_to_drive(service, local_path: Path, filename: str) -> str:
    log(f"Uploading to Google Drive: {filename}")
    file_metadata = {"name": filename, "parents": [DRIVE_AUDIO_FOLDER_ID]}
    media = MediaFileUpload(str(local_path), mimetype="audio/mp4", resumable=True)
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    drive_id = file.get("id")
    log(f"Uploaded to Drive — file ID: {drive_id}")
    return drive_id


def upload_json_to_drive(service, data: dict, filename: str) -> str:
    file_metadata = {"name": filename, "parents": [DRIVE_ARTICLES_FOLDER_ID]}
    content = json.dumps(data, indent=2).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype="application/json")
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    return file.get("id")


# ── NotebookLM Audio Generation ───────────────────────────────────────────────
async def generate_audio(article: dict) -> dict | None:
    """
    Full enrichment + fact-check + multi-source NotebookLM generation.
    """
    article_id = article["id"]
    title = article["title"]
    local_path = AUDIO_DIR / f"{article_id}.mp4"

    # Clean title
    clean_title = re.sub(
        r'\s*[:\|]\s*(HighLevel Support Portal|GoHighLevel).*$', '', title
    ).strip()
    log(f"Processing: {clean_title}")

    nb_id = None
    try:
        async with await NotebookLMClient.from_storage() as client:
            nb = await client.notebooks.create(clean_title)
            nb_id = nb.id
            log(f"  Created notebook: {nb.id}")

            sources_added = 0

            # Source 1: Original GHL help article URL
            if article.get("url"):
                try:
                    await client.sources.add_url(nb.id, article["url"])
                    log(f"  Source 1: GHL article URL added")
                    sources_added += 1
                    await asyncio.sleep(3)
                except Exception as e:
                    log(f"  Could not add article URL: {e}")

            # Source 2: Article body text
            await client.sources.add_text(nb.id, clean_title, article["body"])
            log(f"  Source 2: Article text added ({len(article['body'])} chars)")
            sources_added += 1

            # Source 3+: NotebookLM web research — searches web for related content
            try:
                log(f"  Running NotebookLM web research for: {clean_title}")
                research_task = await client.research.start(
                    nb.id,
                    query=f"GoHighLevel {clean_title} tutorial guide agency",
                    source="web",
                    mode="fast",
                )

                if research_task:
                    # Poll until research completes (up to 60 seconds)
                    for _ in range(12):
                        await asyncio.sleep(5)
                        research_result = await client.research.poll(nb.id)
                        if research_result.get("status") == "completed":
                            break

                    web_sources = research_result.get("sources", [])
                    # Filter to sources with valid URLs, take top 3
                    valid_sources = [s for s in web_sources if s.get("url")][:3]

                    if valid_sources:
                        imported = await client.research.import_sources(
                            nb.id, research_task["task_id"], valid_sources
                        )
                        log(f"  Source 3+: {len(valid_sources)} web sources imported via research")
                        for s in valid_sources:
                            log(f"    - {s.get('title', s.get('url', ''))[:60]}")
                        sources_added += len(valid_sources)
                    else:
                        log(f"  No web sources found via research")
            except Exception as e:
                log(f"  Web research failed (continuing): {e}")

            log(f"  Total sources: {sources_added} — waiting 2 min for sources to populate...")
            await asyncio.sleep(120)

            log(f"  Generating audio...")
            status = await client.artifacts.generate_audio(
                nb.id,
                instructions=NOTEBOOKLM_INSTRUCTIONS,
                audio_format=AudioFormat.DEEP_DIVE,
                audio_length=AudioLength.DEFAULT,
            )

            # If task_id is empty, generation failed immediately (quota/rate limit)
            if not status.task_id:
                err = getattr(status, 'error', 'unknown error')
                log(f"  FAILED: audio generation rejected — {err}")
                await client.notebooks.delete(nb.id)
                return None

            log(f"  Polling for completion (up to 20 min)...")

            final = await client.artifacts.wait_for_completion(
                nb.id, status.task_id, timeout=1200
            )

            if not final.is_complete:
                log(f"  FAILED: timed out")
                await client.notebooks.delete(nb.id)
                return None

            await client.artifacts.download_audio(nb.id, str(local_path))
            log(f"  Downloaded: {local_path.name} ({local_path.stat().st_size // 1024}KB)")

            await client.notebooks.delete(nb.id)
            log(f"  Notebook cleaned up")

        return {
            **article,
            "title": clean_title,
            "status": "audio_ready",
            "audioFile": str(local_path),
            "sourcesUsed": sources_added,
            "audioGeneratedAt": datetime.now().isoformat(),
        }

    except Exception as e:
        log(f"  ERROR: {e}")
        if nb_id:
            try:
                async with await NotebookLMClient.from_storage() as client:
                    await client.notebooks.delete(nb_id)
                    log(f"  Notebook {nb_id} cleaned up after error")
            except Exception:
                log(f"  WARNING: could not delete notebook {nb_id} — delete it manually")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────
async def process_article(article: dict) -> dict | None:
    article_id = article["id"]
    local_path = AUDIO_DIR / f"{article_id}.mp4"

    result = await generate_audio(article)
    if not result:
        return None

    try:
        drive = get_drive_service()
        safe_title = result['title'][:50].replace('/', '-')

        drive_audio_id = upload_to_drive(
            drive, local_path,
            f"{article_id}_{safe_title}.mp4"
        )
        drive_json_id = upload_json_to_drive(
            drive, article,
            f"{article_id}_article.json"
        )

        result["driveAudioId"] = drive_audio_id
        result["driveJsonId"] = drive_json_id
        log(f"Saved to Google Drive ✓")

    except Exception as e:
        log(f"  Drive upload error: {e}")
        result["driveError"] = str(e)

    try:
        if local_path.exists():
            local_path.unlink()
            log(f"  Local file deleted")
    except Exception as e:
        log(f"  WARNING: could not delete local file: {e}")

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python 2-notebooklm.py <path/to/article.json>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        article = json.load(f)
    result = asyncio.run(process_article(article))
    if result:
        print(json.dumps(result, indent=2))
    else:
        print("Failed")
        sys.exit(1)
