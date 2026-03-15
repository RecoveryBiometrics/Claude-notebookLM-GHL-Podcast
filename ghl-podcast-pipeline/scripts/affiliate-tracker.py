"""
affiliate-tracker.py
Logs into app.gohighlevel.com, navigates to the Affiliate Portal → Promoter Reports,
and scrapes: Referrals, Customers, Clicks, Unpaid Earnings.

Saves a daily snapshot to data/affiliate-stats.json.

Run:
  venv/bin/python3 scripts/affiliate-tracker.py           # headless
  venv/bin/python3 scripts/affiliate-tracker.py --headed  # show browser (debug)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
STATS_FILE = DATA_DIR / "affiliate-stats.json"
SCREENSHOT_DIR = BASE_DIR / "logs"

GHL_EMAIL = os.getenv("GHL_EMAIL")
GHL_PASSWORD = os.getenv("GHL_PASSWORD")


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [AFFILIATE] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def save_screenshot(page, name: str):
    path = SCREENSHOT_DIR / f"affiliate-{name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    try:
        page.screenshot(path=str(path))
        log(f"  Screenshot saved: {path.name}")
    except Exception:
        pass


def load_existing_stats() -> list:
    if STATS_FILE.exists():
        with open(STATS_FILE) as f:
            return json.load(f)
    return []


def save_stats(stats: list):
    DATA_DIR.mkdir(exist_ok=True)
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


def scrape_affiliate_data(headed: bool = False) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        try:
            # ── Step 1: Login ──────────────────────────────────────────────
            log("Step 1/4 — Logging into app.gohighlevel.com...")
            page.goto("https://app.gohighlevel.com/", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)

            # Fill login form
            page.fill('input[type="email"], input[name="email"], #email', GHL_EMAIL)
            page.fill('input[type="password"], input[name="password"], #password', GHL_PASSWORD)
            page.click('button[type="submit"], button:has-text("Sign In"), button:has-text("Login")')
            page.wait_for_load_state("networkidle", timeout=30000)

            # Check for 2FA prompt
            if page.locator('input[placeholder*="code"], input[placeholder*="verification"]').count() > 0:
                save_screenshot(page, "2fa-required")
                log("ERROR: Two-factor authentication prompt detected. Disable 2FA or handle manually.")
                browser.close()
                return {}

            log("  Logged in successfully")
            save_screenshot(page, "post-login")

            # ── Step 2: Navigate to Affiliate Portal ───────────────────────
            log("Step 2/4 — Navigating to Affiliate Portal...")

            # Try direct URL first
            page.goto("https://app.gohighlevel.com/affiliate-portal", timeout=20000)
            page.wait_for_load_state("networkidle", timeout=20000)

            # If redirected away, try clicking through the menu
            if "affiliate" not in page.url:
                page.goto("https://app.gohighlevel.com/", timeout=20000)
                page.wait_for_load_state("networkidle", timeout=20000)

                affiliate_link = page.locator('a:has-text("Affiliate"), [href*="affiliate"]').first
                affiliate_link.click(timeout=10000)
                page.wait_for_load_state("networkidle", timeout=20000)

            log(f"  Current URL: {page.url}")
            save_screenshot(page, "affiliate-portal")

            # ── Step 3: Click Promoter Reports ────────────────────────────
            log("Step 3/4 — Opening Promoter Reports...")

            page.locator('text=Promoter Reports, a:has-text("Reports"), button:has-text("Reports")').first.click(timeout=15000)
            page.wait_for_load_state("networkidle", timeout=20000)
            save_screenshot(page, "promoter-reports")

            # Make sure "High Level Affiliate Program" is selected if there's a dropdown
            program_selector = page.locator('select, [role="listbox"], [role="combobox"]').first
            if program_selector.count() > 0:
                try:
                    program_selector.select_option(label="High Level Affiliate Program")
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass  # Already selected or not needed

            save_screenshot(page, "program-selected")

            # ── Step 4: Scrape the stats ───────────────────────────────────
            log("Step 4/4 — Scraping affiliate stats...")

            # Wait for stats to load
            page.wait_for_timeout(3000)
            save_screenshot(page, "stats-page")

            def extract_stat(labels: list) -> str:
                """Try multiple label variations to find a stat value."""
                for label in labels:
                    # Look for a card/tile with this label
                    el = page.locator(f'text="{label}"').first
                    if el.count() > 0:
                        # Get the parent container and find the number inside it
                        parent = el.locator("xpath=../..")
                        num = parent.locator("h1, h2, h3, h4, strong, .stat-value, .count, [class*=\"value\"], [class*=\"number\"]").first
                        if num.count() > 0:
                            return num.inner_text().strip()
                return "N/A"

            referrals = extract_stat(["Referrals", "Total Referrals"])
            customers = extract_stat(["Customers", "Total Customers", "Active Customers"])
            clicks = extract_stat(["Clicks", "Total Clicks", "Link Clicks"])
            unpaid_earnings = extract_stat(["Unpaid Earnings", "Unpaid", "Pending Earnings", "Balance"])

            stats = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "scraped_at": datetime.now().isoformat(),
                "referrals": referrals,
                "customers": customers,
                "clicks": clicks,
                "unpaid_earnings": unpaid_earnings,
                "url": page.url,
            }

            log(f"  Referrals:       {referrals}")
            log(f"  Customers:       {customers}")
            log(f"  Clicks:          {clicks}")
            log(f"  Unpaid Earnings: {unpaid_earnings}")

            browser.close()
            return stats

        except PlaywrightTimeout as e:
            save_screenshot(page, "timeout-error")
            log(f"ERROR: Timeout — {e}")
            browser.close()
            return {}

        except Exception as e:
            save_screenshot(page, "error")
            log(f"ERROR: {e}")
            browser.close()
            return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="Show browser window (for debugging)")
    args = parser.parse_args()

    log("=" * 60)
    log("Affiliate tracker starting")

    if not GHL_EMAIL or not GHL_PASSWORD:
        log("ERROR: GHL_EMAIL or GHL_PASSWORD missing from .env")
        sys.exit(1)

    stats = scrape_affiliate_data(headed=args.headed)

    if not stats:
        log("ERROR: No data scraped — check screenshots in logs/")
        sys.exit(1)

    # Append today's snapshot (replace if same date already exists)
    all_stats = load_existing_stats()
    today = stats["date"]
    all_stats = [s for s in all_stats if s.get("date") != today]
    all_stats.append(stats)
    all_stats.sort(key=lambda s: s["date"])

    save_stats(all_stats)
    log(f"  Saved to {STATS_FILE}")
    log("Affiliate tracker complete")
    log("=" * 60)


if __name__ == "__main__":
    main()
