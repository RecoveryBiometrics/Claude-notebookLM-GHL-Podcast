"""
batch-blog.py — Generate blog posts for ALL episodes missing from globalhighlevel.com

Reads published.json, checks which episodes already have a post in
globalhighlevel-site/posts/, and runs 5-blog.py's create_blog_post()
for each missing one.

Run:  venv/bin/python3 scripts/batch-blog.py
"""

import importlib.util
import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

BASE_DIR   = Path(__file__).parent.parent
PUBLISHED  = BASE_DIR / "data" / "published.json"
SITE_POSTS = BASE_DIR.parent / "globalhighlevel-site" / "posts"
LOG_FILE   = BASE_DIR / "logs" / "pipeline.log"


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [BATCH-BLOG] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_blog_module():
    path = Path(__file__).parent / "5-blog.py"
    spec = importlib.util.spec_from_file_location("blog", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    # Load published episodes
    with open(PUBLISHED) as f:
        episodes = json.load(f)

    # Find existing post slugs on disk
    existing_slugs = set()
    if SITE_POSTS.exists():
        for p in SITE_POSTS.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                existing_slugs.add(data.get("slug", ""))
                # Also track by articleId
                existing_slugs.add(str(data.get("articleId", "")))
            except Exception:
                pass

    # Also track by articleId from existing posts
    existing_article_ids = set()
    if SITE_POSTS.exists():
        for p in SITE_POSTS.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                aid = str(data.get("articleId", ""))
                if aid:
                    existing_article_ids.add(aid)
            except Exception:
                pass

    # Filter to episodes that need blog posts
    # Must have seoTitle + seoDescription (needed by 5-blog.py)
    # Must not already have a post file
    missing = []
    for ep in episodes:
        article_id = str(ep.get("articleId", ""))
        seo_title = ep.get("seoTitle", "")
        blog_slug = ep.get("blogSlug", "")
        status = ep.get("status", "")

        # Skip failed episodes
        if status == "failed":
            continue

        # Skip if no SEO title (minimum requirement)
        if not seo_title:
            continue

        # Ensure seoDescription exists (5-blog.py needs it)
        if not ep.get("seoDescription"):
            ep["seoDescription"] = ep.get("title", seo_title)

        # Skip if we already have a post for this article ID
        if article_id in existing_article_ids:
            continue

        # Skip if the blog slug file already exists on disk
        if blog_slug and (SITE_POSTS / f"{blog_slug}.json").exists():
            continue

        missing.append(ep)

    log(f"Total episodes: {len(episodes)}")
    log(f"Existing blog posts: {len(existing_article_ids)}")
    log(f"Missing blog posts: {len(missing)}")

    if not missing:
        log("All episodes have blog posts!")
        return

    # Load 5-blog.py
    blog = load_blog_module()

    succeeded = 0
    failed = 0

    for i, ep in enumerate(missing, 1):
        title = ep.get("seoTitle", "Unknown")
        log(f"\n{'='*60}")
        log(f"[{i}/{len(missing)}] {title[:70]}")

        try:
            result = blog.create_blog_post(ep)
            slug = result.get("blogSlug", "")
            log(f"  ✓ Blog post saved: {slug}")
            succeeded += 1

            # Update published.json with blog info
            ep["blogSlug"] = result.get("blogSlug", "")
            ep["blogPostId"] = result.get("blogPostId", "")
            ep["blogPostedAt"] = result.get("blogPostedAt", "")

        except Exception as e:
            log(f"  ✗ FAILED: {e}")
            failed += 1

        # Save published.json after each post (in case of crash)
        with open(PUBLISHED, "w") as f:
            json.dump(episodes, f, indent=2)

        # Rate limit: 3 second pause between posts
        if i < len(missing):
            time.sleep(3)

    log(f"\n{'='*60}")
    log(f"BATCH COMPLETE: {succeeded} succeeded, {failed} failed, {len(missing)} total")


if __name__ == "__main__":
    main()
