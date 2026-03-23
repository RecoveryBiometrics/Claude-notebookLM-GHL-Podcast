"""
3-seo.py
Single Claude Haiku call: write SEO metadata and self-review in one shot.
Replaces the previous two-agent (Writer + Reviewer) approach to cut API costs.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

import anthropic
import sys; sys.path.insert(0, os.path.expanduser("~/.claude"))
from cost_logger import log_api_cost
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
TOPIC_WEIGHTS_FILE = BASE_DIR / "data" / "topic-weights.json"


def load_hot_keywords() -> list:
    """Load top-performing keywords from analytics data, if available."""
    if not TOPIC_WEIGHTS_FILE.exists():
        return []
    try:
        with open(TOPIC_WEIGHTS_FILE) as f:
            weights = json.load(f)
        return weights.get("hot_keywords", [])
    except Exception:
        return []

AFFILIATE_LINK = os.getenv(
    "GHL_AFFILIATE_LINK",
    "https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12"
)
MODEL = "claude-haiku-4-5-20251001"

REQUIRED_TAGS = ["gohighlevel", "go high level", "GHL", "CRM", "marketing automation", "agency software"]


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [SEO] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Single SEO Agent ──────────────────────────────────────────────────────────
def generate_seo(article: dict) -> dict:
    """
    Single Haiku call: generate SEO title, description, and tags,
    then self-check output against the checklist before returning.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Truncate body — title + first 800 chars is enough to understand the topic
    body_snippet = article.get("body", "")[:800]

    hot_keywords = load_hot_keywords()
    keywords_hint = ""
    if hot_keywords:
        keywords_hint = f"\nAUDIENCE INSIGHT: Based on download data, episodes about these topics get the most listens: {', '.join(hot_keywords[:8])}. Where it fits naturally, angle the title and description toward these themes.\n"

    prompt = f"""You are an SEO expert for a podcast about GoHighLevel software for digital marketing agencies.
{keywords_hint}

Article title: {article['title']}
Article category: {article.get('category', '')}
Article content (excerpt):
{body_snippet}

Generate SEO metadata for this podcast episode, then self-check it before returning.

STEP 1 — GENERATE:

1. TITLE: Under 70 characters. Formula: "How to [Action] in GoHighLevel — [Specific Benefit]". Must contain "GoHighLevel".

2. DESCRIPTION: Exactly 4 paragraphs:
   - Paragraph 1 (exact wording): "🚀 Start your FREE 30-day GoHighLevel trial: https://globalhighlevel.com/trial"
   - Paragraph 2: 2-3 sentences on what this episode covers. Use "GoHighLevel" naturally.
   - Paragraph 3: "In this episode you'll learn:" followed by 3-4 bullet points (use • symbol).
   - Paragraph 4 (exact wording): "Ready to try GoHighLevel yourself? The link above gets you a FREE 30-day trial — double the standard 14-day trial. See why thousands of agencies run their entire business on one platform."

3. TAGS: Exactly 8 comma-separated tags. Must include: gohighlevel, go high level, GHL, CRM, marketing automation, agency software. Add 2 specific tags for this topic.

STEP 2 — SELF-CHECK before returning:
- Title under 70 chars? ✓/✗
- Title contains "GoHighLevel"? ✓/✗
- Description has 3 paragraphs with CTA and affiliate link? ✓/✗
- Exactly 8 tags including all 6 required? ✓/✗
Fix anything that fails before returning.

Return only this JSON, no other text:
{{
  "title": "final title",
  "description": "final description",
  "tags": "tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8"
}}"""

    log(f"SEO generating for: {article['title'][:60]}")

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    log_api_cost(message, script="3-seo")

    raw = message.content[0].text.strip()

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError(f"SEO did not return valid JSON: {raw[:200]}")

    result = json.loads(match.group())
    log(f"  Title: {result.get('title', '')[:60]}")

    return {
        **article,
        "status": "seo_ready",
        "seoTitle": result["title"],
        "seoDescription": result["description"],
        "seoTags": result["tags"],
        "seoGeneratedAt": datetime.now().isoformat(),
        "affiliateLinkIncluded": "globalhighlevel.com/trial" in result["description"],
    }


# Allow running standalone for testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python 3-seo.py <path/to/article.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        article = json.load(f)

    result = generate_seo(article)
    print(json.dumps(result, indent=2))
