"""
gsc-topics.py
Reads Google Search Console data and generates/improves content based on real search behavior.

Runs as part of each scheduler cycle (after analytics.py pulls fresh GSC data).

Three strategies:
  1. GAP FINDER — queries with high impressions but no matching content → new blog topics
  2. CTR OPTIMIZER — pages with high impressions but low CTR → rewrite titles/descriptions
  3. RANKING BOOSTER — pages ranking 5-20 → identify what to add to push them higher

Feeds topics into all blog agents (English, India, Spanish).
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

import anthropic
try:
    from cost_logger import log_api_cost
except ImportError:
    def log_api_cost(*a, **kw): return {}
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
GSC_DATA_FILE = BASE_DIR / "data" / "gsc-stats.json"
SITE_POSTS_DIR = Path("/opt/globalhighlevel-site/posts") if Path("/opt/globalhighlevel-site/posts").exists() else BASE_DIR.parent / "globalhighlevel-site" / "posts"
TOPICS_OUTPUT = BASE_DIR / "data" / "gsc-topics.json"
SEO_COOLDOWN_FILE = BASE_DIR / "data" / "seo-cooldown.json"
# Cooldown days differ by action type:
#   rewrite_meta:   28 days — title/meta changes show CTR signal in ~2-4 weeks
#   expand_content: 90 days — content/ranking changes take 3-6 months to show
# Default for unknown actions = longer, to avoid premature re-rewrites.
COOLDOWNS_BY_ACTION = {
    "rewrite_meta": 28,
    "expand_content": 90,
}
COOLDOWN_DAYS = 28  # legacy default — used only as fallback

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [GSC-TOPICS] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_gsc_data() -> dict:
    if not GSC_DATA_FILE.exists():
        return {}
    try:
        with open(GSC_DATA_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def load_existing_slugs() -> set:
    """Get all existing blog post slugs."""
    slugs = set()
    if SITE_POSTS_DIR.exists():
        for f in SITE_POSTS_DIR.glob("*.json"):
            slugs.add(f.stem)
    return slugs


def load_existing_titles() -> list:
    """Get all existing blog post titles."""
    titles = []
    if SITE_POSTS_DIR.exists():
        for f in SITE_POSTS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                titles.append(data.get("title", ""))
            except Exception:
                pass
    return titles


# ── SEO Cooldown — don't re-flag pages that were recently suggested ───────────

def load_cooldowns() -> dict:
    """Load cooldown records: {slug: {"action": ..., "flagged_at": ..., "metrics": {...}}}"""
    if not SEO_COOLDOWN_FILE.exists():
        return {}
    try:
        with open(SEO_COOLDOWN_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cooldowns(cooldowns: dict):
    with open(SEO_COOLDOWN_FILE, "w") as f:
        json.dump(cooldowns, f, indent=2)


def is_on_cooldown(slug: str, cooldowns: dict) -> bool:
    """Check if a slug is locked. Respects per-slug locked_until (absolute date)
    or falls back to the 28-day flagged_at window."""
    if slug not in cooldowns:
        return False
    entry = cooldowns[slug]
    # Per-slug absolute lock (e.g., measurement windows after a manual rewrite)
    locked_until = entry.get("locked_until", "")
    if locked_until:
        try:
            if datetime.now() < datetime.fromisoformat(locked_until):
                return True
        except Exception:
            pass
    flagged_at = entry.get("flagged_at", "")
    if not flagged_at:
        return False
    action = entry.get("action", "")
    cooldown_for_action = COOLDOWNS_BY_ACTION.get(action, COOLDOWN_DAYS)
    try:
        flagged_date = datetime.fromisoformat(flagged_at)
        days_since = (datetime.now() - flagged_date).days
        return days_since < cooldown_for_action
    except Exception:
        return False


def record_suggestion(slug: str, action: str, metrics: dict, cooldowns: dict):
    """Record that a suggestion was made for this slug."""
    cooldowns[slug] = {
        "action": action,
        "flagged_at": datetime.now().isoformat(),
        "metrics_at_flag": metrics,
    }


# ── Strategy 1: Gap Finder ────────────────────────────────────────────────────
def find_content_gaps(gsc_data: dict) -> list:
    """
    Find queries people search for that we don't have content for.
    High impressions + no matching page = opportunity.
    """
    queries = gsc_data.get("queries", [])
    pages = gsc_data.get("pages", [])
    existing_slugs = load_existing_slugs()

    # Queries with impressions but low/no clicks — people see us but don't click,
    # or queries where we show up but have no dedicated page
    gaps = []
    for q in queries:
        query = q["query"].lower()
        impressions = q.get("impressions", 0)
        clicks = q.get("clicks", 0)
        position = q.get("position", 100)

        if impressions < 5:
            continue

        # Check if any existing slug roughly matches this query
        query_words = set(query.split())
        has_match = False
        for slug in existing_slugs:
            slug_words = set(slug.replace("-", " ").split())
            overlap = len(query_words & slug_words)
            if overlap >= 2:
                has_match = True
                break

        if not has_match:
            gaps.append({
                "query": q["query"],
                "impressions": impressions,
                "clicks": clicks,
                "position": position,
                "type": "gap",
            })

    # Sort by impressions descending
    gaps.sort(key=lambda x: x["impressions"], reverse=True)
    return gaps[:20]


# ── Strategy 2: CTR Optimizer ─────────────────────────────────────────────────
def find_low_ctr_pages(gsc_data: dict) -> list:
    """
    Pages with high impressions but low CTR — title/description need rewriting.
    """
    pages = gsc_data.get("pages", [])
    low_ctr = []

    for p in pages:
        impressions = p.get("impressions", 0)
        ctr = p.get("ctr", 0)
        clicks = p.get("clicks", 0)

        # Impressions >= 50 gives statistical signal (0 clicks @ 3% CTR is
        # only ~22% noise at n=50, vs ~54% at n=20). Below 50, any CTR
        # judgment is essentially a coin flip.
        if impressions >= 50 and ctr < 3.0:
            low_ctr.append({
                "page": p["page"],
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "position": p.get("position", 0),
                "type": "low_ctr",
            })

    low_ctr.sort(key=lambda x: x["impressions"], reverse=True)
    return low_ctr[:30]


# ── Strategy 3: Ranking Booster ───────────────────────────────────────────────
def find_almost_ranking(gsc_data: dict) -> list:
    """
    Pages ranking 5-20 — close to page 1 but need a push.
    These are the highest ROI to improve.
    """
    pages = gsc_data.get("pages", [])
    almost = []

    for p in pages:
        position = p.get("position", 100)
        impressions = p.get("impressions", 0)

        # Lower threshold than rewrite_meta: ranking-candidate pages have
        # fewer impressions by definition (not ranked yet), but 30+ gives
        # enough data to judge whether content expansion earns a rank shift.
        if 5 <= position <= 20 and impressions >= 30:
            almost.append({
                "page": p["page"],
                "position": position,
                "impressions": impressions,
                "clicks": p.get("clicks", 0),
                "ctr": p.get("ctr", 0),
                "type": "almost_ranking",
            })

    almost.sort(key=lambda x: x["impressions"], reverse=True)
    return almost[:30]


# ── Topic Generator (uses GSC gaps) ──────────────────────────────────────────
def generate_topics_from_gaps(gaps: list, language: str = "english") -> list:
    """Use Claude to turn search gaps into blog topics for any language."""
    if not gaps:
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    existing_titles = load_existing_titles()
    existing_list = "\n".join(f"- {t}" for t in existing_titles[-50:])

    gap_list = "\n".join(
        f"- \"{g['query']}\" ({g['impressions']} impressions, position {g['position']:.0f})"
        for g in gaps[:15]
    )

    lang_instructions = {
        "english": "Write topics in English targeting GoHighLevel users worldwide.",
        "india": "Write topics in English but specifically for Indian businesses and agencies. Include India-specific angles (WhatsApp, Razorpay/UPI, rupee pricing, Zoho comparisons, Indian industries).",
        "spanish": "Write topics in Spanish targeting GoHighLevel users in Latin America and Spain. Use natural Spanish, not translations. Include region-specific angles (WhatsApp, MercadoPago, local competitors, Latin American industries).",
    }

    prompt = f"""Based on real Google Search Console data, people are searching for these terms and finding our GoHighLevel blog:

SEARCH QUERIES (sorted by impressions):
{gap_list}

We don't have dedicated content for these queries yet. Generate 10 blog post topics that would rank for these searches.

{lang_instructions.get(language, lang_instructions['english'])}

ALREADY PUBLISHED (don't repeat these):
{existing_list}

Requirements:
- Each topic must target one or more of the search queries above
- Be specific and actionable
- Include "GoHighLevel" or "GHL" in each topic
- Format as a blog post title

Return ONLY the 10 topics, one per line, no numbering, no bullets."""

    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    log_api_cost(msg, script="gsc-topics")

    topics = [line.strip() for line in msg.content[0].text.strip().splitlines() if line.strip()]
    return topics


# ── Improvement Suggestions ───────────────────────────────────────────────────
def generate_improvements(low_ctr: list, almost_ranking: list) -> list:
    """Generate specific improvement suggestions for existing pages.
    Respects a 28-day cooldown — won't re-flag pages that were recently suggested.
    """
    if not low_ctr and not almost_ranking:
        return []

    cooldowns = load_cooldowns()
    suggestions = []
    skipped = 0

    # Filter cooldowns FIRST, then take top N — otherwise if the top slots are
    # all in cooldown we return zero suggestions instead of backfilling.
    low_ctr_eligible = []
    for page in low_ctr:
        slug = page["page"].split("/blog/")[-1].strip("/") if "/blog/" in page["page"] else ""
        if not slug:
            continue
        if is_on_cooldown(slug, cooldowns):
            skipped += 1
            continue
        low_ctr_eligible.append((page, slug))

    # Build the queue only. DO NOT record cooldowns here — cooldown should mean
    # "page was recently RE-WRITTEN", not "page was recently FLAGGED". Recording
    # cooldown at flag-time creates a self-defeating loop: gsc-topics locks a
    # page, then the optimizer reads the queue, sees cooldown, skips. The
    # optimizer itself is the only writer that should set cooldowns (it does so
    # in apply_changes() when a rewrite is actually applied).
    for page, slug in low_ctr_eligible[:5]:
        suggestions.append({
            "slug": slug,
            "action": "rewrite_meta",
            "reason": f"High impressions ({page['impressions']}) but low CTR ({page['ctr']}%) — title and description need to be more compelling",
            "impressions": page["impressions"],
            "ctr": page["ctr"],
            "position": page["position"],
        })

    almost_eligible = []
    for page in almost_ranking:
        slug = page["page"].split("/blog/")[-1].strip("/") if "/blog/" in page["page"] else ""
        if not slug:
            continue
        if is_on_cooldown(slug, cooldowns):
            skipped += 1
            continue
        almost_eligible.append((page, slug))

    for page, slug in almost_eligible[:5]:
        suggestions.append({
            "slug": slug,
            "action": "expand_content",
            "reason": f"Ranking at position {page['position']:.0f} with {page['impressions']} impressions — add more depth to push to page 1",
            "impressions": page["impressions"],
            "position": page["position"],
        })
    if skipped:
        log(f"  Skipped {skipped} pages on cooldown (flagged within last {COOLDOWN_DAYS} days)")

    return suggestions


MAX_RETRY_ATTEMPTS = 2  # original + 1 retry
CHANGELOG_FILE = BASE_DIR / "data" / "seo-changelog.json"


# ── 28-Day Outcome Review ────────────────────────────────────────────────────
def review_expired_cooldowns(gsc_data: dict) -> list:
    """
    Check pages whose cooldown just expired. Compare current GSC metrics
    to the metrics at time of optimization. If CTR didn't improve, re-flag
    for one more attempt.
    """
    cooldowns = load_cooldowns()
    gsc_pages = {p["page"].split("/blog/")[-1].strip("/"): p for p in gsc_data.get("pages", []) if "/blog/" in p["page"]}
    retry_suggestions = []

    # Load changelog to update outcomes
    changelog = []
    if CHANGELOG_FILE.exists():
        try:
            changelog = json.loads(CHANGELOG_FILE.read_text())
        except Exception:
            changelog = []

    for slug, cd in list(cooldowns.items()):
        flagged_at = cd.get("flagged_at", "")
        if not flagged_at:
            continue
        try:
            days_since = (datetime.now() - datetime.fromisoformat(flagged_at)).days
        except Exception:
            continue

        # Only review pages whose cooldown just expired (28-35 days)
        if days_since < COOLDOWN_DAYS or days_since > COOLDOWN_DAYS + 7:
            continue

        attempt = cd.get("attempt", 1)
        metrics_before = cd.get("metrics_at_flag", {})
        ctr_before = metrics_before.get("ctr", 0)
        position_before = metrics_before.get("position", 100)

        # Get current metrics
        current = gsc_pages.get(slug, {})
        ctr_now = current.get("ctr", 0)
        position_now = current.get("position", 100)

        # Determine outcome
        improved = ctr_now > ctr_before or position_now < position_before - 1
        outcome = "improved" if improved else "no_change"

        log(f"  28-day review: {slug} — CTR {ctr_before}% → {ctr_now}%, pos {position_before} → {position_now} = {outcome}")

        # Update changelog entries for this slug
        for entry in changelog:
            if entry.get("slug") == slug and entry.get("outcome") is None:
                entry["position_28d"] = position_now
                entry["ctr_28d"] = ctr_now
                entry["outcome"] = outcome

        # If not improved and retries available, re-flag
        if not improved and attempt < MAX_RETRY_ATTEMPTS:
            retry_suggestions.append({
                "slug": slug,
                "action": cd.get("action", "rewrite_meta"),
                "reason": f"Retry #{attempt + 1}: previous optimization did not improve CTR ({ctr_before}% → {ctr_now}%)",
                "impressions": current.get("impressions", metrics_before.get("impressions", 0)),
                "ctr": ctr_now,
                "position": position_now,
                "attempt": attempt + 1,
            })
            # Clear cooldown so optimizer can pick it up
            del cooldowns[slug]
            log(f"  Re-flagged for retry #{attempt + 1}")
        elif not improved:
            log(f"  Parked — max retries ({MAX_RETRY_ATTEMPTS}) exhausted")
            cooldowns[slug]["outcome"] = "parked"
        else:
            cooldowns[slug]["outcome"] = "improved"

    save_cooldowns(cooldowns)

    # Save updated changelog
    if changelog:
        try:
            CHANGELOG_FILE.write_text(json.dumps(changelog, indent=2))
        except Exception:
            pass

    if retry_suggestions:
        log(f"  {len(retry_suggestions)} pages re-flagged for retry")

    return retry_suggestions


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> dict:
    log("=" * 50)
    log("GSC topic analysis starting")

    gsc_data = load_gsc_data()
    if not gsc_data or not gsc_data.get("queries"):
        log("No GSC data available — skipping topic generation")
        return {}

    # Run all three strategies
    gaps = find_content_gaps(gsc_data)
    low_ctr = find_low_ctr_pages(gsc_data)
    almost = find_almost_ranking(gsc_data)

    log(f"Found: {len(gaps)} content gaps, {len(low_ctr)} low-CTR pages, {len(almost)} almost-ranking pages")

    # Generate topics for each language
    results = {"generated_at": datetime.now().isoformat()}

    if gaps:
        log("Generating English topics from search gaps...")
        results["english_topics"] = generate_topics_from_gaps(gaps, "english")
        log(f"  {len(results['english_topics'])} English topics generated")

        log("Generating India topics from search gaps...")
        results["india_topics"] = generate_topics_from_gaps(gaps, "india")
        log(f"  {len(results['india_topics'])} India topics generated")

        log("Generating Spanish topics from search gaps...")
        results["spanish_topics"] = generate_topics_from_gaps(gaps, "spanish")
        log(f"  {len(results['spanish_topics'])} Spanish topics generated")

    # Generate improvement suggestions
    results["improvements"] = generate_improvements(low_ctr, almost)
    log(f"  {len(results['improvements'])} improvement suggestions")

    # Review expired cooldowns and add retry suggestions
    retry_suggestions = review_expired_cooldowns(gsc_data)
    if retry_suggestions:
        results["improvements"].extend(retry_suggestions)
        log(f"  {len(retry_suggestions)} retry suggestions added")

    # Save results
    with open(TOPICS_OUTPUT, "w") as f:
        json.dump(results, f, indent=2)
    log(f"Saved to {TOPICS_OUTPUT}")

    # Append GSC-generated topics to each language's topic file
    _append_topics("india", results.get("india_topics", []))
    _append_topics("spanish", results.get("spanish_topics", []))

    log("GSC topic analysis complete")
    return results


def _append_topics(language: str, new_topics: list):
    """Append new topics to a language's topic file, avoiding duplicates."""
    if not new_topics:
        return

    topic_file = BASE_DIR / "data" / f"{language}-topics.json"
    existing = []
    if topic_file.exists():
        try:
            with open(topic_file) as f:
                existing = json.load(f)
        except Exception:
            existing = []

    existing_lower = {t.lower() if isinstance(t, str) else t.get("topic", "").lower() for t in existing}
    added = 0
    for t in new_topics:
        if t.lower() not in existing_lower:
            existing.append(t)
            added += 1

    if added:
        with open(topic_file, "w") as f:
            json.dump(existing, f, indent=2)
        log(f"  Added {added} GSC topics to {language}-topics.json")


if __name__ == "__main__":
    main()
