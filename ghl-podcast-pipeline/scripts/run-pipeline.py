"""
run-pipeline.py
Scrape one article → NotebookLM audio → SEO → Upload to Transistor → loop.
Runs 20 episodes per day, skips already-published articles.

Run: venv/bin/python3 scripts/run-pipeline.py
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

from dotenv import load_dotenv

load_dotenv()

# CONTENT VELOCITY PAUSE — set 2026-04-28. See scheduler.py header for context.
# When True: NotebookLM + SEO + Transistor upload still run (audio podcast lives),
# but Step 4 (blog post creation on globalhighlevel.com) is skipped.
# Resume: flip to False and scp to VPS. Expected resume 2026-05-19.
PAUSE_BLOG_POST_FROM_PODCAST = True

BASE_DIR = Path(__file__).parent.parent
PUBLISHED_FILE = BASE_DIR / "data" / "published.json"
ARTICLES_CACHE = BASE_DIR / "data" / "articles-cache.json"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
SCRIPTS_DIR = Path(__file__).parent

EPISODES_PER_DAY = 20
CACHE_MAX_AGE_HOURS = 24


# ── Load sibling scripts by file path (they start with numbers) ───────────────
def load_script(name: str):
    path = SCRIPTS_DIR / name
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [PIPELINE] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Published log ─────────────────────────────────────────────────────────────
def load_published() -> list:
    if PUBLISHED_FILE.exists():
        with open(PUBLISHED_FILE) as f:
            return json.load(f)
    return []


def save_published(records: list):
    with open(PUBLISHED_FILE, "w") as f:
        json.dump(records, f, indent=2)


def count_published_today(published: list) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    return sum(1 for r in published if r.get("uploadedAt", "").startswith(today))


# ── Article Discovery Cache ───────────────────────────────────────────────────
def cache_is_fresh() -> bool:
    """Returns True if the articles cache exists and is less than CACHE_MAX_AGE_HOURS old."""
    if not ARTICLES_CACHE.exists():
        return False
    age_seconds = datetime.now().timestamp() - ARTICLES_CACHE.stat().st_mtime
    return age_seconds < CACHE_MAX_AGE_HOURS * 3600


def load_cache() -> list:
    if ARTICLES_CACHE.exists():
        with open(ARTICLES_CACHE) as f:
            return json.load(f)
    return []


def save_cache(articles: list):
    with open(ARTICLES_CACHE, "w") as f:
        json.dump(articles, f, indent=2)


async def build_articles_cache() -> list:
    """
    Crawl ALL GHL help article pages: solutions index → category folders → subcategory folders → articles.
    Returns list of {id, url} sorted by article ID descending (newest first).
    """
    from playwright.async_api import async_playwright

    BASE_URL = "https://help.gohighlevel.com"
    SOLUTIONS_URL = f"{BASE_URL}/support/solutions"

    log("Building articles cache — crawling all GHL help pages...")

    all_article_urls = set()
    visited_folders = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))

        # Step 1: Get all category folder links from the solutions index
        log("  Loading solutions index...")
        await page.goto(SOLUTIONS_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)

        # Collect article links directly on the solutions page
        direct_articles = await page.eval_on_selector_all(
            "a[href*='/support/solutions/articles/']",
            "els => els.map(e => e.href)"
        )
        all_article_urls.update(direct_articles)

        # Collect all category/subcategory folder links
        folder_links = await page.eval_on_selector_all(
            "a[href*='/support/solutions/folders/']",
            "els => els.map(e => e.href)"
        )
        folders_to_visit = list(set(folder_links))
        log(f"  Found {len(folders_to_visit)} category folders to crawl")

        # Step 2: Visit each folder to find articles and sub-folders
        for i, folder_url in enumerate(folders_to_visit):
            if folder_url in visited_folders:
                continue
            visited_folders.add(folder_url)

            try:
                await page.goto(folder_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(1)

                # Articles on this folder page
                articles = await page.eval_on_selector_all(
                    "a[href*='/support/solutions/articles/']",
                    "els => els.map(e => e.href)"
                )
                all_article_urls.update(articles)

                # Sub-folder links (go one level deeper)
                sub_folders = await page.eval_on_selector_all(
                    "a[href*='/support/solutions/folders/']",
                    "els => els.map(e => e.href)"
                )
                for sf in sub_folders:
                    if sf not in visited_folders:
                        folders_to_visit.append(sf)
                        visited_folders.add(sf)

                if (i + 1) % 10 == 0:
                    log(f"  Crawled {i + 1}/{len(folders_to_visit)} folders, {len(all_article_urls)} articles found so far...")

            except Exception as e:
                log(f"  Warning: could not crawl {folder_url}: {e}")
                continue

        await browser.close()

    # Extract numeric IDs and sort descending (highest ID = newest article)
    articles = []
    for url in all_article_urls:
        m = re.search(r"/articles/(\d+)", url)
        if m:
            article_id = m.group(1)
            # Normalize URL to remove trailing slugs
            clean_url = f"{BASE_URL}/support/solutions/articles/{article_id}"
            articles.append({"id": article_id, "url": clean_url})

    # Deduplicate by ID, sort newest first
    seen_ids = set()
    unique = []
    for a in articles:
        if a["id"] not in seen_ids:
            seen_ids.add(a["id"])
            unique.append(a)

    unique.sort(key=lambda x: int(x["id"]), reverse=True)

    save_cache(unique)
    log(f"  Cache built: {len(unique)} unique articles found, sorted newest first")
    return unique


# ── Scrape one article ────────────────────────────────────────────────────────
async def scrape_one(published_ids: set) -> dict | None:
    from playwright.async_api import async_playwright

    BASE_URL = "https://help.gohighlevel.com"

    # Use cache if fresh, otherwise rebuild
    if cache_is_fresh():
        all_articles = load_cache()
        log(f"Using articles cache ({len(all_articles)} articles)")
    else:
        all_articles = await build_articles_cache()

    # Pick the first article not yet published (cache is already sorted newest first)
    target = None
    for entry in all_articles:
        if entry["id"] not in published_ids:
            target = entry
            break

    if not target:
        log("No more unprocessed articles in cache.")
        return None

    # Scrape the article content
    log(f"Scraping: {target['url']}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))

        await page.goto(target["url"], wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)

        title = (await page.title()).replace(
            " – GoHighLevel Support", ""
        ).replace(" | GoHighLevel", "").strip()

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

        category = ""
        try:
            crumbs = await page.eval_on_selector_all(
                "[class*='breadcrumb'] a",
                "els => els.map(e => e.innerText.trim())"
            )
            category = crumbs[0] if crumbs else ""
        except Exception:
            pass

        await browser.close()

    return {
        "id": target["id"],
        "title": title,
        "url": target["url"],
        "category": category,
        "subcategory": "",
        "body": body,
        "scraped": datetime.now().strftime("%Y-%m-%d"),
    }


# ── Process one article through full pipeline ─────────────────────────────────
async def process_one(article: dict, published_today: int) -> dict | None:
    notebooklm = load_script("2-notebooklm.py")
    seo = load_script("3-seo.py")
    upload = load_script("4-upload.py")
    blog = load_script("5-blog.py")

    log(f"{'='*50}")
    log(f"Article: {article['title']}")
    log(f"Category: {article.get('category', 'Unknown')}")

    # Step 1: NotebookLM + Drive upload
    log("Step 1/3 — Generating audio via NotebookLM")
    result = await notebooklm.process_article(article)
    if not result:
        log(f"FAILED at NotebookLM — halting cycle")
        return {"status": "notebooklm_failed"}
    time.sleep(3)

    # Step 2: SEO agents
    log("Step 2/3 — SEO Writer + Reviewer")
    try:
        result = seo.generate_seo(result)
    except Exception as e:
        log(f"FAILED at SEO: {e}")
        return None
    time.sleep(3)

    # Step 3: Upload to Transistor
    log("Step 3/4 — Uploading to Transistor.fm")
    try:
        result = upload.upload_episode(result, published_today)
    except Exception as e:
        log(f"FAILED at upload: {e}")
        # Return partial result so driveAudioId is preserved in published.json
        result["status"] = "upload_failed"
        return result

    log(f"✓ PUBLISHED: {result.get('seoTitle', '')}")
    log(f"  Transistor ID: {result.get('transistorEpisodeId')}")
    log(f"  Scheduled: {result.get('publishedAt')}")

    # Step 4: Blog post
    if PAUSE_BLOG_POST_FROM_PODCAST:
        log("Step 4/4 — Blog post creation SKIPPED — PAUSE_BLOG_POST_FROM_PODCAST=True (Apr 24 GSC cliff recovery)")
    else:
        log("Step 4/4 — Publishing blog post to reiamplifi.com")
        try:
            result = blog.create_blog_post(result)
            log(f"  Blog post live — ID: {result.get('blogPostId')} slug: /{result.get('blogSlug')}")
        except Exception as e:
            log(f"  Blog post FAILED (non-fatal): {e}")
            # Blog failure doesn't kill the pipeline — episode is already published

    return result


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    log("=" * 60)
    log("GHL Podcast Pipeline starting")

    published = load_published()
    published_ids = {r["articleId"] for r in published}
    published_today = count_published_today(published)

    log(f"Published all time: {len(published)} | Today: {published_today}/{EPISODES_PER_DAY}")

    if published_today >= EPISODES_PER_DAY:
        log("Daily limit reached. Run again tomorrow.")
        return

    episodes_to_do = EPISODES_PER_DAY - published_today
    completed = 0
    failed = 0
    consecutive_upload_failures = 0
    MAX_CONSECUTIVE_UPLOAD_FAILURES = 3

    for i in range(episodes_to_do):
        log(f"\nEpisode {i + 1}/{episodes_to_do}")

        article = await scrape_one(published_ids)
        if not article:
            log("No more unprocessed articles found.")
            break

        if len(article.get("body", "")) < 100:
            log(f"Skipping — no content: {article.get('title')}")
            published_ids.add(article["id"])
            continue

        result = await process_one(article, published_today + completed)

        if result and result.get("status") == "published":
            published.append({
                "articleId": result["id"],
                "title": result["title"],
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
                "blogPostId": result.get("blogPostId"),
                "blogSlug": result.get("blogSlug"),
                "streams": 0,
            })
            published_ids.add(result["id"])
            completed += 1
            consecutive_upload_failures = 0
        elif result and result.get("status") == "upload_failed":
            # Audio is on Drive but Transistor upload failed — save driveAudioId for retry
            published.append({
                "articleId": result["id"],
                "title": result.get("title", ""),
                "category": result.get("category", ""),
                "status": "failed",
                "failedAt": datetime.now().isoformat(),
                "driveAudioId": result.get("driveAudioId"),
                "driveJsonId": result.get("driveJsonId"),
                "seoTitle": result.get("seoTitle"),
                "seoDescription": result.get("seoDescription"),
                "seoTags": result.get("seoTags"),
            })
            published_ids.add(result["id"])
            failed += 1
            consecutive_upload_failures += 1
            if consecutive_upload_failures >= MAX_CONSECUTIVE_UPLOAD_FAILURES:
                log(f"ERROR: {MAX_CONSECUTIVE_UPLOAD_FAILURES} consecutive upload failures.")
                log("Halting pipeline. Run retry-failed.py after fixing the issue.")
                save_published(published)
                return
        elif result and result.get("status") == "notebooklm_failed":
            # NotebookLM timed out or hit API limits — stop now, let it rest until next cycle
            published.append({
                "articleId": article["id"],
                "title": article.get("title", ""),
                "status": "failed",
                "failedAt": datetime.now().isoformat(),
            })
            published_ids.add(article["id"])
            failed += 1
            log("ERROR: NotebookLM failure — halting pipeline. Will retry next cycle.")
            save_published(published)
            return
        else:
            # Check if failure was at upload stage (audio on Drive but no Transistor ID)
            drive_id = None
            for r in published:
                if r.get("articleId") == article["id"]:
                    drive_id = r.get("driveAudioId")
                    break

            failed_record = {
                "articleId": article["id"],
                "title": article.get("title", ""),
                "status": "failed",
                "failedAt": datetime.now().isoformat(),
            }
            # If audio made it to Drive, save the ID so retry-failed.py can recover it
            if drive_id:
                failed_record["driveAudioId"] = drive_id

            published.append(failed_record)
            published_ids.add(article["id"])
            failed += 1

            # Check log for consecutive upload failures to stop burning NotebookLM credits
            recent_log = LOG_FILE.read_text().splitlines()[-10:]
            if any("FAILED at upload" in l for l in recent_log):
                consecutive_upload_failures += 1
                if consecutive_upload_failures >= MAX_CONSECUTIVE_UPLOAD_FAILURES:
                    log(f"ERROR: {MAX_CONSECUTIVE_UPLOAD_FAILURES} consecutive upload failures.")
                    log("Halting pipeline. Run retry-failed.py after fixing the issue.")
                    save_published(published)
                    return
            else:
                consecutive_upload_failures = 0

        save_published(published)

        if i < episodes_to_do - 1:
            log("Cooling down 2 min before next episode (NotebookLM queue)...")
            time.sleep(120)

    log(f"\nDone — {completed} published, {failed} failed")
    log("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
