"""
8-seo-optimizer.py — THIN DISPATCHER (was 859 lines, now ~180)

Reads ~/.claude/skills/fix-page-snippet/SKILL.md as the system prompt and
calls Claude with per-page context. ALL judgment lives in the skill markdown.
This script does only deterministic plumbing.

Flow (each run):
  1. Filter candidates (rank 4-10, imps>=50, CTR<1%, NOT in cooldown)
  2. For each top-N: call Claude with SKILL.md as system prompt
  3. Validate (≤65 title, ≤160 meta) → write post JSON → log cooldown
  4. Print summary; --dry-run prints proposed rewrites without writing

When the skill's --audit appends new self-improvement rules to SKILL.md,
the next cron run automatically uses them. NO code change needed.

Re-enable in scheduler.py Step 0c after a clean dry-run.
"""

import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Sheets logging config — same tracker as the rest of the GHL pipeline
TRACKING_SHEET_ID = "1A2eD2LeBpWFjDMe6W9BZbN6FvfW-em_7gD002pJD7_E"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SEO_CHANGELOG_TAB = "SEO Changelog"

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
GSC_FILE = BASE_DIR / "data" / "gsc-stats.json"
COOLDOWN_FILE = BASE_DIR / "data" / "seo-cooldown.json"
def _resolve_skill_path() -> Path:
    """VPS-safe: prefer bundled-in-repo skill (deployed via scp) over local ~/.claude."""
    bundled = BASE_DIR / "skill-refs" / "fix-page-snippet" / "SKILL.md"
    if bundled.exists():
        return bundled
    return Path.home() / ".claude" / "skills" / "fix-page-snippet" / "SKILL.md"

SKILL_PATH = _resolve_skill_path()
POSTS_DIR = BASE_DIR.parent / "globalhighlevel-site" / "posts"
SITE_BASE = "https://globalhighlevel.com"

COOLDOWN_DAYS = {"rewrite_meta": 28, "expand_content": 90, "consolidation": 56}
MAX_PAGES_PER_CYCLE = 5
MODEL = "claude-sonnet-4-6"  # judgment-heavy work; Sonnet > Haiku for this

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [SEO-OPT] {msg}", flush=True)


def slug_from_url(url: str) -> str:
    return url.replace(SITE_BASE + "/blog/", "").replace(SITE_BASE + "/", "").strip("/")


def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def find_candidates() -> list:
    """Deterministic filter — robot work only."""
    if not GSC_FILE.exists():
        log("No GSC data found")
        return []
    gsc = json.load(open(GSC_FILE))
    cool = json.load(open(COOLDOWN_FILE)) if COOLDOWN_FILE.exists() else {}

    today = datetime.now()
    locked = set()
    for slug, e in cool.items():
        days = COOLDOWN_DAYS.get(e.get("action", ""), 28)
        try:
            unlock = datetime.fromisoformat(e["flagged_at"].split(".")[0]) + timedelta(days=days)
            if unlock > today:
                locked.add(slug.strip("/"))
        except Exception:
            pass

    out = []
    for r in gsc.get("pages", []):
        slug = slug_from_url(r["page"])
        if slug in ("", "/") or slug in locked:
            continue
        if r["impressions"] < 50 or r["ctr"] >= 1.0:
            continue
        if not (4 <= r["position"] <= 10):
            continue
        out.append({**r, "_slug": slug})
    out.sort(key=lambda r: -r["impressions"])
    return out[:MAX_PAGES_PER_CYCLE]


def infer_target_query(page_url: str, gsc: dict) -> str:
    """Best-guess: top query for any page is the query with most impressions overall."""
    queries = sorted(gsc.get("queries", []), key=lambda q: -q["impressions"])
    return queries[0]["query"] if queries else "gohighlevel"


def run_skill_against_page(page: dict, post_data: dict, target_query: str) -> dict | None:
    """Latent work — call Claude with SKILL.md as system prompt.

    Returns dict with new_title, new_description, lever_title, lever_meta,
    reason. Returns None if skipped or invalid.
    """
    if not SKILL_PATH.exists():
        log(f"ERROR: SKILL.md not at {SKILL_PATH}")
        return None
    if not client:
        log("ERROR: ANTHROPIC_API_KEY missing")
        return None

    skill_md = SKILL_PATH.read_text()
    article = strip_html(post_data.get("html_content", ""))[:1500]

    user_msg = f"""Apply /fix-page-snippet to this page following Phases 1-5 of your skill.

URL: {page['page']}
TARGET QUERY: {target_query}
GSC: imps={page['impressions']}, clicks={page['clicks']}, ctr={page['ctr']}%, rank={page['position']}
CATEGORY: {post_data.get('category', 'unknown')}

CURRENT TITLE ({len(post_data['title'])} chars):
{post_data['title']}

CURRENT META ({len(post_data['description'])} chars):
{post_data['description']}

ARTICLE OPENING (first 1500 chars):
{article}

Phase 2 (SERP research): SKIP — no live web access in this context. Apply judgment from your system prompt rules without live SERP data.

CRITICAL OUTPUT RULES:
- Respond with ONLY a JSON object, nothing else.
- No prose before the JSON. No prose after.
- No code fences. No markdown.
- Start your response with `{{` and end with `}}`.
- Put your reasoning INSIDE the "reason" field, not as separate text.

Schema:
{{
  "new_title": "...",
  "new_description": "...",
  "lever_title": "<one of: specific-features-named, time-or-number-promise, contrarian-framing, pain-first, outcome-first>",
  "lever_meta": "<one of: mirror-article-pain, list-industries-first, comparison-hook, news-framing, outcome-promise>",
  "reason": "one sentence explaining lever choice",
  "skip": false
}}

If the rewrite would only beat current on <2 of 4 tests, set skip=true with reason. If current scores ≥3 of 4 (hard gate), set skip=true. If proposed claim isn't supported by the article body (fact-check gate), set skip=true."""

    def _parse(text: str) -> dict | None:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except Exception:
            pass
        # Fallback: find largest balanced {...} block in the response
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception as e:
                log(f"  Parse error (fallback): {e}")
                return None
        log(f"  Parse error: no JSON found. First 200 chars: {text[:200]}")
        return None

    def _length_ok(r: dict) -> tuple[bool, str]:
        t_over = len(r.get("new_title", "")) - 65
        m_over = len(r.get("new_description", "")) - 160
        if t_over <= 0 and m_over <= 0:
            return True, ""
        msgs = []
        if t_over > 0:
            msgs.append(f"title is {len(r['new_title'])} chars (limit 65, trim {t_over})")
        if m_over > 0:
            msgs.append(f"meta is {len(r['new_description'])} chars (limit 160, trim {m_over})")
        return False, "; ".join(msgs)

    conversation = [{"role": "user", "content": user_msg}]
    result = None

    for attempt in range(3):  # initial + 2 retries
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=[{"type": "text", "text": skill_md, "cache_control": {"type": "ephemeral"}}],
                messages=conversation,
            )
        except Exception as e:
            log(f"  API error (attempt {attempt+1}): {e}")
            return None

        assistant_text = resp.content[0].text
        result = _parse(assistant_text)
        if not result:
            return None

        if result.get("skip"):
            log(f"  Skill skipped: {result.get('reason', 'no reason')}")
            return None

        ok, why = _length_ok(result)
        if ok:
            return result

        if attempt < 2:
            log(f"  Length retry {attempt+1}: {why}")
            conversation.append({"role": "assistant", "content": assistant_text})
            conversation.append({"role": "user", "content": (
                f"Length violation: {why}. Trim to fit. Keep the same lever and "
                "specificity — just cut filler words. Return ONLY the JSON object, "
                "no explanation, no code fences."
            )})
        else:
            log(f"  Reject after retries: {why}")
            return None

    return None


def get_sheets_service():
    """Returns Google Sheets service client OR None if no Sheet-write auth available.

    Mirrors the verticals_measure.py auth pattern:
      - Trigger/cron context: GOOGLE_SERVICE_ACCOUNT_KEY_B64 env var (SA w/ sheets scope)
      - Local: returns None (local token-gsc.json doesn't have sheets scope)
    """
    sa_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY_B64", "")
    if not sa_b64:
        log("  Sheets: no GOOGLE_SERVICE_ACCOUNT_KEY_B64 env (local context — Sheet write skipped)")
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        info = json.loads(base64.b64decode(sa_b64))
        creds = service_account.Credentials.from_service_account_info(info, scopes=SHEETS_SCOPES)
        return build("sheets", "v4", credentials=creds, cache_discovery=False)
    except Exception as e:
        log(f"  Sheets: auth failed ({e}) — skipping Sheet write")
        return None


def log_to_sheet(sheets, slug: str, page: dict, rewrite: dict, old_title: str, old_desc: str) -> bool:
    """Append one row to the SEO Changelog tab. Returns True on success."""
    if sheets is None:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    unlock = (datetime.now() + timedelta(days=28)).strftime("%Y-%m-%d")
    page_path = f"/blog/{slug}/"
    change_type = "Meta rewrite (title + description) — via thin dispatcher /fix-page-snippet"
    description = (
        f"Old title: '{old_title}' → New: '{rewrite['new_title']}'. "
        f"Old meta replaced with: '{rewrite['new_description']}'. "
        f"Reason: {rewrite.get('reason', 'no reason given')}. "
        f"Lever: {rewrite.get('lever_title','?')} + {rewrite.get('lever_meta','?')}."
    )
    impact = (
        f"Baseline: {page['impressions']} impr, {page['clicks']} clicks, "
        f"{page['ctr']}% CTR, rank {page['position']}. "
        f"Locked until {unlock}. Measure lift: {unlock}."
    )
    row = [today, page_path, change_type, description, impact]
    try:
        sheets.spreadsheets().values().append(
            spreadsheetId=TRACKING_SHEET_ID,
            range=f"{SEO_CHANGELOG_TAB}!A:E",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        return True
    except Exception as e:
        log(f"  Sheets: append failed ({e})")
        return False


def apply_rewrite(slug: str, page: dict, post_data: dict, rewrite: dict) -> bool:
    """Write post JSON + cooldown entry. Returns True on success."""
    post_path = POSTS_DIR / f"{slug}.json"
    if not post_path.exists():
        log(f"  ERROR: post file not found: {post_path}")
        return False

    old_title = post_data["title"]
    old_desc = post_data["description"]

    post_data["title"] = rewrite["new_title"]
    post_data["description"] = rewrite["new_description"]
    with open(post_path, "w") as f:
        json.dump(post_data, f, indent=2, ensure_ascii=False)

    cool = json.load(open(COOLDOWN_FILE)) if COOLDOWN_FILE.exists() else {}
    now = datetime.now()
    cool[slug] = {
        "action": "rewrite_meta",
        "flagged_at": now.isoformat(),
        "locked_until": (now + timedelta(days=28)).isoformat(),
        "attempt": cool.get(slug, {}).get("attempt", 0) + 1,
        "metrics_at_flag": {
            "impressions": page["impressions"],
            "clicks": page["clicks"],
            "ctr": page["ctr"],
            "position": page["position"],
        },
        "changes": {
            "old_title": old_title,
            "new_title": rewrite["new_title"],
            "old_description": old_desc,
            "new_description": rewrite["new_description"],
        },
        "lever_title": rewrite.get("lever_title"),
        "lever_meta": rewrite.get("lever_meta"),
        "reason": rewrite.get("reason"),
        "source": "8-seo-optimizer.py (thin dispatcher → /fix-page-snippet)",
    }
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(cool, f, indent=2, ensure_ascii=False)
    return True


def main(dry_run: bool = False):
    """Entry point matching old 8-seo-optimizer.py contract."""
    log(f"Starting (dry_run={dry_run})")

    candidates = find_candidates()
    if not candidates:
        log("No candidates")
        return {"skipped": False, "pages_optimized": 0, "rewrites": 0, "details": []}

    log(f"Found {len(candidates)} candidates")
    gsc = json.load(open(GSC_FILE))
    sheets = None if dry_run else get_sheets_service()
    details = []
    rewrites_count = 0
    sheet_logged = 0

    for page in candidates:
        slug = page["_slug"]
        post_path = POSTS_DIR / f"{slug}.json"
        if not post_path.exists():
            log(f"  SKIP {slug}: post file missing")
            continue
        post_data = json.load(open(post_path))
        old_title = post_data["title"]
        old_desc = post_data["description"]
        target_query = infer_target_query(page["page"], gsc)

        log(f"\n→ {slug} (imps={page['impressions']} rank={page['position']})")
        log(f"  Current title: {old_title}")

        rewrite = run_skill_against_page(page, post_data, target_query)
        if not rewrite:
            details.append({"slug": slug, "status": "skipped"})
            continue

        log(f"  Proposed title: {rewrite['new_title']}")
        log(f"  Proposed meta:  {rewrite['new_description']}")
        log(f"  Lever: {rewrite.get('lever_title')} + {rewrite.get('lever_meta')}")
        log(f"  Reason: {rewrite.get('reason')}")

        if dry_run:
            details.append({"slug": slug, "status": "dry-run", "rewrite": rewrite})
            continue

        if apply_rewrite(slug, page, post_data, rewrite):
            rewrites_count += 1
            if log_to_sheet(sheets, slug, page, rewrite, old_title, old_desc):
                sheet_logged += 1
                log(f"  Sheet: logged to SEO Changelog ✓")
            details.append({"slug": slug, "status": "applied", "rewrite": rewrite})
        else:
            details.append({"slug": slug, "status": "apply-failed"})

    log(f"\nDone. Rewrites applied: {rewrites_count}, sheet rows: {sheet_logged}, dry-run: {dry_run}")
    return {
        "skipped": False,
        "pages_optimized": rewrites_count,
        "rewrites": rewrites_count,
        "sheet_rows_logged": sheet_logged,
        "expansions": 0,
        "details": details,
    }


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    result = main(dry_run=dry)
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, indent=2))
