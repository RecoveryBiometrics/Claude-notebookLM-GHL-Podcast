"""
ops_log.py
Centralized ops-log posting for all pipeline scripts.

All pipeline events flow through here → #ops-log channel.
The daily CEO digest (in scheduler.py) reads today's entries and summarizes to #ceo.

Usage:
    from ops_log import ops_log

    ops_log("Podcast Pipeline", "Cycle #42 complete. 20 episodes, 20 blogs, 0 failures.")
    ops_log("SEO Optimizer", "Optimized 3 pages: spam-calls (rewrite), 3d-secure (rewrite), ai-agents (expand)")
    ops_log("SEO Optimizer", "Title rewrite: 'How to X' → 'Stop X in 5 Min'", level="detail")
"""

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).parent.parent
OPS_LOG_FILE = BASE_DIR / "data" / "ops-log.json"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
OPS_LOG_CHANNEL = "C0AQG0DP222"        # #ops-log
DETAIL_CHANNEL = "C0AQ95LG97F"         # #globalhighlevel

# Tag prefixes from projects.yml
BUSINESS_TAG = os.getenv("OPS_LOG_BUSINESS", "GHL")


def _log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [OPS-LOG] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_entries() -> list:
    if not OPS_LOG_FILE.exists():
        return []
    try:
        return json.loads(OPS_LOG_FILE.read_text())
    except Exception:
        return []


def _save_entries(entries: list):
    # Keep last 200 entries to prevent unbounded growth
    entries = entries[-200:]
    OPS_LOG_FILE.write_text(json.dumps(entries, indent=2))


def ops_log(source: str, message: str, level: str = "info", data: dict = None):
    """
    Post an ops-log entry.

    Args:
        source: Which pipeline/team (e.g. "Podcast Pipeline", "SEO Optimizer", "Weekly SEO Report")
        message: One-line summary of what happened
        level: "info", "detail", "warning", "error"
        data: Optional structured data to attach
    """
    timestamp = datetime.now().isoformat()
    tag = f"[{BUSINESS_TAG}] [{source}]"

    entry = {
        "timestamp": timestamp,
        "business": BUSINESS_TAG,
        "source": source,
        "level": level,
        "message": message,
        "data": data,
    }

    # 1. Append to local log file
    entries = _load_entries()
    entries.append(entry)
    _save_entries(entries)

    # 2. Post to #ops-log via Bot Token API (skip detail-level messages)
    if SLACK_BOT_TOKEN and level != "detail":
        _post_to_slack(OPS_LOG_CHANNEL, tag, message, level)

    # 3. Post detail-level messages to #globalhighlevel
    if SLACK_BOT_TOKEN and level == "detail":
        _post_to_slack(DETAIL_CHANNEL, tag, message, level)

    _log(f"{tag} {message}")


def post_to_channel(channel: str, text: str):
    """Post a message to any Slack channel via Bot Token API."""
    if not SLACK_BOT_TOKEN:
        _log("No SLACK_BOT_TOKEN set — skipping Slack post")
        return
    try:
        payload = json.dumps({"channel": channel, "text": text}).encode("utf-8")
        req = Request(
            "https://slack.com/api/chat.postMessage",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            },
        )
        with urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            if not body.get("ok"):
                _log(f"Slack API error: {body.get('error', 'unknown')}")
    except Exception as e:
        _log(f"Slack post failed (non-fatal): {e}")


def _post_to_slack(channel: str, tag: str, message: str, level: str):
    """Post a single entry to a Slack channel via Bot Token API."""
    emoji = {"info": "", "warning": "⚠️ ", "error": "🔴 ", "detail": ""}.get(level, "")
    text = f"{emoji}*{tag}* {message}"
    post_to_channel(channel, text)


def get_todays_entries() -> list:
    """Get all ops-log entries from today. Used by CEO digest."""
    today = datetime.now().strftime("%Y-%m-%d")
    entries = _load_entries()
    return [e for e in entries if e["timestamp"].startswith(today)]


def build_ceo_digest() -> str:
    """
    Build a CEO-friendly summary from today's ops-log entries.
    Returns formatted text for Slack.
    """
    entries = get_todays_entries()
    if not entries:
        return ""

    # Group by source
    by_source = {}
    for e in entries:
        if e["level"] == "detail":
            continue
        src = e["source"]
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(e)

    lines = []
    for source, items in by_source.items():
        errors = [i for i in items if i["level"] == "error"]
        warnings = [i for i in items if i["level"] == "warning"]
        infos = [i for i in items if i["level"] == "info"]

        if errors:
            status = "🔴"
        elif warnings:
            status = "⚠️"
        else:
            status = "✅"

        lines.append(f"{status} *{source}*")
        for item in items:
            lines.append(f"  • {item['message']}")

    date_str = datetime.now().strftime("%b %d")
    header = f"*Daily Ops Summary — {date_str}*\n"
    return header + "\n".join(lines)
