"""
design-homepage.py
Two-agent system: Designer → Manager review.

Uses claude-opus-4-6 (most capable model) for both agents.
Zero tolerance for made-up facts. Mobile-first. Billion-dollar standard.

Run:
  cd globalhighlevel-site
  ../ghl-podcast-pipeline/venv/bin/python3 design-homepage.py
"""

import anthropic
import os
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".." / "ghl-podcast-pipeline" / ".env")

OUTPUT   = BASE_DIR / "homepage_hero.html"
LOG_FILE = BASE_DIR / "design-log.txt"

AFFILIATE = "https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12&utm_source=globalhighlevel&utm_medium=homepage&utm_campaign=hero"
client    = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def log(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── VERIFIED FACTS ONLY ───────────────────────────────────────────────────────
# These are the ONLY facts agents are allowed to use. No inventing anything else.

VERIFIED_FACTS = """
VERIFIED FACTS — use ONLY these, invent nothing else:

Site: GlobalHighLevel (globalhighlevel.com)
Purpose: Free GoHighLevel tutorials, guides and strategies
Audience: Digital marketing agency owners, freelancers, business owners
Author: William Welch (GoHighLevel user and affiliate)

Podcast: "Go High Level" on Spotify
- 380 followers
- 6,479 all-time streams
- 25 average streams per episode
- Top episode: "GoHighLevel Conversation AI Bot" — 492 streams
- New episodes published automatically, 20 per day

Content library:
- 80+ published tutorials and guides
- Covers GoHighLevel features end-to-end
- Both written guides AND podcast episodes for every topic

The Offer:
- GoHighLevel 30-day FREE trial via affiliate link
- This is DOUBLE the standard 14-day trial — a genuine exclusive benefit
- Affiliate link: {affiliate}
- GHL starts at $97/month for Starter plan

DO NOT invent:
- Testimonials or reviews
- Income claims or revenue numbers
- Student counts or community sizes
- Any personal biography details about William beyond "GoHighLevel user and affiliate"
- Any awards, press mentions, or certifications
- Any claims about ranking, traffic, or subscriber counts beyond what's listed above
""".format(affiliate=AFFILIATE)


# ── Agent 1: Designer ─────────────────────────────────────────────────────────

DESIGNER_PROMPT = f"""You are the lead designer at a world-class digital agency. You have designed landing pages for Stripe, Linear, Vercel, and Webflow. You know exactly what separates a $10M/year affiliate site from an amateur blog.

Your job: Design a complete, stunning, high-converting homepage for GlobalHighLevel.com — a GoHighLevel tutorial site targeting agency owners and business owners worldwide.

{VERIFIED_FACTS}

════════════════════════════════════════════════
DESIGN STANDARD: BILLION-DOLLAR WEBSITE
════════════════════════════════════════════════

Study what makes these sites world-class and apply those principles:
- Stripe.com: bold typography, clean white space, confident copy
- Linear.app: dark gradient hero, precise micro-copy, no fluff
- Webflow.com: strong value prop above fold, clear audience targeting
- HubSpot affiliate pages: multiple proof points, benefit-led copy, strong CTA hierarchy

════════════════════════════════════════════════
TECHNICAL REQUIREMENTS — NON-NEGOTIABLE
════════════════════════════════════════════════

MOBILE-FIRST (this will be graded harshly):
- Include a <style> block at the very top of your output
- Write CSS mobile-first: base styles for mobile, then @media (min-width: 768px) for desktop
- Hamburger menu concept for mobile nav (visual only — CSS toggle)
- All grid layouts must stack vertically on mobile
- Font sizes must scale: smaller on mobile, larger on desktop
- Touch targets minimum 44px height on mobile
- No horizontal scroll on any screen size
- Test every section mentally at 375px width (iPhone SE)

HTML/CSS rules:
- Output starts with <style>...</style> then HTML — nothing else
- No external fonts, no CDN links, no JavaScript dependencies
- Use CSS custom properties (variables) for colors
- All affiliate links: target="_blank" rel="nofollow noopener"
- Semantic HTML: <section>, <article>, <nav>, <header>, <main>
- Images: use CSS gradients and emoji as decorative elements — no <img> tags needed

════════════════════════════════════════════════
PAGE SECTIONS (build all of these)
════════════════════════════════════════════════

1. HERO
   - Bold headline: addresses the exact pain point of agency owners considering GHL
   - Subheadline: what GlobalHighLevel gives them (free tutorials + the 30-day trial offer)
   - TWO CTAs: primary "Start Free 30-Day Trial →" (affiliate link) + secondary "Browse Tutorials"
   - Trust strip beneath CTAs: podcast stats (use verified numbers only)
   - Hero background: dark gradient (#0f172a to #1e3a5f) with subtle pattern

2. SOCIAL PROOF BAR
   - Clean strip using ONLY verified numbers: 80+ tutorials, 380 podcast followers, 6,479 streams
   - No made-up logos or company names
   - Simple stat blocks: number + label

3. WHO THIS IS FOR
   - 3 audience cards: Digital Marketing Agencies | Freelancers & Consultants | Business Owners
   - Each card: emoji icon + title + 2-line description of their specific GHL use case
   - Pain-point led, not feature-led

4. WHAT YOU GET
   - 3 benefit columns with emoji icons
   - Focus on outcomes: "Stop guessing, start scaling" not "we have tutorials"

5. THE OFFER — make this a standout section
   - Dedicated section for the 30-day free trial
   - Emphasize: DOUBLE the standard 14-day trial
   - No credit card framing, clear CTA
   - Use a contrasting background color

6. LATEST TUTORIALS
   - Section heading + subtitle
   - 3 placeholder cards styled as real tutorial cards
   - Each: category badge, title, description, "Read Guide →" link
   - Use placeholder text that represents real GHL topics (SMS automation, AI chatbot, funnels)
   - Note in HTML comment: <!-- build.py injects real posts here via id="tutorials-grid" -->
   - Give the cards container: id="tutorials-grid"

7. PODCAST SECTION
   - Promote the "Go High Level" podcast on Spotify
   - Use verified stats only
   - Spotify green (#1DB954) accent
   - CTA to Spotify (use # as href placeholder)

8. FINAL CTA
   - Strong closing section
   - Restate the 30-day offer
   - Big button
   - Dark background for contrast

════════════════════════════════════════════════
COPY STANDARDS
════════════════════════════════════════════════
- Every headline must pass the "so what?" test — if a visitor can ask "so what?", rewrite it
- CTA buttons must state the benefit, not just the action ("Start My Free 30-Day Trial" not "Click Here")
- Zero corporate jargon: no "leverage", "synergy", "ecosystem", "robust"
- Write like a confident expert talking to a peer, not a salesperson pitching a stranger
- Short sentences. Active voice. Specific > vague always.

Output: <style> block followed by complete HTML body content. Nothing else."""


# ── Agent 2: Manager ──────────────────────────────────────────────────────────

MANAGER_PROMPT = f"""You are the world's toughest conversion rate optimization director. You have reviewed landing pages for billion-dollar companies. You do not accept "good enough." You either approve or you rewrite.

Your job: Review the homepage HTML below. Grade it against every criterion. Rewrite any section that fails. Return the COMPLETE final HTML — no commentary, no explanations, just the finished page.

{VERIFIED_FACTS}

════════════════════════════════════════════════
YOUR GRADING CRITERIA — ZERO TOLERANCE
════════════════════════════════════════════════

FACTS (instant fail if violated):
- [ ] Zero made-up facts, testimonials, income claims, or biography details
- [ ] All stats match the verified facts list exactly
- [ ] No invented social proof (fake company logos, fake reviews)

MOBILE (grade every section at 375px):
- [ ] <style> block exists with proper @media queries
- [ ] Hero stacks vertically, text readable, buttons full-width on mobile
- [ ] Stats bar wraps gracefully — no overflow
- [ ] All grid/flex layouts use flex-wrap:wrap or grid with auto-fill
- [ ] Font sizes defined for both mobile and desktop
- [ ] No element causes horizontal scroll

DESIGN QUALITY:
- [ ] Looks like a $10M/year site, not a WordPress blog
- [ ] Strong visual hierarchy — eye flows naturally to the CTA
- [ ] Consistent spacing system (multiples of 8px)
- [ ] Dark hero section creates strong contrast with white content below
- [ ] Color usage is intentional — primary blue, accent for offer section

CONVERSION:
- [ ] Hero headline addresses a specific, felt pain point in under 8 words
- [ ] The 30-day free trial / double-the-standard offer is prominent and clearly differentiated
- [ ] At least 4 affiliate link placements across the page
- [ ] Every CTA button has benefit-led text (not "Submit" or "Click Here")
- [ ] Final CTA section is impossible to ignore

COPY:
- [ ] Zero corporate jargon
- [ ] Every headline passes the "so what?" test
- [ ] Subheadlines support and extend the headline — no repetition
- [ ] Short, punchy sentences throughout

════════════════════════════════════════════════
INSTRUCTIONS
════════════════════════════════════════════════
1. Go through every criterion above
2. For each failure: rewrite that section until it passes
3. Do not touch passing sections
4. Return the COMPLETE final HTML with <style> block — nothing else

HTML TO REVIEW:
"""


def strip_fences(text: str) -> str:
    text = re.sub(r"^```html?\s*\n?", "", text.strip())
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def run_designer() -> str:
    log("Agent 1 (Designer — opus-4-6) starting...")
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=10000,
        messages=[{"role": "user", "content": DESIGNER_PROMPT}]
    )
    html = strip_fences(response.content[0].text)
    log(f"Designer complete — {len(html):,} chars")
    return html


def run_manager(designer_html: str) -> str:
    log("Agent 2 (Manager — opus-4-6) reviewing...")
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=10000,
        messages=[{"role": "user", "content": MANAGER_PROMPT + designer_html}]
    )
    html = strip_fences(response.content[0].text)
    log(f"Manager complete — {len(html):,} chars")
    return html


def main():
    log("=" * 50)
    log("Homepage agents starting — opus-4-6 — zero tolerance")
    log("=" * 50)

    designer_html = run_designer()
    final_html    = run_manager(designer_html)

    OUTPUT.write_text(final_html, encoding="utf-8")
    log(f"Saved → {OUTPUT.name}")
    log("Run build.py to deploy.")


if __name__ == "__main__":
    main()
