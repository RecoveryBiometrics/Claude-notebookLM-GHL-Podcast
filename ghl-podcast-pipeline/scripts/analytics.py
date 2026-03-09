"""
analytics.py
Pulls download counts from Transistor API, updates published.json with real
stream data, and writes data/topic-weights.json to guide content prioritization.

Run: venv/bin/python3 scripts/analytics.py
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
PUBLISHED_FILE = BASE_DIR / "data" / "published.json"
TOPIC_WEIGHTS_FILE = BASE_DIR / "data" / "topic-weights.json"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"

TRANSISTOR_API_KEY = os.getenv("TRANSISTOR_API_KEY")
TRANSISTOR_SHOW_ID = os.getenv("TRANSISTOR_SHOW_ID")


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [ANALYTICS] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Transistor API ─────────────────────────────────────────────────────────────
def fetch_episode_analytics() -> dict:
    """
    Pull download counts for all episodes from Transistor.
    Returns dict mapping transistorEpisodeId (str) -> total downloads.
    """
    headers = {"x-api-key": TRANSISTOR_API_KEY, "Accept": "application/json"}
    end = datetime.now().strftime("%Y-%m-%d")

    url = f"https://api.transistor.fm/v1/analytics/{TRANSISTOR_SHOW_ID}/episodes"
    params = {"start_date": "2025-01-01", "end_date": end}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        downloads = {}
        for ep in data.get("data", []):
            ep_id = str(ep.get("id", ""))
            total = sum(d.get("downloads", 0) for d in ep.get("downloads", []))
            downloads[ep_id] = total

        log(f"  Fetched analytics for {len(downloads)} episodes")
        return downloads

    except Exception as e:
        log(f"  ERROR fetching from Transistor: {e}")
        return {}


# ── Update published.json ──────────────────────────────────────────────────────
def update_published_streams(downloads: dict) -> list:
    """Write real download counts back into published.json."""
    if not PUBLISHED_FILE.exists():
        return []

    with open(PUBLISHED_FILE) as f:
        records = json.load(f)

    updated = 0
    for r in records:
        ep_id = str(r.get("transistorEpisodeId", ""))
        if ep_id and ep_id in downloads:
            old = r.get("streams", 0)
            r["streams"] = downloads[ep_id]
            if r["streams"] != old:
                updated += 1

    with open(PUBLISHED_FILE, "w") as f:
        json.dump(records, f, indent=2)

    log(f"  Updated {updated} episode stream counts in published.json")
    return records


# ── Topic analysis ─────────────────────────────────────────────────────────────
STOPWORDS = {
    "how", "to", "in", "the", "a", "an", "and", "or", "for", "of", "with",
    "your", "you", "get", "use", "using", "gohighlevel", "highlevel",
    "agency", "guide", "from", "this", "that", "what", "when", "why",
    "more", "make", "start", "manage", "setup", "set",
}


def extract_keywords(title: str) -> list:
    words = re.findall(r'\b[a-z]+\b', title.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 3]


def build_topic_weights(records: list) -> dict:
    published = [r for r in records if r.get("status") == "published" and r.get("streams", 0) > 0]

    if not published:
        log("  No episodes with download data yet — skipping topic analysis")
        return {}

    # --- Category performance ---
    cat_data = defaultdict(list)
    for r in published:
        cat = r.get("category") or "Unknown"
        cat_data[cat].append(r.get("streams", 0))

    top_categories = sorted(
        [
            {
                "name": cat,
                "avg_downloads": round(sum(v) / len(v), 1),
                "total_downloads": sum(v),
                "episode_count": len(v),
            }
            for cat, v in cat_data.items()
        ],
        key=lambda x: x["avg_downloads"],
        reverse=True,
    )

    # --- Keyword performance (from titles of published episodes) ---
    kw_data = defaultdict(list)
    for r in published:
        title = r.get("seoTitle") or r.get("title", "")
        for kw in extract_keywords(title):
            kw_data[kw].append(r.get("streams", 0))

    top_keywords = sorted(
        [
            {
                "keyword": kw,
                "avg_downloads": round(sum(v) / len(v), 1),
                "episode_count": len(v),
            }
            for kw, v in kw_data.items()
            if len(v) >= 2
        ],
        key=lambda x: x["avg_downloads"],
        reverse=True,
    )[:20]

    # --- Summary ---
    all_streams = [r["streams"] for r in published]
    best = max(published, key=lambda r: r["streams"])

    weights = {
        "updated_at": datetime.now().isoformat(),
        "total_episodes_analyzed": len(published),
        "summary": {
            "total_downloads": sum(all_streams),
            "avg_downloads_per_episode": round(sum(all_streams) / len(all_streams), 1),
            "best_episode_title": best.get("seoTitle") or best.get("title", ""),
            "best_episode_downloads": max(all_streams),
        },
        "top_categories": top_categories[:10],
        "top_keywords": top_keywords,
        # Flat list used by 3-seo.py for quick prompt injection
        "hot_keywords": [kw["keyword"] for kw in top_keywords[:10]],
    }

    return weights


# ── Report ─────────────────────────────────────────────────────────────────────
def print_report(weights: dict):
    s = weights.get("summary", {})
    log(f"  Total downloads all-time: {s.get('total_downloads', 0)}")
    log(f"  Avg downloads per episode: {s.get('avg_downloads_per_episode', 0)}")
    log(f"  Best episode: {s.get('best_episode_title', 'N/A')} ({s.get('best_episode_downloads', 0)} downloads)")
    log("  Top categories by avg downloads:")
    for cat in weights.get("top_categories", [])[:5]:
        log(f"    {cat['avg_downloads']:>6.1f} avg — {cat['name']} ({cat['episode_count']} eps)")
    kws = weights.get("hot_keywords", [])
    if kws:
        log("  Hot keywords: " + ", ".join(kws[:8]))


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log("=" * 60)
    log("Analytics starting")

    if not TRANSISTOR_API_KEY or not TRANSISTOR_SHOW_ID:
        log("ERROR: TRANSISTOR_API_KEY or TRANSISTOR_SHOW_ID missing from .env")
        return

    log("Step 1/3 — Fetching episode downloads from Transistor...")
    downloads = fetch_episode_analytics()

    log("Step 2/3 — Updating stream counts in published.json...")
    records = update_published_streams(downloads)

    log("Step 3/3 — Building topic weights...")
    weights = build_topic_weights(records)

    if weights:
        with open(TOPIC_WEIGHTS_FILE, "w") as f:
            json.dump(weights, f, indent=2)
        log(f"  Saved topic-weights.json")
        print_report(weights)

    log("Analytics complete")
    log("=" * 60)


if __name__ == "__main__":
    main()
