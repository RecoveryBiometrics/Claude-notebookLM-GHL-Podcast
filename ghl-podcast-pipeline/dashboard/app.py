"""
dashboard/app.py
Local Flask dashboard to monitor the pipeline.
Run: python dashboard/app.py
Then open: http://localhost:5000
"""

import json
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
PUBLISHED_FILE = BASE_DIR / "data" / "published.json"
ARTICLES_DIR = BASE_DIR / "data" / "articles"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"

TRANSISTOR_API_KEY = os.getenv("TRANSISTOR_API_KEY")
TRANSISTOR_SHOW_ID = os.getenv("TRANSISTOR_SHOW_ID")

app = Flask(__name__)


def load_published() -> list:
    if PUBLISHED_FILE.exists():
        with open(PUBLISHED_FILE) as f:
            return json.load(f)
    return []


def count_articles() -> int:
    if ARTICLES_DIR.exists():
        return len(list(ARTICLES_DIR.glob("*.json")))
    return 0


def get_stats(published: list) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    this_week = datetime.now().strftime("%Y-%W")

    total = len(published)
    done = [r for r in published if r.get("status") == "published"]
    failed = [r for r in published if r.get("status") == "failed"]
    today_eps = [r for r in done if r.get("uploadedAt", "").startswith(today)]
    week_eps = [
        r for r in done
        if r.get("uploadedAt") and
        datetime.fromisoformat(r["uploadedAt"]).strftime("%Y-%W") == this_week
    ]

    return {
        "total_processed": total,
        "total_published": len(done),
        "total_failed": len(failed),
        "today": len(today_eps),
        "this_week": len(week_eps),
        "articles_scraped": count_articles(),
        "pending": count_articles() - total,
    }


def get_top_episodes(published: list, n: int = 10) -> list:
    done = [r for r in published if r.get("status") == "published"]
    sorted_eps = sorted(done, key=lambda x: x.get("streams", 0), reverse=True)
    return sorted_eps[:n]


def get_recent_log(n: int = 50) -> list:
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE) as f:
        lines = f.readlines()
    return [l.rstrip() for l in lines[-n:]]


def get_failed(published: list) -> list:
    return [r for r in published if r.get("status") == "failed"]


@app.route("/")
def index():
    published = load_published()
    stats = get_stats(published)
    top = get_top_episodes(published)
    failed = get_failed(published)
    log_lines = get_recent_log()
    return render_template(
        "index.html",
        stats=stats,
        top_episodes=top,
        failed=failed,
        log_lines=log_lines,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/api/stats")
def api_stats():
    published = load_published()
    return jsonify(get_stats(published))


@app.route("/api/log")
def api_log():
    return jsonify(get_recent_log(100))


if __name__ == "__main__":
    print("Dashboard running at http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
