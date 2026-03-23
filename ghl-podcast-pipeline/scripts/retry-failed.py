"""
retry-failed.py
Intelligent recovery agent for the GHL podcast pipeline.

For each failed episode in published.json:
  - If audio is on Google Drive → skip audio generation, retry SEO + Transistor upload
  - If no Drive audio → retry full pipeline (scrape → audio → SEO → upload)

Also runs a self-diagnostic: reads the last error from the log, uses Claude
to identify the root cause and suggest/apply a code fix before retrying.

Run: venv/bin/python3 scripts/retry-failed.py
"""

import asyncio
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
import sys; sys.path.insert(0, os.path.expanduser("~/.claude"))
from cost_logger import log_api_cost
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
PUBLISHED_FILE = BASE_DIR / "data" / "published.json"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
SCRIPTS_DIR = Path(__file__).parent


def load_script(name: str):
    path = SCRIPTS_DIR / name
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [RETRY] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_published() -> list:
    if PUBLISHED_FILE.exists():
        with open(PUBLISHED_FILE) as f:
            return json.load(f)
    return []


def save_published(records: list):
    with open(PUBLISHED_FILE, "w") as f:
        json.dump(records, f, indent=2)


# ── Self-Diagnostic Agent ──────────────────────────────────────────────────────
def extract_recent_errors(n_lines: int = 100) -> str:
    """Pull the last N lines from the log containing ERROR or FAILED."""
    if not LOG_FILE.exists():
        return ""
    lines = LOG_FILE.read_text().splitlines()
    error_lines = [l for l in lines[-n_lines:] if "ERROR" in l or "FAILED" in l or "Error" in l]
    return "\n".join(error_lines[-20:])  # last 20 error lines


def read_script(name: str) -> str:
    path = SCRIPTS_DIR / name
    return path.read_text() if path.exists() else ""


def diagnostic_agent() -> dict:
    """
    Claude agent that reads recent errors + relevant scripts,
    diagnoses the root cause, and returns a fix if needed.
    Returns: {
        "issue": str,
        "fix_needed": bool,
        "file": str,
        "old_code": str,
        "new_code": str,
        "explanation": str,
    }
    """
    log("Running self-diagnostic agent...")

    recent_errors = extract_recent_errors()
    if not recent_errors:
        log("  No recent errors found in log.")
        return {"fix_needed": False, "issue": "No errors found"}

    log(f"  Found {len(recent_errors.splitlines())} error lines to analyze")

    upload_code = read_script("4-upload.py")
    notebooklm_code = read_script("2-notebooklm.py")
    seo_code = read_script("3-seo.py")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""You are a Python debugging agent for an automated podcast pipeline.

Recent error log lines:
{recent_errors}

=== 4-upload.py ===
{upload_code}

=== 2-notebooklm.py (first 100 lines) ===
{notebooklm_code[:3000]}

=== 3-seo.py (first 50 lines) ===
{seo_code[:1500]}

Analyze the errors and determine:
1. What is the root cause?
2. Is there a code fix needed?
3. If yes, what exact change should be made?

Respond in this exact JSON format (no other text):
{{
  "issue": "brief description of root cause",
  "fix_needed": true or false,
  "file": "filename like 4-upload.py or empty string",
  "old_code": "exact code string to replace (or empty)",
  "new_code": "replacement code string (or empty)",
  "explanation": "what the fix does and why"
}}"""
        }]
    )
    log_api_cost(message, script="retry-failed")

    try:
        # Extract JSON from response
        text = message.content[0].text.strip()
        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        result = json.loads(text)
        log(f"  Diagnostic: {result.get('issue', 'unknown')}")
        if result.get("fix_needed"):
            log(f"  Fix needed in {result.get('file')}: {result.get('explanation', '')[:80]}")
        return result
    except Exception as e:
        log(f"  Diagnostic parse error: {e}")
        return {"fix_needed": False, "issue": "Could not parse diagnostic response"}


def apply_fix(diagnosis: dict) -> bool:
    """Apply the code fix suggested by the diagnostic agent."""
    if not diagnosis.get("fix_needed"):
        return False

    filename = diagnosis.get("file", "")
    old_code = diagnosis.get("old_code", "")
    new_code = diagnosis.get("new_code", "")

    if not filename or not old_code or not new_code:
        log("  Fix missing required fields — skipping auto-fix")
        return False

    filepath = SCRIPTS_DIR / filename
    if not filepath.exists():
        log(f"  File not found: {filepath}")
        return False

    content = filepath.read_text()
    if old_code not in content:
        log(f"  Could not find code to replace in {filename} — skipping")
        return False

    fixed = content.replace(old_code, new_code, 1)
    filepath.write_text(fixed)
    log(f"  Applied fix to {filename}: {diagnosis.get('explanation', '')[:80]}")
    return True


# ── Retry Logic ────────────────────────────────────────────────────────────────
async def retry_upload_only(article: dict, published_today: int) -> dict | None:
    """
    Article already has audio on Drive. Just run SEO + Transistor upload.
    """
    seo = load_script("3-seo.py")
    upload = load_script("4-upload.py")

    log(f"  Retrying SEO + upload for: {article.get('title', article['articleId'])[:60]}")

    # Re-run SEO if any required field is missing
    if not all([article.get("seoTitle"), article.get("seoDescription"), article.get("seoTags")]):
        # SEO needs a body field — use title as fallback if body not available
        if not article.get("body"):
            article["body"] = article.get("title", "")
        try:
            article = seo.generate_seo(article)
        except Exception as e:
            log(f"  SEO failed: {e}")
            return None

    # Re-run upload
    try:
        result = upload.upload_episode(article, published_today)
        log(f"  Upload succeeded: {result.get('transistorEpisodeId')}")
        return result
    except Exception as e:
        log(f"  Upload still failing: {e}")
        return None


async def retry_full_pipeline(article_id: str, published_ids: set, published_today: int) -> dict | None:
    """
    Full retry: scrape the article again and run the whole pipeline.
    """
    from playwright.async_api import async_playwright

    log(f"  Full retry for article {article_id} — re-scraping...")

    notebooklm = load_script("2-notebooklm.py")
    seo = load_script("3-seo.py")
    upload = load_script("4-upload.py")

    # Try to find the article URL from published.json title
    # We'll scrape by visiting the article URL directly
    article_url = f"https://help.gohighlevel.com/support/solutions/articles/{article_id}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))

        await page.goto(article_url, wait_until="networkidle")
        await asyncio.sleep(2)

        title = (await page.title()).replace(" – GoHighLevel Support", "").replace(" | GoHighLevel", "").strip()
        body = ""
        for sel in [".article-body", ".article__body", "[class*='article-content']", "main"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    body = (await el.inner_text()).strip()
                    if len(body) > 100:
                        break
            except Exception:
                continue

        await browser.close()

    if not body:
        log(f"  Could not scrape article {article_id}")
        return None

    article = {
        "id": article_id,
        "title": title,
        "url": article_url,
        "category": "",
        "subcategory": "",
        "body": body,
        "scraped": datetime.now().strftime("%Y-%m-%d"),
    }

    result = await notebooklm.process_article(article)
    if not result:
        return None

    time.sleep(3)

    try:
        result = seo.generate_seo(result)
    except Exception as e:
        log(f"  SEO failed: {e}")
        return None

    time.sleep(3)

    try:
        result = upload.upload_episode(result, published_today)
        return result
    except Exception as e:
        log(f"  Upload failed: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    log("=" * 60)
    log("Retry agent starting")

    published = load_published()
    failed = [r for r in published if r.get("status") == "failed"]

    if not failed:
        log("No failed episodes found. Nothing to retry.")
        return

    log(f"Found {len(failed)} failed episodes")

    # Step 1: Retry each failed episode
    published_today = sum(
        1 for r in published
        if r.get("status") == "published" and
        r.get("uploadedAt", "").startswith(datetime.now().strftime("%Y-%m-%d"))
    )

    fixed_ids = set()

    for record in failed:
        article_id = record["articleId"]
        log(f"\nRetrying: {record.get('title', article_id)[:60]}")

        if record.get("driveAudioId"):
            # Audio exists on Drive — just retry upload
            # Ensure 'id' field exists (upload code expects 'id', records use 'articleId')
            record_with_id = {**record, "id": record["articleId"]}
            log(f"  Audio already on Drive ({record['driveAudioId']}) — retrying upload only")
            result = await retry_upload_only(record_with_id, published_today)
        else:
            # No audio — full retry
            log(f"  No Drive audio — running full pipeline")
            published_ids = {r["articleId"] for r in published}
            result = await retry_full_pipeline(article_id, published_ids, published_today)

        if result:
            # Update the record in published list
            for i, r in enumerate(published):
                if r["articleId"] == article_id:
                    published[i] = {
                        "articleId": result["id"],
                        "title": result.get("title", ""),
                        "category": result.get("category", ""),
                        "status": "published",
                        "transistorEpisodeId": result.get("transistorEpisodeId"),
                        "publishedAt": result.get("publishedAt"),
                        "uploadedAt": result.get("uploadedAt"),
                        "seoTitle": result.get("seoTitle"),
                        "driveAudioId": result.get("driveAudioId"),
                        "driveJsonId": result.get("driveJsonId"),
                        "driveTranscriptId": result.get("driveTranscriptId"),
                        "affiliateLinkIncluded": result.get("affiliateLinkIncluded", False),
                        "streams": 0,
                    }
                    break
            fixed_ids.add(article_id)
            published_today += 1
            save_published(published)
            log(f"  Recovered: {result.get('seoTitle', '')[:60]}")
        else:
            log(f"  Still failing — leaving as failed")

        time.sleep(5)

    log(f"\nRetry complete — {len(fixed_ids)}/{len(failed)} recovered")
    log("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
