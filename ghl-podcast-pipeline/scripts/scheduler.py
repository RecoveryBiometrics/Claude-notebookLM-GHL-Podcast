"""
scheduler.py
Runs the pipeline on a 25-hour cycle indefinitely.

Cycle order:
  0. analytics.py     — pull Transistor download data, update topic weights
  1. retry-failed.py  — recover any partial failures from previous run
  2. run-pipeline.py  — generate + publish today's batch of 20 episodes
  3. 6-india-blog.py  — publish 5 India blog topics
  4. deploy_site()    — git push new posts/ JSON → Netlify rebuilds globalhighlevel.com
  5. Send daily email summary to bill@reiamplifi.com
  6. Sleep until 25 hours after cycle started
  7. Repeat forever

Safe restarts: saves last run time to logs/scheduler-state.json.
If restarted early, waits out the remaining time before running again.

Setup (one time):
  1. Add GMAIL_APP_PASSWORD to .env
  2. Run: systemctl --user enable ghl-podcast
  3. Run: systemctl --user start ghl-podcast

Manual run:
  nohup venv/bin/python3 scripts/scheduler.py > logs/scheduler.log 2>&1 &

Stop:
  kill $(cat logs/scheduler.pid)
"""

import asyncio
import importlib.util
import json
import os
import smtplib
import ssl
import subprocess
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
SCRIPTS_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "logs" / "scheduler-state.json"
PUBLISHED_FILE = BASE_DIR / "data" / "published.json"
TOPIC_WEIGHTS_FILE = BASE_DIR / "data" / "topic-weights.json"
GSC_DATA_FILE = BASE_DIR / "data" / "gsc-stats.json"

CYCLE_HOURS = 25
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [SCHEDULER] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── State file (safe restarts) ────────────────────────────────────────────────
def save_state(cycle_started: datetime):
    next_due = cycle_started + timedelta(hours=CYCLE_HOURS)
    state = {
        "last_cycle_started": cycle_started.isoformat(),
        "next_cycle_due": next_due.isoformat(),
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def seconds_until_next_cycle() -> float:
    """
    Returns how many seconds to wait before starting the next cycle.
    0 if it's already been 25 hours (or no state file yet).
    """
    if not STATE_FILE.exists():
        return 0
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        next_due = datetime.fromisoformat(state["next_cycle_due"])
        remaining = (next_due - datetime.now()).total_seconds()
        return max(0, remaining)
    except Exception:
        return 0


# ── Daily email summary ───────────────────────────────────────────────────────
def build_summary(cycle_num: int, next_run: datetime) -> str:
    """Build the daily summary text from published.json and recent logs."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Count from published.json
    published_today = 0
    failed_today = 0
    total_published = 0
    total_failed = 0
    episode_titles = []

    total_blogs = 0
    blogs_today = 0
    total_streams = 0
    india_blogs_today = 0
    india_blogs_total = 0

    if PUBLISHED_FILE.exists():
        with open(PUBLISHED_FILE) as f:
            records = json.load(f)
        for r in records:
            if r.get("status") == "published":
                total_published += 1
                total_streams += r.get("streams", 0)
                uploaded = r.get("uploadedAt", "")
                if uploaded.startswith(today):
                    published_today += 1
                    title = r.get("seoTitle", r.get("title", ""))
                    if title:
                        episode_titles.append(f"  • {title[:70]}")
                if r.get("blogPostId"):
                    total_blogs += 1
                    if uploaded.startswith(today):
                        blogs_today += 1
            elif r.get("status") == "failed":
                total_failed += 1
                uploaded = r.get("failedAt", r.get("uploadedAt", ""))
                if uploaded.startswith(today):
                    failed_today += 1

    # Pull recent errors from log
    error_lines = []
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().splitlines()
        for line in lines[-200:]:
            if "FAILED" in line or "ERROR" in line:
                error_lines.append(f"  {line.strip()}")
        error_lines = error_lines[-5:]  # last 5 errors only

    titles_text = "\n".join(episode_titles[:20]) if episode_titles else "  (none today)"
    errors_text = "\n".join(error_lines) if error_lines else "  None"

    # Count India blog stats
    india_file = BASE_DIR / "data" / "india-published.json"
    if india_file.exists():
        with open(india_file) as f:
            india_records = json.load(f)
        for r in india_records:
            if r.get("blogPostId"):
                india_blogs_total += 1
                if r.get("publishedAt", "").startswith(today):
                    india_blogs_today += 1

    needs_action = failed_today > 0 and total_failed > 0

    # --- Site updates section ---
    site_text = ""
    site_posts_dir = BASE_DIR.parent / "globalhighlevel-site" / "posts"
    categories_file = BASE_DIR.parent / "globalhighlevel-site" / "categories.json"
    if site_posts_dir.exists():
        try:
            site_posts = []
            new_today = []
            for f in sorted(site_posts_dir.glob("*.json")):
                try:
                    data = json.loads(f.read_text())
                    site_posts.append(data)
                    pub_date = data.get("publishedAt", "")
                    if pub_date.startswith(today):
                        new_today.append(data.get("title", data.get("slug", "")))
                except Exception:
                    pass

            # Category breakdown
            cat_counts = {}
            for sp in site_posts:
                cat = sp.get("category", "Uncategorized")
                cat_counts[cat] = cat_counts.get(cat, 0) + 1

            # Sort by count descending
            cat_lines = "\n".join(
                f"  {count:>3} — {cat}"
                for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1])
            )

            new_today_text = "\n".join(f"  • {t[:70]}" for t in new_today) if new_today else "  (none today)"

            site_text = f"""
GLOBALHIGHLEVEL.COM
  Total posts live:     {len(site_posts)}
  New today:            {len(new_today)}
  Categories:           {len(cat_counts)}

  Posts by category:
{cat_lines}

  New posts deployed today:
{new_today_text}
"""
        except Exception:
            site_text = ""

    # --- Analytics section ---
    analytics_text = ""
    if TOPIC_WEIGHTS_FILE.exists():
        try:
            with open(TOPIC_WEIGHTS_FILE) as f:
                weights = json.load(f)
            s = weights.get("summary", {})
            top_cats = weights.get("top_categories", [])[:5]
            hot_kws = weights.get("hot_keywords", [])[:8]

            cat_lines = "\n".join(
                f"  {c['avg_downloads']:>6.1f} avg — {c['name']} ({c['episode_count']} eps)"
                for c in top_cats
            ) or "  (not enough data yet)"

            analytics_text = f"""
ANALYTICS (all-time)
  Total downloads:      {s.get('total_downloads', 0)}
  Avg per episode:      {s.get('avg_downloads_per_episode', 0)}
  Best episode:         {s.get('best_episode_title', 'N/A')[:60]}
  Best episode DLs:     {s.get('best_episode_downloads', 0)}

TOP CATEGORIES (by avg downloads)
{cat_lines}

HOT KEYWORDS (SEO is targeting these)
  {', '.join(hot_kws) or 'not enough data yet'}
"""
        except Exception:
            analytics_text = ""

    # --- Top 20 podcast episodes by downloads ---
    top_episodes_text = ""
    if PUBLISHED_FILE.exists():
        try:
            with open(PUBLISHED_FILE) as f:
                all_eps = json.load(f)
            eps_with_streams = [
                e for e in all_eps
                if e.get("status") == "published" and e.get("streams", 0) > 0
            ]
            eps_with_streams.sort(key=lambda x: x.get("streams", 0), reverse=True)
            top_20 = eps_with_streams[:20]
            if top_20:
                ep_lines = "\n".join(
                    f"  {e.get('streams', 0):>6} — {(e.get('seoTitle') or e.get('title', ''))[:60]}"
                    for e in top_20
                )
                top_episodes_text = f"""
TOP 20 PODCAST EPISODES (by downloads)
{ep_lines}
"""
        except Exception:
            top_episodes_text = ""

    # --- Google Search Console ---
    gsc_text = ""
    if GSC_DATA_FILE.exists():
        try:
            with open(GSC_DATA_FILE) as f:
                gsc = json.load(f)
            t = gsc.get("totals", {})
            period = gsc.get("period", "last 28 days")

            # Top pages by clicks
            top_pages = gsc.get("pages", [])[:10]
            page_lines = "\n".join(
                f"  {p['clicks']:>4} clicks | {p['impressions']:>6} imp | pos {p['position']:>4} — {p['page'].replace('https://globalhighlevel.com','')[:50]}"
                for p in top_pages
            ) or "  (no data yet)"

            # Top queries
            top_queries = gsc.get("queries", [])[:15]
            query_lines = "\n".join(
                f"  {q['clicks']:>4} clicks | {q['impressions']:>6} imp | pos {q['position']:>4} — {q['query'][:50]}"
                for q in top_queries
            ) or "  (no data yet)"

            # Category rollup — match page URLs to categories
            categories_file = BASE_DIR.parent / "globalhighlevel-site" / "categories.json"
            cat_rollup_text = ""
            if categories_file.exists():
                cats = json.loads(categories_file.read_text())
                site_posts_dir = BASE_DIR.parent / "globalhighlevel-site" / "posts"
                # Build slug→category map
                slug_to_cat = {}
                if site_posts_dir.exists():
                    for pf in site_posts_dir.glob("*.json"):
                        try:
                            pd = json.loads(pf.read_text())
                            slug_to_cat[pd.get("slug", "")] = pd.get("category", "")
                        except Exception:
                            pass

                # Aggregate GSC data by category
                cat_clicks = {}
                cat_impressions = {}
                for page_data in gsc.get("pages", []):
                    url = page_data["page"]
                    # Extract slug from URL
                    slug_match = url.split("/blog/")
                    if len(slug_match) > 1:
                        slug = slug_match[1].strip("/")
                        cat = slug_to_cat.get(slug, "Other")
                        cat_clicks[cat] = cat_clicks.get(cat, 0) + page_data.get("clicks", 0)
                        cat_impressions[cat] = cat_impressions.get(cat, 0) + page_data.get("impressions", 0)

                if cat_clicks:
                    cat_lines = "\n".join(
                        f"  {cat_clicks[c]:>4} clicks | {cat_impressions[c]:>6} imp — {c}"
                        for c in sorted(cat_clicks, key=cat_clicks.get, reverse=True)
                    )
                    cat_rollup_text = f"""
  By category:
{cat_lines}
"""

            gsc_text = f"""
GOOGLE SEARCH CONSOLE ({period})
  Total clicks:         {t.get('clicks', 0)}
  Total impressions:    {t.get('impressions', 0)}
  Avg CTR:              {t.get('ctr', 0)}%
  Avg position:         {t.get('position', 0)}
{cat_rollup_text}
  Top pages:
{page_lines}

  Top search queries:
{query_lines}
"""
        except Exception:
            gsc_text = ""

    summary = f"""GHL Podcast Pipeline — Daily Report
Cycle #{cycle_num} | {datetime.now().strftime("%B %d, %Y %I:%M %p")}

TODAY
  Podcast episodes:     {published_today}
  GHL blogs:            {blogs_today}
  India blogs:          {india_blogs_today}
  Failed:               {failed_today}
  {"ACTION MAY BE NEEDED — see failures below" if needs_action else "All good"}

ALL TIME
  Podcast episodes:     {total_published}
  GHL blogs:            {total_blogs}
  India blogs:          {india_blogs_total}
  Total streams:        {total_streams}
  Failed:               {total_failed} (will retry next cycle)
  Remaining:            ~{1565 - total_published} articles left (~{max(0, (1565 - total_published) // 20)} days)

NEXT RUN
  {next_run.strftime("%B %d, %Y at %I:%M %p")}
{site_text}{gsc_text}{analytics_text}{top_episodes_text}
TODAY'S EPISODES
{titles_text}

RECENT ERRORS
{errors_text}

---
Pipeline running automatically. No action needed unless noted above.
To check logs: tail -f ~/Claude_notebookLM_GHL_Podcast/ghl-podcast-pipeline/logs/pipeline.log
"""
    return summary


def send_email(subject: str, body: str):
    """Send summary email via Gmail SMTP."""
    if not GMAIL_APP_PASSWORD:
        log("  No GMAIL_APP_PASSWORD set — skipping email")
        return

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = GMAIL_ADDRESS

        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(context=context)
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())

        log(f"  Daily summary emailed to {GMAIL_ADDRESS}")
    except Exception as e:
        log(f"  Email failed: {e}")


# ── Site deploy ───────────────────────────────────────────────────────────────
def deploy_site():
    """
    Push new blog post JSON files to GitHub → Netlify auto-rebuilds and deploys.
    Only commits if there are actual new/changed files in globalhighlevel-site/posts/.
    """
    site_dir = BASE_DIR.parent / "globalhighlevel-site"
    posts_dir = site_dir / "posts"
    # Cloudflare Pages builds from globalhighlevel-site/ subdirectory
    cf_posts_dir = site_dir / "globalhighlevel-site" / "posts"

    if not posts_dir.exists():
        log("  deploy_site: posts/ dir not found — skipping")
        return

    try:
        # Sync root posts/ into the subdirectory that Cloudflare Pages builds from
        if cf_posts_dir.exists():
            import shutil
            for f in posts_dir.glob("*.json"):
                dest = cf_posts_dir / f.name
                if not dest.exists() or f.stat().st_mtime > dest.stat().st_mtime:
                    shutil.copy2(f, dest)
            # Also sync categories.json
            root_cats = site_dir / "categories.json"
            cf_cats = site_dir / "globalhighlevel-site" / "categories.json"
            if root_cats.exists():
                shutil.copy2(root_cats, cf_cats)

        # Check if there's anything new to commit
        result = subprocess.run(
            ["git", "status", "--porcelain", "posts/", "globalhighlevel-site/posts/"],
            cwd=site_dir, capture_output=True, text=True, timeout=30
        )
        if not result.stdout.strip():
            log("  deploy_site: no new posts to push — skipping")
            return

        # Count new files
        new_files = len(result.stdout.strip().splitlines())

        # Stage both locations + categories
        subprocess.run(
            ["git", "add", "posts/", "globalhighlevel-site/posts/", "categories.json", "globalhighlevel-site/categories.json"],
            cwd=site_dir, check=True, capture_output=True, timeout=30
        )

        # Commit
        msg = f"Auto-deploy: {new_files} new post(s) — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=site_dir, check=True, capture_output=True, timeout=30
        )

        # Push
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=site_dir, check=True, capture_output=True, timeout=120
        )

        log(f"  deploy_site: pushed {new_files} post(s) → Cloudflare Pages deploying globalhighlevel.com")

    except subprocess.TimeoutExpired:
        log("  deploy_site: git command timed out (non-fatal)")
    except subprocess.CalledProcessError as e:
        log(f"  deploy_site error (non-fatal): {e}")


# ── Script loader ─────────────────────────────────────────────────────────────
def load_script(name: str):
    path = SCRIPTS_DIR / name
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Main cycle ────────────────────────────────────────────────────────────────
async def run_cycle(cycle_num: int):
    cycle_started = datetime.now()
    log("=" * 60)
    log(f"Cycle #{cycle_num} starting")

    # Save state NOW so restarts wait out the 25h window instead of re-running immediately
    save_state(cycle_started)

    # Step 0a: Pull analytics data to update stream counts + topic weights
    log("Step 0a — Running analytics.py...")
    try:
        analytics = load_script("analytics.py")
        analytics.main()
    except Exception as e:
        log(f"  analytics.py error (non-fatal): {e}")

    # Step 0b: Generate topics from GSC search data
    log("Step 0b — Running gsc-topics.py...")
    try:
        gsc_topics = load_script("gsc-topics.py")
        gsc_topics.main()
    except Exception as e:
        log(f"  gsc-topics.py error (non-fatal): {e}")

    # Send start notification email
    log("Sending start notification email...")
    next_run_est = cycle_started + timedelta(hours=CYCLE_HOURS)
    start_body = f"""GHL Podcast Pipeline — Cycle #{cycle_num} Starting
{cycle_started.strftime("%B %d, %Y at %I:%M %p")}

The pipeline just kicked off. It will:
  1. Retry any failed episodes from last cycle
  2. Generate and publish today's batch of 20 episodes

Estimated next run: {next_run_est.strftime("%B %d, %Y at %I:%M %p")}

You'll get a summary email when it's done.
"""
    send_email(f"GHL Podcast — Cycle #{cycle_num} Starting | {cycle_started.strftime('%b %d')}", start_body)

    # Step 1: Retry any failed episodes from previous cycle
    log("Step 1/2 — Running retry-failed.py...")
    try:
        retry = load_script("retry-failed.py")
        await retry.main()
    except Exception as e:
        log(f"  retry-failed.py error: {e}")

    # Step 2: Run main pipeline
    log("Step 2/3 — Running run-pipeline.py...")
    try:
        pipeline = load_script("run-pipeline.py")
        await pipeline.main()
    except Exception as e:
        log(f"  run-pipeline.py error: {e}")

    # Step 3: Run India blog agent (5 topics per cycle)
    log("Step 3/5 — Running 6-india-blog.py (up to 5 topics)...")
    try:
        import sys
        sys.argv = ["6-india-blog.py", "--limit", "5"]
        india = load_script("6-india-blog.py")
        india.main()
        sys.argv = [sys.argv[0]]
    except Exception as e:
        log(f"  6-india-blog.py error (non-fatal): {e}")

    # Step 4: Run Spanish blog agent (5 topics per cycle)
    log("Step 4/5 — Running 7-spanish-blog.py (up to 5 topics)...")
    try:
        import sys
        sys.argv = ["7-spanish-blog.py", "--limit", "5"]
        spanish = load_script("7-spanish-blog.py")
        spanish.main()
        sys.argv = [sys.argv[0]]
    except Exception as e:
        log(f"  7-spanish-blog.py error (non-fatal): {e}")

    # Step 5: Deploy new posts to globalhighlevel.com via GitHub → Cloudflare Pages
    log("Step 5/5 — Deploying new posts to globalhighlevel.com...")
    try:
        deploy_site()
    except Exception as e:
        log(f"  deploy_site error (non-fatal): {e}")

    # Save state so restarts are safe
    save_state(cycle_started)

    # Send daily email summary
    next_run = cycle_started + timedelta(hours=CYCLE_HOURS)
    log("Sending daily summary email...")
    summary = build_summary(cycle_num, next_run)
    subject = f"GHL Podcast — Cycle #{cycle_num} | {datetime.now().strftime('%b %d')}"
    send_email(subject, summary)

    # Weekly Slack SEO report (sends once per 7 days automatically)
    try:
        weekly_report = load_script("weekly-slack-report.py")
        weekly_report.main()
    except Exception as e:
        log(f"  Weekly Slack report error (non-fatal): {e}")

    log(f"Cycle #{cycle_num} complete.")
    log(f"Next cycle: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)


async def main():
    log("=" * 60)
    log(f"Scheduler started — cycling every {CYCLE_HOURS} hours")
    log("=" * 60)

    # Save PID for easy killing
    pid_file = BASE_DIR / "logs" / "scheduler.pid"
    pid_file.write_text(str(os.getpid()))

    # On restart: wait out any remaining time from previous cycle
    wait_secs = seconds_until_next_cycle()
    if wait_secs > 0:
        wait_hrs = wait_secs / 3600
        resume_at = datetime.now() + timedelta(seconds=wait_secs)
        log(f"Restarted early — {wait_hrs:.1f}h left in current cycle.")
        log(f"Resuming at: {resume_at.strftime('%Y-%m-%d %H:%M:%S')}")
        await asyncio.sleep(wait_secs)

    cycle = 1
    while True:
        cycle_started = datetime.now()
        await run_cycle(cycle)

        # Sleep in short chunks so Mac sleep doesn't stall the timer.
        # Check wall-clock time each loop — if 25 real hours have passed, go.
        target = cycle_started + timedelta(hours=CYCLE_HOURS)
        log(f"Next cycle at {target.strftime('%Y-%m-%d %H:%M:%S')} — sleeping...")
        while datetime.now() < target:
            await asyncio.sleep(300)  # wake every 5 min to check clock
        cycle += 1


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Scheduler stopped.")
