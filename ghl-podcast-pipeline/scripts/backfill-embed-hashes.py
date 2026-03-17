"""
One-time backfill: fetch Transistor embed hashes for all episodes
and update blog post JSON files with the correct transistorEpisodeId.

The blog posts were using numeric Transistor IDs (e.g., 3076505) but
the embed URLs need the hash (e.g., 93df003f) from share.transistor.fm/e/{hash}.
"""

import json
import re
import time
import urllib.request
from pathlib import Path

API_KEY = "H9gHPjBGDqTDA7jHgK6_fg"
SHOW_ID = "75382"
BASE_DIR = Path(__file__).parent.parent
PUBLISHED = BASE_DIR / "data" / "published.json"
SITE_POSTS = BASE_DIR.parent / "globalhighlevel-site" / "posts"


def fetch_all_episodes():
    """Fetch all episodes from Transistor API with pagination."""
    episodes = []
    page = 1
    while True:
        url = f"https://api.transistor.fm/v1/episodes?show_id={SHOW_ID}&pagination[per]=25&pagination[page]={page}"
        req = urllib.request.Request(url, headers={"x-api-key": API_KEY})
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        batch = data.get("data", [])
        if not batch:
            break
        episodes.extend(batch)
        total_pages = data.get("meta", {}).get("totalPages", 1)
        print(f"  Fetched page {page}/{total_pages} ({len(batch)} episodes)")
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)  # be nice to the API
    return episodes


def extract_embed_hash(episode):
    """Extract embed hash from episode's embed_html attribute."""
    embed_html = episode.get("attributes", {}).get("embed_html", "")
    match = re.search(r'/e/([a-f0-9]+)', embed_html)
    return match.group(1) if match else ""


def main():
    print("Fetching all episodes from Transistor...")
    episodes = fetch_all_episodes()
    print(f"Got {len(episodes)} episodes total\n")

    # Build map: numeric_id -> embed_hash
    id_to_hash = {}
    for ep in episodes:
        ep_id = ep["id"]
        embed_hash = extract_embed_hash(ep)
        if embed_hash:
            id_to_hash[ep_id] = embed_hash

    print(f"Extracted {len(id_to_hash)} embed hashes\n")

    # Load published.json to get blogSlug -> transistorEpisodeId mapping
    published = json.load(open(PUBLISHED))
    slug_to_hash = {}
    for item in published:
        slug = item.get("blogSlug", "")
        tid = str(item.get("transistorEpisodeId", ""))
        if slug and tid and tid in id_to_hash:
            slug_to_hash[slug] = id_to_hash[tid]

    print(f"Matched {len(slug_to_hash)} blog posts to embed hashes\n")

    # Update published.json with embed hashes
    updated_published = 0
    for item in published:
        tid = str(item.get("transistorEpisodeId", ""))
        if tid in id_to_hash:
            item["transistorEmbedHash"] = id_to_hash[tid]
            updated_published += 1
    with open(PUBLISHED, "w") as f:
        json.dump(published, f, indent=2)
    print(f"Updated {updated_published} entries in published.json\n")

    # Update blog post JSON files
    updated = 0
    skipped = 0
    for post_file in sorted(SITE_POSTS.glob("*.json")):
        post = json.load(open(post_file))
        slug = post.get("slug", post_file.stem)
        if slug in slug_to_hash:
            post["transistorEpisodeId"] = slug_to_hash[slug]
            with open(post_file, "w") as f:
                json.dump(post, f, indent=2)
            updated += 1
        else:
            skipped += 1

    print(f"Updated {updated} blog post files")
    print(f"Skipped {skipped} (no matching episode)")


if __name__ == "__main__":
    main()
