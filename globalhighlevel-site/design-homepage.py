"""
design-homepage.py
Two-agent system for designing a high-converting homepage for globalhighlevel.com.

Agent 1 — Designer:   Writes a full conversion-optimized landing page in HTML/CSS
Agent 2 — Manager:    Reviews against a strict conversion checklist, rewrites weak sections

Run:
  cd globalhighlevel-site
  python3 design-homepage.py

Output:
  homepage_hero.html  — drop-in hero/body content for build.py
"""

import anthropic
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR   = Path(__file__).parent
load_dotenv(BASE_DIR / ".." / "ghl-podcast-pipeline" / ".env")
OUTPUT     = BASE_DIR / "homepage_hero.html"
LOG_FILE   = BASE_DIR / "design-log.txt"

AFFILIATE  = "https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12&utm_source=globalhighlevel&utm_medium=homepage&utm_campaign=hero"
PRIMARY    = "#1a73e8"
client     = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def log(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Agent 1: Designer ─────────────────────────────────────────────────────────

DESIGNER_PROMPT = f"""You are an expert conversion rate optimizer and web designer specializing in affiliate marketing landing pages.

Design a complete, high-converting homepage body for globalhighlevel.com — a GoHighLevel tutorial and resource site targeting digital marketing agencies and business owners worldwide.

GOAL: Get visitors to click the affiliate link and start a free 30-day GoHighLevel trial.
AFFILIATE LINK: {AFFILIATE}

CONTEXT:
- Site name: GlobalHighLevel
- Podcast: "Go High Level" on Spotify — 380 followers, 6,479 all-time streams, top episode 492 streams
- Content: 80+ free tutorials and guides on GoHighLevel features
- Audience: Digital marketing agency owners, freelancers, business owners considering GHL
- GHL offer: 30-day free trial (double the standard 14-day trial) via affiliate link
- Author: William Welch — GoHighLevel expert

DESIGN THE FOLLOWING SECTIONS (in order):

1. HERO — Pain-point headline, subheadline, primary CTA button, trust line beneath button
2. SOCIAL PROOF BAR — Podcast stats + "trusted by" style strip
3. WHY GOHIGHLEVEL — 3 benefit columns with icons (use emoji as icons)
4. FEATURED IN / AUTHORITY — Simple trust signals
5. LATEST TUTORIALS PREVIEW — Placeholder grid (3 cards, we'll populate dynamically)
6. PODCAST SECTION — Promote the "Go High Level" podcast with Spotify link
7. FINAL CTA SECTION — Strong closing push for the free trial

CSS REQUIREMENTS:
- All CSS must be inline styles only — no <style> tags, no external CSS
- Primary color: {PRIMARY}
- Design must be mobile-responsive using flexbox/grid with inline styles
- Professional, clean, modern — looks like a real authority site
- Hero background: dark gradient or GHL blue
- Use real HTML entities for special characters

HTML REQUIREMENTS:
- Return ONLY the body content — no <html>, <head>, <body>, <style> tags
- No markdown, no code fences — raw HTML only
- All links to the affiliate URL must have target="_blank" rel="nofollow"
- The tutorial cards section should have id="tutorials" so build.py can inject real posts

CONVERSION BEST PRACTICES TO FOLLOW:
- Headline must address a specific pain point (not generic "welcome")
- CTA button text must be action-oriented (not just "click here")
- Include urgency or scarcity element
- Show the "30-day FREE trial" offer prominently — it's a stronger offer than standard 14-day
- Social proof numbers must be specific (use the real stats above)
- Every section should have at least one path to the affiliate link
- Remove all friction — make clicking feel like the obvious next step

Output the complete HTML now."""


# ── Agent 2: Manager ──────────────────────────────────────────────────────────

MANAGER_PROMPT = """You are a senior conversion rate optimization manager reviewing a landing page for an affiliate marketing site.

Your job: Review the HTML below against the conversion checklist. Rewrite any section that fails. Return the COMPLETE improved HTML — not just the changes.

CONVERSION CHECKLIST (every item must pass):
1. ✅ Hero headline addresses a specific pain point within 3 seconds of reading
2. ✅ Primary CTA button uses action language + benefit ("Start My Free 30-Day Trial")
3. ✅ The 30-day free trial offer (vs standard 14-day) is prominently shown — this is the key differentiator
4. ✅ Social proof is specific — real numbers, not vague claims
5. ✅ Benefits focus on OUTCOMES for the visitor, not features of the product
6. ✅ At least 4 affiliate link placements across the page
7. ✅ No walls of text — scannable, broken into digestible sections
8. ✅ Mobile-friendly layout (flexbox/grid with wrap)
9. ✅ Clear visual hierarchy — visitor eye flows top to bottom toward CTA
10. ✅ Final CTA section is strong — creates urgency, restates the offer, big button

FOR EACH FAILING ITEM: Rewrite that section to pass.
FOR PASSING ITEMS: Keep them exactly as-is.

Return ONLY the complete improved HTML. No commentary, no markdown fences, no explanation.

HTML TO REVIEW:
"""


def run_designer() -> str:
    log("Agent 1 (Designer) starting...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": DESIGNER_PROMPT}]
    )
    html = response.content[0].text.strip()
    # Strip any accidental markdown fences
    html = re.sub(r"^```html?\n?", "", html)
    html = re.sub(r"\n?```$", "", html)
    log(f"Designer complete — {len(html)} chars")
    return html


def run_manager(designer_html: str) -> str:
    log("Agent 2 (Manager) reviewing...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": MANAGER_PROMPT + designer_html}]
    )
    html = response.content[0].text.strip()
    html = re.sub(r"^```html?\n?", "", html)
    html = re.sub(r"\n?```$", "", html)
    log(f"Manager complete — {len(html)} chars")
    return html


def main():
    log("=" * 50)
    log("Homepage design agents starting")
    log("=" * 50)

    # Agent 1: Design
    designer_html = run_designer()

    # Agent 2: Review + improve
    final_html = run_manager(designer_html)

    # Save output
    OUTPUT.write_text(final_html, encoding="utf-8")
    log(f"Saved to {OUTPUT.name}")
    log("Done. Run build.py to deploy.")


if __name__ == "__main__":
    main()
