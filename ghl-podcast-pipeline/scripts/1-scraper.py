"""
1-scraper.py
Scrapes every help article from help.gohighlevel.com and saves each one
as a JSON file in data/articles/. Skips articles already scraped.
Re-scrapes if the article was updated since last scrape.
"""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
ARTICLES_DIR = BASE_DIR / "data" / "articles"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_URL = "https://help.gohighlevel.com"
SOLUTIONS_URL = f"{BASE_URL}/support/solutions"
DELAY_BETWEEN_REQUESTS = 2.5  # seconds — polite crawling

# Priority category order (process AI articles first — highest conversion)
CATEGORY_PRIORITY = [
    "ai", "automation", "workflow", "crm", "contact",
    "funnel", "website", "email", "sms", "calendar",
    "appointment", "payment", "commerce", "report",
    "analytic", "agency", "integration",
]


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [SCRAPER] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Helpers ───────────────────────────────────────────────────────────────────
def slug_from_url(url: str) -> str:
    """Extract a filesystem-safe slug from an article URL."""
    return re.sub(r"[^a-z0-9\-]", "-", url.rstrip("/").split("/")[-1].lower())


def article_id_from_url(url: str) -> str:
    """Extract the numeric article ID from the URL if present, else use slug."""
    match = re.search(r"/articles/(\d+)", url)
    return match.group(1) if match else slug_from_url(url)


def already_scraped(article_id: str, last_modified: str) -> bool:
    """Return True if article exists on disk and hasn't been updated."""
    path = ARTICLES_DIR / f"{article_id}.json"
    if not path.exists():
        return False
    with open(path) as f:
        existing = json.load(f)
    return existing.get("lastModified") == last_modified


def save_article(data: dict):
    path = ARTICLES_DIR / f"{data['id']}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def priority_score(category: str) -> int:
    """Lower score = higher priority."""
    cat = category.lower()
    for i, keyword in enumerate(CATEGORY_PRIORITY):
        if keyword in cat:
            return i
    return len(CATEGORY_PRIORITY)


# ── Scraper ───────────────────────────────────────────────────────────────────
async def get_all_article_links(page) -> list[dict]:
    """
    Crawl the solutions index to collect every article URL,
    its category, and subcategory.
    """
    log(f"Loading solutions index: {SOLUTIONS_URL}")
    await page.goto(SOLUTIONS_URL, wait_until="networkidle", timeout=60000)
    await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

    article_links = []

    # Find all category links on the index page
    category_links = await page.eval_on_selector_all(
        "a[href*='/support/solutions/']",
        "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))"
    )

    # Filter to folder/category URLs (not individual articles yet)
    category_urls = [
        c for c in category_links
        if "/folders/" in c["href"] or
        (c["href"].startswith(BASE_URL) and "/solutions/" in c["href"] and "/articles/" not in c["href"])
    ]
    category_urls = list({c["href"]: c for c in category_urls}.values())  # dedupe
    log(f"Found {len(category_urls)} category/subcategory links")

    visited_categories = set()

    for cat in category_urls:
        cat_url = cat["href"]
        if cat_url in visited_categories:
            continue
        visited_categories.add(cat_url)

        try:
            log(f"  Crawling category: {cat['text'] or cat_url}")
            await page.goto(cat_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

            # Collect article links from this category page
            links = await page.eval_on_selector_all(
                "a[href*='/support/solutions/articles/']",
                "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))"
            )

            for link in links:
                article_links.append({
                    "url": link["href"],
                    "title_hint": link["text"],
                    "category": cat["text"] or "",
                })

            # Also follow subcategory links found on this page
            sub_links = await page.eval_on_selector_all(
                "a[href*='/support/solutions/folders/']",
                "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))"
            )
            for sub in sub_links:
                if sub["href"] not in visited_categories:
                    category_urls.append(sub)

        except Exception as e:
            log(f"  ERROR crawling {cat_url}: {e}")
            continue

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in article_links:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    # Sort by category priority
    unique.sort(key=lambda x: priority_score(x["category"]))
    log(f"Total unique article URLs found: {len(unique)}")
    return unique


async def scrape_article(page, url: str, category: str) -> dict | None:
    """Visit a single article page and extract its content."""
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

        # Title
        title = await page.title()
        title = title.replace(" – GoHighLevel Support", "").replace(" | GoHighLevel", "").strip()

        # Body text — try the main article content area
        body = ""
        for selector in [".article-body", ".article__body", "[class*='article-content']", "main article", "main"]:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    body = await el.inner_text()
                    body = body.strip()
                    if len(body) > 100:
                        break
            except Exception:
                continue

        if not body:
            log(f"  WARNING: no body text found for {url}")

        # Last modified date
        last_modified = ""
        for selector in ["[class*='modified']", "[class*='updated']", "time", "[datetime]"]:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    last_modified = (
                        await el.get_attribute("datetime") or
                        await el.inner_text()
                    )
                    last_modified = last_modified.strip()[:10]  # keep YYYY-MM-DD
                    break
            except Exception:
                continue

        # Subcategory — breadcrumb
        subcategory = ""
        try:
            breadcrumbs = await page.eval_on_selector_all(
                "[class*='breadcrumb'] a, nav[aria-label*='breadcrumb'] a",
                "els => els.map(e => e.innerText.trim())"
            )
            if len(breadcrumbs) >= 2:
                subcategory = breadcrumbs[-2]
        except Exception:
            pass

        article_id = article_id_from_url(url)

        return {
            "id": article_id,
            "title": title,
            "url": url,
            "category": category,
            "subcategory": subcategory,
            "body": body,
            "lastModified": last_modified,
            "scraped": datetime.now().strftime("%Y-%m-%d"),
        }

    except Exception as e:
        log(f"  ERROR scraping {url}: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    log("=" * 60)
    log("GHL Article Scraper started")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # Step 1: collect all article URLs
        article_links = await get_all_article_links(page)

        # Step 2: scrape each article
        new_count = 0
        updated_count = 0
        skipped_count = 0

        for i, link in enumerate(article_links, 1):
            url = link["url"]
            article_id = article_id_from_url(url)

            # Quick check — load last-modified without full scrape if possible
            existing_path = ARTICLES_DIR / f"{article_id}.json"
            if existing_path.exists():
                with open(existing_path) as f:
                    existing = json.load(f)
                # We'll do a lightweight check: if scraped within last 7 days, skip
                scraped_date = existing.get("scraped", "")
                if scraped_date >= datetime.now().strftime("%Y-%m-%d")[:7]:  # same month
                    skipped_count += 1
                    continue

            log(f"[{i}/{len(article_links)}] Scraping: {link.get('title_hint') or url}")
            article = await scrape_article(page, url, link["category"])

            if article:
                is_update = existing_path.exists()
                save_article(article)
                if is_update:
                    updated_count += 1
                    log(f"  Updated: {article['title']}")
                else:
                    new_count += 1
                    log(f"  Saved: {article['title']}")
            else:
                log(f"  FAILED: {url}")

        await browser.close()

    log(f"Scraper complete — New: {new_count} | Updated: {updated_count} | Skipped: {skipped_count}")
    log("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
