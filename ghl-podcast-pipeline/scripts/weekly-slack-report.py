"""
Weekly SEO & Analytics Slack Report
Pulls GSC data + GA4 data + pipeline stats, posts a formatted summary to Slack.

Reusable across projects — configure via environment variables:
  SLACK_WEBHOOK_URL  — Slack incoming webhook URL
  GSC_SITE_URL       — Google Search Console property (e.g. https://globalhighlevel.com)
  GA4_PROPERTY_ID    — GA4 property ID (numeric, e.g. 123456789)
  SITE_NAME          — Display name for the report

Can be run standalone or called from scheduler.py.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
GSC_DATA_FILE = DATA_DIR / "gsc-stats.json"
PUBLISHED_FILE = DATA_DIR / "published.json"
INDIA_PUBLISHED = DATA_DIR / "india-published.json"
SPANISH_PUBLISHED = DATA_DIR / "spanish-published.json"
WEEKLY_STATE_FILE = DATA_DIR / "weekly-report-state.json"

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SITE_NAME = os.getenv("SITE_NAME", "GlobalHighLevel")


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def should_send_weekly() -> bool:
    """Check if 7+ days have passed since last weekly report."""
    if not WEEKLY_STATE_FILE.exists():
        return True
    try:
        state = json.loads(WEEKLY_STATE_FILE.read_text())
        last_sent = datetime.fromisoformat(state.get("last_sent", "2000-01-01"))
        return (datetime.now() - last_sent).days >= 7
    except Exception:
        return True


def mark_sent():
    """Record that we sent the weekly report."""
    WEEKLY_STATE_FILE.write_text(json.dumps({
        "last_sent": datetime.now().isoformat(),
    }))


def load_gsc_data() -> dict:
    """Load latest GSC stats from file."""
    if GSC_DATA_FILE.exists():
        return json.loads(GSC_DATA_FILE.read_text())
    return {}


def load_published_counts() -> dict:
    """Count total and recent posts from published data files."""
    counts = {"episodes": 0, "episodes_7d": 0, "india": 0, "india_7d": 0, "spanish": 0, "spanish_7d": 0}
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()

    for key, filepath in [("episodes", PUBLISHED_FILE), ("india", INDIA_PUBLISHED), ("spanish", SPANISH_PUBLISHED)]:
        if filepath.exists():
            try:
                data = json.loads(filepath.read_text())
                if isinstance(data, list):
                    counts[key] = len(data)
                    counts[f"{key}_7d"] = sum(
                        1 for item in data
                        if item.get("publishedAt", item.get("published_at", "")) > cutoff
                    )
                elif isinstance(data, dict) and "posts" in data:
                    posts = data["posts"]
                    counts[key] = len(posts)
                    counts[f"{key}_7d"] = sum(
                        1 for item in posts
                        if item.get("publishedAt", item.get("published_at", "")) > cutoff
                    )
            except Exception:
                pass

    return counts


def build_slack_message() -> dict:
    """Build the weekly Slack message payload."""
    gsc = load_gsc_data()
    counts = load_published_counts()
    totals = gsc.get("totals", {})
    pages = gsc.get("pages", [])
    queries = gsc.get("queries", [])
    period = gsc.get("period", "unknown")

    # Top pages by clicks
    top_pages = [p for p in pages if p.get("clicks", 0) > 0][:5]
    if not top_pages:
        top_pages = sorted(pages, key=lambda x: x.get("impressions", 0), reverse=True)[:5]

    # Pages close to page 1 (positions 8-20, high impressions)
    almost_there = [
        p for p in pages
        if 8 <= p.get("position", 99) <= 20 and p.get("impressions", 0) >= 10
    ]
    almost_there.sort(key=lambda x: x["impressions"], reverse=True)

    # Top queries
    top_queries = queries[:10]

    # Format top pages
    pages_text = ""
    for p in top_pages:
        slug = p["page"].split("/blog/")[-1].rstrip("/") if "/blog/" in p["page"] else p["page"]
        pages_text += f"  • `{slug}` — {p['clicks']} clicks, {p['impressions']} imp, pos {p['position']}\n"
    if not pages_text:
        pages_text = "  No page data yet\n"

    # Format almost-there pages
    almost_text = ""
    for p in almost_there[:5]:
        slug = p["page"].split("/blog/")[-1].rstrip("/") if "/blog/" in p["page"] else p["page"]
        almost_text += f"  • `{slug}` — pos {p['position']}, {p['impressions']} imp\n"

    # Format queries
    queries_text = ""
    for q in top_queries:
        queries_text += f"  • \"{q['query']}\" — {q['impressions']} imp, pos {q['position']}\n"
    if not queries_text:
        queries_text = "  No query data yet\n"

    # Build the message
    msg = f"""*{SITE_NAME} — Weekly SEO Report*
_{period}_

*Google Search Console*
> Clicks: *{totals.get('clicks', 0)}* | Impressions: *{totals.get('impressions', 0)}* | CTR: *{totals.get('ctr', 0)}%* | Avg Position: *{totals.get('position', 0)}*

*Top Pages*
{pages_text}
*Top Search Queries*
{queries_text}"""

    if almost_text:
        msg += f"""
*Almost Page 1* (positions 8-20, worth optimizing)
{almost_text}"""

    msg += f"""
*Content This Week*
  • Episodes: {counts['episodes_7d']} new ({counts['episodes']} total)
  • India blogs: {counts['india_7d']} new ({counts['india']} total)
  • Spanish blogs: {counts['spanish_7d']} new ({counts['spanish']} total)
"""

    return {"text": msg}


def send_to_slack(payload: dict) -> bool:
    """Send a message to Slack via incoming webhook."""
    if not SLACK_WEBHOOK_URL:
        log("No SLACK_WEBHOOK_URL set — skipping Slack report")
        return False

    try:
        data = json.dumps(payload).encode("utf-8")
        req = Request(SLACK_WEBHOOK_URL, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                log("Weekly Slack report sent successfully")
                return True
            else:
                log(f"Slack returned status {resp.status}")
                return False
    except URLError as e:
        log(f"Slack webhook failed: {e}")
        return False


def main(force: bool = False):
    """Run the weekly Slack report. Skips if <7 days since last report unless force=True."""
    if not force and not should_send_weekly():
        log("Weekly report not due yet — skipping")
        return

    log(f"Building weekly report for {SITE_NAME}...")
    payload = build_slack_message()
    if send_to_slack(payload):
        mark_sent()
        log("Done — next report in 7 days")
    else:
        log("Report not sent — will retry next cycle")


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
