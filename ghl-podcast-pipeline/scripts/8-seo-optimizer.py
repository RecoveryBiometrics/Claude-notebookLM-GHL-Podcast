"""
8-seo-optimizer.py — THIN DISPATCHER (was 859 lines, now ~60)

WAS:  859 lines of Python with judgment baked in (5 internal "roles", scoring,
      banlist, prompts, all hardcoded). When Claude got smarter, this script
      didn't. Caused live conflict 2026-04-24 with manual /fix-page-snippet work.

NOW:  Thin dispatcher. Just does deterministic plumbing:
        1. Filter candidates (rank 4-10, imps>=50, CTR<1%, NOT in cooldown)
        2. For each top-N candidate, call Claude with the skill markdown as
           the system prompt + page-specific context as the user message
        3. Apply rewrite to post JSON, log to cooldown + Google Sheet
      All judgment (banlist, levers, scoring, audience rule) lives in:
        ~/.claude/skills/fix-page-snippet/SKILL.md
      When the skill's self-improvement appends new rules, this script
      automatically uses them on next run. NO code change needed.

STATUS: STUB — NOT YET WIRED INTO scheduler.py
        Production cutover requires:
          [ ] Implement run_skill_against_page() — call Claude API with skill
              SKILL.md as system prompt + scouting report as user message
          [ ] Test on 3-5 pages manually, compare output to interactive
              /fix-page-snippet quality
          [ ] Verify Sheet write works from headless cron context (auth)
          [ ] Re-enable Step 0c in scheduler.py after dry-run passes

WHY THIS PATTERN IS BETTER:
  • Judgment in markdown = self-improving (new rules append, no deploy)
  • Model upgrades automatically improve quality (Claude 4.8 → free lift)
  • One source of truth — manual /fix-page-snippet and cron use SAME rules
  • No more racing rewriters — both paths read same cooldown, same skill
  • 859 → 60 lines = vastly less to maintain, audit, and break
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
GSC_FILE = BASE_DIR / "data" / "gsc-stats.json"
COOLDOWN_FILE = BASE_DIR / "data" / "seo-cooldown.json"
SKILL_PATH = Path.home() / ".claude" / "skills" / "fix-page-snippet" / "SKILL.md"

COOLDOWN_DAYS = {"rewrite_meta": 28, "expand_content": 90, "consolidation": 56}
MAX_PAGES_PER_CYCLE = 5


def find_candidates() -> list:
    """Deterministic filter — robot work only. No judgment."""
    if not GSC_FILE.exists():
        return []
    gsc = json.load(open(GSC_FILE))
    cool = json.load(open(COOLDOWN_FILE)) if COOLDOWN_FILE.exists() else {}

    today = datetime.now()
    locked = set()
    for slug, e in cool.items():
        days = COOLDOWN_DAYS.get(e.get("action", ""), 28)
        try:
            if datetime.fromisoformat(e["flagged_at"].split(".")[0]) + timedelta(days=days) > today:
                locked.add(slug.strip("/"))
        except Exception:
            pass

    out = []
    for r in gsc.get("pages", []):
        slug = r["page"].replace("https://globalhighlevel.com/blog/", "").replace("https://globalhighlevel.com/", "").strip("/")
        if slug in ("", "/") or slug in locked:
            continue
        if r["impressions"] < 50 or r["ctr"] >= 1.0:
            continue
        if not (4 <= r["position"] <= 10):
            continue
        out.append(r)
    out.sort(key=lambda r: -r["impressions"])
    return out[:MAX_PAGES_PER_CYCLE]


def run_skill_against_page(page: dict) -> dict:
    """Latent work — call Claude with the skill markdown as the brain.

    TODO (production cutover):
      1. Read SKILL_PATH.read_text() as system prompt
      2. Build scouting-report user message from page data
      3. anthropic.messages.create(system=skill_md, messages=[...])
      4. Parse winning title + meta from response
      5. Apply hard gates (≤65 / ≤160 chars), assert before returning
    """
    raise NotImplementedError(
        "Stub. Implement Claude API call with SKILL.md as system prompt before re-enabling."
    )


def main():
    """Entry point matching old 8-seo-optimizer.py contract."""
    candidates = find_candidates()
    if not candidates:
        return {"skipped": False, "pages_optimized": 0, "rewrites": 0, "details": []}

    # Stub: do not actually rewrite until run_skill_against_page() is implemented.
    return {
        "skipped": True,
        "skip_reason": "Thin dispatcher stub — skill call not yet implemented",
        "candidates_found": len(candidates),
        "pages_optimized": 0,
        "rewrites": 0,
        "details": [],
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
