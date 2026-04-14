"""
8-seo-optimizer.py
SEO Optimizer Team — picks up flagged pages from gsc-topics.json and executes fixes.

5-role pipeline:
  1. GSC Analyst   — prioritize pages by opportunity
  2. Researcher    — SERP + Reddit research for competitor analysis
  3. Content Writer — rewrite titles/descriptions, expand content
  4. Fact Checker   — validate output quality
  5. Engineer       — apply changes, update cooldown, notify Slack

Schedule: Weekly (gated by last-run timestamp).
Batch size: configurable via MAX_PAGES_PER_CYCLE (default 10).
"""

import json
import os
import re
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import anthropic
try:
    from cost_logger import log_api_cost
except ImportError:
    def log_api_cost(*a, **kw): return {}
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

try:
    from ops_log import ops_log as _ops_log
except ImportError:
    def _ops_log(*a, **kw): pass

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
GSC_TOPICS_FILE = BASE_DIR / "data" / "gsc-topics.json"
SEO_COOLDOWN_FILE = BASE_DIR / "data" / "seo-cooldown.json"
OPTIMIZER_STATE_FILE = BASE_DIR / "data" / "seo-optimizer-state.json"
CHANGELOG_FILE = BASE_DIR / "data" / "seo-changelog.json"

# Post directories — both must stay in sync
SITE_POSTS_DIR = BASE_DIR.parent / "globalhighlevel-site" / "posts"
PIPELINE_POSTS_DIR = BASE_DIR.parent / "posts"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GHL_AFFILIATE_LINK = os.getenv("GHL_AFFILIATE_LINK", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SITE_URL = os.getenv("SITE_URL", "https://globalhighlevel.com")

MODEL = "claude-haiku-4-5-20251001"
MAX_PAGES_PER_CYCLE = int(os.getenv("MAX_PAGES_PER_CYCLE", "10"))
SCHEDULE_DAYS = int(os.getenv("SEO_OPTIMIZER_SCHEDULE_DAYS", "7"))
COOLDOWN_DAYS = 28
MAX_RETRY_ATTEMPTS = int(os.getenv("SEO_MAX_RETRY_ATTEMPTS", "2"))
TITLE_MAX = int(os.getenv("TITLE_MAX_CHARS", "60"))
DESC_MAX = int(os.getenv("DESC_MAX_CHARS", "155"))

HEADERS_DDG = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [SEO-OPT] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Weekly Gate ───────────────────────────────────────────────────────────────
def should_run() -> bool:
    """Only run if SCHEDULE_DAYS have passed since last run."""
    if not OPTIMIZER_STATE_FILE.exists():
        return True
    try:
        state = json.loads(OPTIMIZER_STATE_FILE.read_text())
        last_run = datetime.fromisoformat(state.get("last_run", ""))
        days_since = (datetime.now() - last_run).days
        if days_since < SCHEDULE_DAYS:
            log(f"Skipping — last run {days_since} days ago (schedule: every {SCHEDULE_DAYS} days)")
            return False
        return True
    except Exception:
        return True


def save_run_state(results: dict):
    """Save last-run timestamp and results summary."""
    state = {
        "last_run": datetime.now().isoformat(),
        "pages_optimized": results.get("pages_optimized", 0),
        "rewrites": results.get("rewrites", 0),
        "expansions": results.get("expansions", 0),
    }
    OPTIMIZER_STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Data Loading ──────────────────────────────────────────────────────────────
def load_improvements() -> list:
    """Load flagged pages from gsc-topics.json."""
    if not GSC_TOPICS_FILE.exists():
        return []
    try:
        data = json.loads(GSC_TOPICS_FILE.read_text())
        return data.get("improvements", [])
    except Exception:
        return []


def load_cooldowns() -> dict:
    if not SEO_COOLDOWN_FILE.exists():
        return {}
    try:
        return json.loads(SEO_COOLDOWN_FILE.read_text())
    except Exception:
        return {}


def save_cooldowns(cooldowns: dict):
    SEO_COOLDOWN_FILE.write_text(json.dumps(cooldowns, indent=2))


def load_post(slug: str) -> dict | None:
    """Load a post JSON by slug from the site posts directory."""
    for posts_dir in [SITE_POSTS_DIR, PIPELINE_POSTS_DIR]:
        post_file = posts_dir / f"{slug}.json"
        if post_file.exists():
            try:
                return json.loads(post_file.read_text())
            except Exception:
                continue
    return None


def load_changelog() -> list:
    if not CHANGELOG_FILE.exists():
        return []
    try:
        return json.loads(CHANGELOG_FILE.read_text())
    except Exception:
        return []


def save_changelog(entries: list):
    CHANGELOG_FILE.write_text(json.dumps(entries, indent=2))


# ══════════════════════════════════════════════════════════════════════════════
# ROLE 1: GSC Analyst — Prioritize pages by opportunity
# ══════════════════════════════════════════════════════════════════════════════
def analyze_and_prioritize(improvements: list, max_pages: int) -> list:
    """
    Score and rank pages by optimization opportunity.
    Score = impressions × (1 / max(ctr, 0.1)) × position_weight
    rewrite_meta pages get a bonus if position < 10 (already on page 1).
    """
    cooldowns = load_cooldowns()
    scored = []

    for item in improvements:
        slug = item.get("slug", "")
        if not slug:
            continue

        # Skip if on cooldown
        if slug in cooldowns:
            cd = cooldowns[slug]
            flagged_at = cd.get("flagged_at", "")
            attempt = cd.get("attempt", 1)
            if flagged_at:
                try:
                    days_since = (datetime.now() - datetime.fromisoformat(flagged_at)).days
                    if days_since < COOLDOWN_DAYS:
                        continue
                except Exception:
                    pass
            # If max retries exhausted, skip
            if attempt >= MAX_RETRY_ATTEMPTS and cd.get("outcome") != "improved":
                continue

        # Check post exists
        post = load_post(slug)
        if not post:
            continue

        impressions = item.get("impressions", 0)
        ctr = item.get("ctr", 0)
        position = item.get("position", 100)
        action = item.get("action", "rewrite_meta")

        # Score: high impressions + low CTR + good position = high opportunity
        ctr_factor = 1 / max(ctr, 0.1)
        position_weight = 2.0 if position <= 10 else (1.5 if position <= 15 else 1.0)
        score = impressions * ctr_factor * position_weight

        # Bonus for retry attempts (they've been waiting 28+ days)
        if item.get("attempt", 1) > 1:
            score *= 1.3

        scored.append({
            **item,
            "score": score,
            "post": post,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[:max_pages]

    log(f"GSC Analyst: {len(improvements)} flagged → {len(scored)} eligible → {len(selected)} selected")
    for s in selected:
        log(f"  [{s['action']}] {s['slug']} — pos {s.get('position', '?')}, {s.get('impressions', '?')} impr, score {s['score']:.0f}")

    return selected


# ══════════════════════════════════════════════════════════════════════════════
# ROLE 2: Researcher — SERP + Reddit competitor analysis
# ══════════════════════════════════════════════════════════════════════════════
def scrape_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """Scrape top DuckDuckGo results. Returns list of {title, snippet, url}."""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS_DDG,
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for result in soup.select(".result__body")[:max_results + 3]:
            if result.select_one(".badge--ad"):
                continue
            title_el = result.select_one(".result__title")
            snippet_el = result.select_one(".result__snippet")
            url_el = result.select_one(".result__url")
            if title_el and snippet_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True),
                    "url": url_el.get_text(strip=True) if url_el else "",
                })
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        log(f"  DuckDuckGo scrape failed: {e}")
        return []


def scrape_reddit(query: str, max_results: int = 5) -> list[str]:
    """Fetch top Reddit questions about the topic."""
    subreddits = ["GoHighLevel", "marketing", "automation", "entrepreneur"]
    questions = []
    for subreddit in subreddits:
        if len(questions) >= max_results:
            break
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{subreddit}/search.json",
                params={"q": query, "restrict_sr": 1, "sort": "top", "limit": max_results, "type": "link"},
                headers={"User-Agent": "SEOOptimizerBot/1.0"},
                timeout=15,
            )
            posts = resp.json().get("data", {}).get("children", [])
            for post in posts:
                title = post.get("data", {}).get("title", "")
                if title and title not in questions:
                    questions.append(title)
        except Exception:
            pass
    return questions[:max_results]


def do_research(page: dict) -> dict:
    """
    Role 2: Research competitors for this page.
    For rewrite_meta: focus on competitor titles/descriptions.
    For expand_content: full SERP + Reddit research.
    """
    post = page["post"]
    title = post.get("title", "")
    # Extract core topic from title (strip "How to" prefix and "in GoHighLevel" suffix)
    core_topic = re.sub(r"^(How to |Master |Enable |Track )", "", title)
    core_topic = re.sub(r" in GoHighLevel.*$| GoHighLevel.*$", "", core_topic)

    query = f"{core_topic} GoHighLevel"
    log(f"  Researching: {query}")

    serp_results = scrape_duckduckgo(query)
    time.sleep(1)  # Be polite

    reddit_questions = []
    if page.get("action") == "expand_content":
        reddit_questions = scrape_reddit(core_topic)
        time.sleep(1)

    research = {
        "query": query,
        "core_topic": core_topic,
        "serp_results": serp_results,
        "reddit_questions": reddit_questions,
        "competitor_titles": [r["title"] for r in serp_results],
        "competitor_snippets": [r["snippet"] for r in serp_results],
    }

    log(f"  Research complete: {len(serp_results)} SERP results, {len(reddit_questions)} Reddit questions")
    return research


# ══════════════════════════════════════════════════════════════════════════════
# ROLE 3: Content Writer — Rewrite titles/descriptions, expand content
# ══════════════════════════════════════════════════════════════════════════════
LANG_INSTRUCTIONS = {
    "es": "The output MUST be written in Spanish (Español). The current page is on /es/ and serves Spanish-speaking searchers. Do NOT write any part of the title or description in English.",
    "ar": "The output MUST be written in Arabic (العربية). The current page is on /ar/ and serves Arabic-speaking searchers. Do NOT write any part of the title or description in English.",
    "en-IN": "The output MUST be written in Indian English (clear English, Indian cultural context welcome). Use ₹ for currency, reference Indian platforms (WhatsApp, UPI) where relevant.",
    "en": "The output MUST be written in English.",
}


def _post_language(post: dict) -> str:
    lang = post.get("language", "")
    if lang in LANG_INSTRUCTIONS:
        return lang
    slug = post.get("slug", "") or ""
    # Fall back to filesystem location heuristic if language field is missing
    if any(x in slug for x in ["espanol", "español", "latinoamerica", "mercadopago"]):
        return "es"
    return "en"


def generate_meta_rewrite(page: dict, research: dict) -> dict:
    """Rewrite title and description for a low-CTR page."""
    post = page["post"]
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    competitor_context = "\n".join(
        f"- {t}" for t in research["competitor_titles"]
    ) or "No competitor data."

    attempt = page.get("attempt", 1)
    retry_hint = ""
    if attempt > 1:
        retry_hint = "\nIMPORTANT: A previous rewrite did NOT improve CTR. Try a completely different angle — different hook, different structure, different emotional trigger.\n"

    post_lang = _post_language(post)
    lang_instruction = LANG_INSTRUCTIONS.get(post_lang, LANG_INSTRUCTIONS["en"])

    prompt = f"""You are an SEO title/description specialist. Rewrite the title and meta description for this blog post to dramatically increase click-through rate from Google search results.

OUTPUT LANGUAGE: {lang_instruction}


CURRENT TITLE: {post.get('title', '')}
CURRENT DESCRIPTION: {post.get('description', '')[:200]}
POSITION IN GOOGLE: {page.get('position', '?')}
IMPRESSIONS: {page.get('impressions', '?')}
CURRENT CTR: {page.get('ctr', '?')}%

COMPETITOR TITLES RANKING FOR SIMILAR QUERIES:
{competitor_context}
{retry_hint}
REWRITE RULES:
1. TITLE — max {TITLE_MAX} characters
   - Do NOT always start with "How to" — vary the structure
   - Good patterns: question titles, number titles, problem-first, benefit-first
   - Examples: "Stop Spam Calls in GHL (5-Min IVR Setup)", "GHL Pipeline Hack: Color-Code Deals by Priority"
   - Must contain "GoHighLevel" or "GHL"
   - Lead with the benefit or pain point, not the action

2. DESCRIPTION — max {DESC_MAX} characters
   - Lead with the problem or outcome, never "Learn how to..."
   - Include a specific number or concrete detail
   - End with curiosity or a soft CTA
   - Make the reader think "that's exactly what I need"

Return ONLY this JSON:
{{
  "title": "new title",
  "description": "new description"
}}"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(message, script="8-seo-optimizer")

    raw = message.content[0].text.strip()
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError(f"Content Writer did not return valid JSON: {raw[:200]}")

    result = json.loads(match.group())
    log(f"  New title ({len(result['title'])} chars): {result['title']}")
    log(f"  New desc ({len(result['description'])} chars): {result['description'][:80]}...")
    return result


def generate_content_expansion(page: dict, research: dict) -> dict:
    """Expand content for an almost-page-1 post + rewrite its title/description."""
    post = page["post"]
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    existing_content = post.get("html_content", "")
    # Get existing H2s to avoid duplication
    existing_h2s = re.findall(r'<h2[^>]*>(.*?)</h2>', existing_content, re.IGNORECASE)
    existing_h2_list = "\n".join(f"- {h}" for h in existing_h2s) or "None found"

    serp_context = "\n".join(
        f"- {r['title']}: {r['snippet']}" for r in research["serp_results"]
    ) or "No SERP data."

    reddit_context = "\n".join(
        f"- {q}" for q in research["reddit_questions"]
    ) or "No Reddit questions."

    affiliate_url = f"{GHL_AFFILIATE_LINK}&utm_source=blog&utm_medium=article&utm_campaign={post.get('slug', '')}"

    prompt = f"""You are an SEO content expander. This blog post ranks at position {page.get('position', '?')} — almost page 1. Add 300-600 words of new depth to push it higher.

CURRENT TITLE: {post.get('title', '')}
CURRENT DESCRIPTION: {post.get('description', '')[:200]}
POSITION: {page.get('position', '?')} | IMPRESSIONS: {page.get('impressions', '?')}

EXISTING H2 SECTIONS (do NOT duplicate these):
{existing_h2_list}

WHAT COMPETITORS COVER (find gaps to fill):
{serp_context}

REDDIT QUESTIONS (use as FAQ if relevant):
{reddit_context}

AFFILIATE LINK: {affiliate_url}

GENERATE:

1. NEW TITLE — max {TITLE_MAX} chars, benefit-first, must contain "GoHighLevel" or "GHL"
2. NEW DESCRIPTION — max {DESC_MAX} chars, problem-first
3. ADDITIONAL HTML SECTIONS — 2-3 new H2 sections that fill gaps competitors cover but we don't.
   Each H2 must have id="section-N" (continue numbering from existing sections).
   Include one FAQ section if Reddit questions are relevant:
   <div style="background:#f8f9fa;padding:24px;border-radius:8px;margin:36px 0;">
   <h2 style="margin-top:0;">Frequently Asked Questions</h2>
   <h3>Question?</h3><p>Answer.</p>
   </div>
4. FAQ SCHEMA (if FAQ added):
   <script type="application/ld+json">
   {{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[...]}}
   </script>

RULES:
- 300-600 words of NEW content only
- Match the existing writing style and tone
- Do NOT include <html>, <head>, or <body> tags
- Replace AFFILIATE_URL with the actual affiliate link
- Write as William Welch, GoHighLevel expert

Return ONLY this JSON:
{{
  "title": "new title",
  "description": "new description",
  "additional_html": "the new H2 sections + FAQ to APPEND to existing content",
  "word_count": 450
}}"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(message, script="8-seo-optimizer")

    raw = message.content[0].text.strip()
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError(f"Content Writer did not return valid JSON: {raw[:200]}")

    result = json.loads(match.group())
    log(f"  New title ({len(result['title'])} chars): {result['title']}")
    log(f"  Content expansion: +{result.get('word_count', '?')} words")
    return result


def generate_rewrites(page: dict, research: dict) -> dict:
    """Route to the right writer based on action type."""
    action = page.get("action", "rewrite_meta")
    log(f"  Content Writer [{action}]: {page['slug']}")

    if action == "expand_content":
        return generate_content_expansion(page, research)
    else:
        return generate_meta_rewrite(page, research)


# ══════════════════════════════════════════════════════════════════════════════
# ROLE 4: Fact Checker — Validate output quality
# ══════════════════════════════════════════════════════════════════════════════
def fact_check(rewrites: dict, page: dict) -> dict | None:
    """
    Validate the rewritten content before it goes live.
    Returns the rewrites if approved, None if rejected.
    """
    issues = []
    title = rewrites.get("title", "")
    description = rewrites.get("description", "")
    post = page["post"]

    # Title checks
    if len(title) > TITLE_MAX:
        issues.append(f"Title too long: {len(title)} chars (max {TITLE_MAX})")
    if len(title) < 15:
        issues.append(f"Title too short: {len(title)} chars")
    if not re.search(r'GoHighLevel|GHL', title, re.IGNORECASE):
        issues.append("Title missing 'GoHighLevel' or 'GHL'")
    if title.lower() == post.get("title", "").lower():
        issues.append("Title unchanged from original")

    # Description checks
    if len(description) > DESC_MAX:
        issues.append(f"Description too long: {len(description)} chars (max {DESC_MAX})")
    if len(description) < 50:
        issues.append(f"Description too short: {len(description)} chars")
    if description.lower().startswith("learn how to"):
        issues.append("Description starts with 'Learn how to' — should lead with benefit/problem")

    # Content expansion checks
    additional_html = rewrites.get("additional_html", "")
    if additional_html:
        # Check for fabricated claims
        if re.search(r'\d{1,3}%\s+(increase|decrease|improvement|growth)', additional_html, re.IGNORECASE):
            issues.append("Content contains specific percentage claims — verify these are real")
        # Check HTML structure
        h2_count = len(re.findall(r'<h2', additional_html))
        if h2_count < 1:
            issues.append("Content expansion has no H2 sections")
        # Check for broken section IDs
        if '<h2' in additional_html and 'id="section-' not in additional_html:
            issues.append("H2 sections missing id='section-N' attributes")

    if issues:
        log(f"  Fact Checker ISSUES ({len(issues)}):")
        for issue in issues:
            log(f"    ⚠ {issue}")

        # Hard failures — reject
        hard_fails = [i for i in issues if "unchanged" in i.lower() or "too short" in i.lower()]
        if hard_fails:
            log(f"  Fact Checker REJECTED — hard failures: {hard_fails}")
            return None

        # Soft issues — auto-fix what we can
        if len(title) > TITLE_MAX:
            rewrites["title"] = title[:TITLE_MAX - 1].rsplit(" ", 1)[0]
            log(f"  Auto-fixed: truncated title to {len(rewrites['title'])} chars")
        if len(description) > DESC_MAX:
            rewrites["description"] = description[:DESC_MAX - 1].rsplit(" ", 1)[0]
            log(f"  Auto-fixed: truncated description to {len(rewrites['description'])} chars")

    log(f"  Fact Checker APPROVED")
    return rewrites


# ══════════════════════════════════════════════════════════════════════════════
# ROLE 5: Engineer — Apply changes, update cooldown, notify
# ══════════════════════════════════════════════════════════════════════════════
def apply_changes(page: dict, rewrites: dict) -> dict:
    """Apply the approved changes to the post JSON files."""
    slug = page["slug"]
    post = page["post"]
    action = page.get("action", "rewrite_meta")

    # Record before state
    before = {
        "title": post.get("title", ""),
        "description": post.get("description", ""),
    }

    # Validate output language matches post language before writing
    post_lang = _post_language(post)
    if post_lang in ("es", "ar"):
        import re as _re
        new_title = rewrites["title"]
        new_desc = rewrites["description"]
        if post_lang == "ar":
            arabic_re = _re.compile(r"[\u0600-\u06FF]")
            if not arabic_re.search(new_desc):
                log(f"  ❌ Language mismatch: /ar/ post got non-Arabic description — skipping write")
                raise ValueError(f"Rewrite language mismatch for {slug}: expected Arabic")
        elif post_lang == "es":
            spanish_signals = len(_re.findall(r"[ñáéíóúü¿¡]", new_desc, _re.IGNORECASE))
            english_stopwords = sum(1 for w in _re.findall(r"[a-z]+", new_desc.lower())
                                    if w in {"the", "and", "for", "with", "your", "free", "step", "how", "to", "learn"})
            if spanish_signals == 0 and english_stopwords >= 2:
                log(f"  ❌ Language mismatch: /es/ post got English description — skipping write")
                raise ValueError(f"Rewrite language mismatch for {slug}: expected Spanish")

    # Apply title + description
    post["title"] = rewrites["title"]
    post["description"] = rewrites["description"]
    post["seo_optimized_at"] = datetime.now().isoformat()
    post["seo_optimization_action"] = action

    # Apply content expansion
    words_added = 0
    if action == "expand_content" and rewrites.get("additional_html"):
        existing = post.get("html_content", "")
        post["html_content"] = existing + "\n\n" + rewrites["additional_html"]
        words_added = rewrites.get("word_count", 0)

    # Save to both directories
    saved = 0
    for posts_dir in [SITE_POSTS_DIR, PIPELINE_POSTS_DIR]:
        post_file = posts_dir / f"{slug}.json"
        if posts_dir.exists():
            post_file.write_text(json.dumps(post, indent=2, ensure_ascii=False))
            saved += 1
            log(f"  Saved: {post_file}")

    if saved == 0:
        log(f"  WARNING: Could not save to any posts directory")

    # Update cooldown
    cooldowns = load_cooldowns()
    attempt = page.get("attempt", 1)
    cooldowns[slug] = {
        "action": action,
        "flagged_at": datetime.now().isoformat(),
        "attempt": attempt,
        "metrics_at_flag": {
            "impressions": page.get("impressions", 0),
            "ctr": page.get("ctr", 0),
            "position": page.get("position", 0),
        },
        "changes": {
            "old_title": before["title"],
            "new_title": rewrites["title"],
            "old_description": before["description"],
            "new_description": rewrites["description"],
            "words_added": words_added,
        },
    }
    save_cooldowns(cooldowns)

    # Build changelog entry
    entry = {
        "date": datetime.now().isoformat(),
        "slug": slug,
        "action": action,
        "attempt": attempt,
        "position_before": page.get("position", 0),
        "impressions_before": page.get("impressions", 0),
        "ctr_before": page.get("ctr", 0),
        "old_title": before["title"],
        "new_title": rewrites["title"],
        "old_description": before["description"],
        "new_description": rewrites["description"],
        "words_added": words_added,
        "position_28d": None,
        "ctr_28d": None,
        "outcome": None,
    }
    changelog = load_changelog()
    changelog.append(entry)
    save_changelog(changelog)

    # Send Slack notification
    send_slack_update(entry)

    log(f"  Engineer: changes applied for {slug}")
    words_msg = f" (+{words_added}w)" if words_added else ""
    _ops_log("SEO Optimizer", f"{action}: '{before['title'][:40]}' → '{rewrites['title'][:40]}'{words_msg}", level="detail")
    return entry


# ── Slack Notifications ───────────────────────────────────────────────────────
def send_slack_update(entry: dict):
    """Send per-page before/after notification to Slack."""
    if not SLACK_WEBHOOK_URL:
        return

    action_label = "Title Rewrite" if entry["action"] == "rewrite_meta" else "Content Expansion"
    action_emoji = "🔧" if entry["action"] == "rewrite_meta" else "📝"

    msg = f"""*SEO Optimizer — {action_label}* {action_emoji}
Page: `{SITE_URL}/blog/{entry['slug']}/`
Position: {entry['position_before']} | Impressions: {entry['impressions_before']} | CTR: {entry['ctr_before']}%

*Before:*
  Title: {entry['old_title']}
  Desc: {entry['old_description'][:120]}...

*After:*
  Title: {entry['new_title']}
  Desc: {entry['new_description'][:120]}..."""

    if entry["words_added"] > 0:
        msg += f"\n\n*Content expanded:* +{entry['words_added']} words"

    if entry.get("attempt", 1) > 1:
        msg += f"\n_Retry attempt #{entry['attempt']}_"

    msg += f"\n\nCooldown: {COOLDOWN_DAYS} days"

    try:
        data = json.dumps({"text": msg}).encode("utf-8")
        req = Request(SLACK_WEBHOOK_URL, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                log(f"  Slack notification sent for {entry['slug']}")
            else:
                log(f"  Slack returned status {resp.status}")
    except Exception as e:
        log(f"  Slack notification failed (non-fatal): {e}")


def send_slack_summary(results: dict):
    """Send end-of-run summary to Slack."""
    if not SLACK_WEBHOOK_URL:
        return
    if results["pages_optimized"] == 0:
        return

    details = "\n".join(
        f"  • {d['slug'][:50]} ({d['action']}) — was pos {d['position_before']}, {d['impressions_before']} impr"
        for d in results["details"]
    )

    msg = f"""*SEO Optimizer — Weekly Summary* 📊
Pages optimized: {results['pages_optimized']}
Title rewrites: {results['rewrites']}
Content expansions: {results['expansions']}

Optimized pages:
{details}"""

    try:
        data = json.dumps({"text": msg}).encode("utf-8")
        req = Request(SLACK_WEBHOOK_URL, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as resp:
            pass
    except Exception as e:
        log(f"  Slack summary failed (non-fatal): {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN — Orchestrate all 5 roles
# ══════════════════════════════════════════════════════════════════════════════
def main(max_pages: int = None, force: bool = False) -> dict:
    """
    Run the SEO Optimizer pipeline.
    Args:
        max_pages: Override MAX_PAGES_PER_CYCLE
        force: Skip the weekly gate check
    Returns:
        Summary dict for scheduler.py to include in reports.
    """
    log("=" * 50)
    log("SEO Optimizer starting")

    if not force and not should_run():
        return {"pages_optimized": 0, "rewrites": 0, "expansions": 0, "details": [], "skipped": True}

    if max_pages is None:
        max_pages = MAX_PAGES_PER_CYCLE

    # Role 1: GSC Analyst
    improvements = load_improvements()
    if not improvements:
        log("No improvements flagged — nothing to optimize")
        save_run_state({"pages_optimized": 0, "rewrites": 0, "expansions": 0})
        return {"pages_optimized": 0, "rewrites": 0, "expansions": 0, "details": []}

    pages = analyze_and_prioritize(improvements, max_pages)
    if not pages:
        log("No eligible pages after filtering — all on cooldown or parked")
        save_run_state({"pages_optimized": 0, "rewrites": 0, "expansions": 0})
        return {"pages_optimized": 0, "rewrites": 0, "expansions": 0, "details": []}

    results = {
        "pages_optimized": 0,
        "rewrites": 0,
        "expansions": 0,
        "details": [],
    }

    for page in pages:
        slug = page["slug"]
        action = page.get("action", "rewrite_meta")
        log(f"\n── Optimizing: {slug} ({action}) ──")

        try:
            # Role 2: Researcher
            research = do_research(page)

            # Role 3: Content Writer
            rewrites = generate_rewrites(page, research)

            # Role 4: Fact Checker
            approved = fact_check(rewrites, page)
            if not approved:
                log(f"  SKIPPED: fact check rejected {slug}")
                continue

            # Role 5: Engineer
            entry = apply_changes(page, approved)

            results["pages_optimized"] += 1
            if action == "expand_content":
                results["expansions"] += 1
            else:
                results["rewrites"] += 1
            results["details"].append(entry)

        except Exception as e:
            log(f"  ERROR processing {slug}: {e}")
            continue

        # Brief pause between pages
        time.sleep(2)

    # Send summary
    send_slack_summary(results)
    save_run_state(results)

    log(f"\nSEO Optimizer complete: {results['pages_optimized']} pages optimized "
        f"({results['rewrites']} rewrites, {results['expansions']} expansions)")
    return results


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    limit = None
    for arg in sys.argv[1:]:
        if arg.isdigit():
            limit = int(arg)
    main(max_pages=limit, force=force)
