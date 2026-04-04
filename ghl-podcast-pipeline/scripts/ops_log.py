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

OPS_LOG_WEBHOOK_URL = os.getenv("OPS_LOG_WEBHOOK_URL", "")

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

    # 2. Post to #ops-log via webhook (if configured)
    if OPS_LOG_WEBHOOK_URL and level != "detail":
        _post_to_slack(tag, message, level)

    _log(f"{tag} {message}")


def _post_to_slack(tag: str, message: str, level: str):
    """Post a single entry to #ops-log via webhook."""
    emoji = {"info": "", "warning": "⚠️ ", "error": "🔴 ", "detail": ""}.get(level, "")
    text = f"{emoji}*{tag}* {message}"

    try:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = Request(OPS_LOG_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                _log(f"Ops-log webhook returned {resp.status}")
    except Exception as e:
        _log(f"Ops-log webhook failed (non-fatal): {e}")


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
