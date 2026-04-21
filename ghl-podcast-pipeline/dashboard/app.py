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


@app.route("/system")
def system():
    """System overview page — full architecture visualization."""
    published = load_published()
    done = [r for r in published if r.get("status") == "published"]

    # Count posts across site
    site_posts_dir = BASE_DIR.parent / "globalhighlevel-site" / "posts"
    total_posts = len(list(site_posts_dir.glob("*.json"))) if site_posts_dir.exists() else 0

    # Count cooldowns
    cooldown_file = BASE_DIR / "data" / "seo-cooldown.json"
    cooldowns = 0
    if cooldown_file.exists():
        cooldowns = len(json.load(open(cooldown_file)))

    # Count redirects
    redirects_file = BASE_DIR.parent / "globalhighlevel-site" / "_redirects"
    redirects = 0
    if redirects_file.exists():
        redirects = len([l for l in open(redirects_file).readlines() if l.strip() and "301" in l])

    # Count skills
    skills_dir = Path(os.path.expanduser("~/.claude/skills"))
    skill_list = []
    if skills_dir.exists():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir():
                skill_md = d / "SKILL.md"
                desc = ""
                if skill_md.exists():
                    for line in open(skill_md).readlines():
                        if line.startswith("description:"):
                            desc = line.split("description:", 1)[1].strip()[:120]
                            break
                skill_list.append({"name": d.name, "desc": desc or "—"})

    system_stats = {
        "total_posts": total_posts,
        "languages": 4,
        "posts_per_day": 35,
        "episodes": len(done),
        "cooldowns": cooldowns,
        "redirects": redirects,
        "skills": len(skill_list),
        "triggers": 3,  # CEO Daily, Verticals Measurement, Weekly SEO
    }

    return render_template("system.html", stats=system_stats, skills=skill_list)


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "5050"))
    print(f"Dashboard running at http://localhost:{port}")
    print(f"System overview at http://localhost:{port}/system")
    app.run(debug=False, host="0.0.0.0", port=port)
