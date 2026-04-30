"""
score_articles.py — Score blog articles via codex CLI against a structured rubric.

Reads post JSONs from globalhighlevel-site/posts/, sends each body to codex with
the locked rubric, parses the JSON scorecard, saves the aggregate to
forensic-data/article-scores-{demo|full}.json.

Usage:
  # demo on 10 curated articles
  python3 scripts/score_articles.py --demo

  # full run on all 946 articles
  python3 scripts/score_articles.py --full

  # specific slugs
  python3 scripts/score_articles.py --slugs slug1 slug2

Auth: relies on `codex` CLI being logged in (ChatGPT Plus subscription).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
POSTS_DIR = ROOT / "globalhighlevel-site" / "posts"
OUT_DIR = ROOT / "forensic-data"

DEMO_SLUGS = [
    "gohighlevel-pricing-plans-2026-complete-guide",
    "guia-completa-gohighlevel-que-es-ghl-esencial-agencia",
    "gohighlevel-plataforma-agencias-latinoamerica-3",
    "gohighlevel-plataforma-agencias-latinoamerica-1",
    "master-call-scripts-gohighlevel-boost-agent-productivity",
    "gohighlevel-setup-guide-indian-agencies-zero-to-1-lakh-mrr",
    "automate-client-support-ask-ai-agent-studio-gohighlevel",
    "how-to-create-ai-content-in-gohighlevel-better-posts-faster",
    "how-to-build-ai-agents-in-gohighlevel-agent-studio-guide",
    "gohighlevel-free-trial-30-days-extended",
]

RUBRIC = """You are scoring a blog article on a marketing/SEO recovery review. Apply the rubric below and return ONLY a single JSON object as your final response. No prose before or after. No explanation. Just the JSON.

DIMENSIONS:

1. expertness (1-10): Does this read like someone who actually used GoHighLevel (GHL), or generic SaaS-blog filler?
   - 9-10 = specific feature names, named workflows, "I've seen agencies do X with Y", quotable specifics, practitioner voice
   - 6-8 = mostly accurate, mentions GHL features by name, but generic framing — could have been written by anyone with the docs
   - 3-5 = vague benefits-talk, no specific feature usage
   - 1-2 = Wikipedia-level filler, brand-swappable

2. ai_slop (1-10): AI generation tics in the BODY (ignore the title). Higher = more sloppy.
   - 1-2 = reads human, varied sentence structure
   - 3-5 = some AI patterns (em-dashes, "delve into", listy bullets) but readable
   - 6-8 = heavy AI patterns (robust, comprehensive, in today's landscape, formulaic "Are you struggling with X?" openings)
   - 9-10 = pure ChatGPT output, listicle-with-restate-the-question, filler paragraphs

3. body_language_detected: single value — "en", "es", "en-IN", "ar", or "unclear"
   - "en-IN" triggers when body has India-specific context (₹, INR, Bangalore, Pune, Delhi, GST, Razorpay, UPI, A2P-India)
   - otherwise pick the dominant language

4. corrected_language: if body_language_detected disagrees with the metadata language field, return what the metadata SHOULD be (e.g., "en-IN"). If they agree, return null.

5. metadata_language_match: "yes" / "no" / "empty"
   - "yes" = body language matches metadata language
   - "no" = body language disagrees with metadata
   - "empty" = metadata language field is empty/missing

6. topic_match: "yes" / "no"
   - "yes" = body topic matches assigned category
   - "no" = body topic should be in a different category

7. suggested_category: if topic_match is "no", return the better category from this list: "AI & Automation", "Email & Deliverability", "SMS & Messaging", "CRM & Contacts", "Payments & Commerce", "Analytics & Reporting", "Phone & Voice", "Agency & Platform", "GoHighLevel India", "GoHighLevel en Español". If topic_match is "yes", return null.

8. thin_content: "yes" / "no"
   - "yes" = body is <500 words AND not a Q&A/quick-tip type post
   - "no" = body has substantive depth

9. verdict: one of:
   - "keep" = everything matches, article is good as-is
   - "rewrite_meta" = article is good but metadata labels are wrong (easy fix)
   - "rewrite_body" = labels right but article is slop
   - "consolidate" = near-duplicate of another article (versioned slug or cluster member with same intent)
   - "delete" = both wrong, not worth saving

10. notes: 1 sentence max, only if something is unusual (e.g., "body is great but tagged wrong language"). Empty string if nothing unusual.

INPUT FORMAT BELOW. Return JSON only.
"""


def strip_html(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r"<script[^<]*</script>", " ", html, flags=re.S)
    text = re.sub(r"<style[^<]*</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_prompt(post: dict, body_text: str) -> str:
    return f"""{RUBRIC}

CURRENT METADATA:
slug: {post.get('slug', '')}
title: {post.get('title', '')}
language: {post.get('language') or 'EMPTY'}
category: {post.get('category') or 'EMPTY'}

BODY (first 4000 chars to stay under token limit):
{body_text[:4000]}

Return ONLY the JSON scorecard now."""


def run_codex(prompt):
    """Run codex exec with prompt, return parsed JSON scorecard or None on failure."""
    try:
        result = subprocess.run(
            ["codex", "exec", prompt, "-c", 'model_reasoning_effort="low"', "--json"],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except FileNotFoundError:
        print("ERROR: codex CLI not found. Run `which codex` to verify install.", file=sys.stderr)
        sys.exit(1)

    # Parse JSONL output, find the agent_message
    agent_text = ""
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "item.completed":
            item = obj.get("item", {})
            if item.get("type") == "agent_message":
                agent_text = item.get("text", "")

    if not agent_text:
        return {"error": "no_agent_message", "stdout": result.stdout[:500], "stderr": result.stderr[:500]}

    # Extract JSON object from agent_text (it might have backticks or prose)
    # Try to find {...} block
    match = re.search(r"\{.*\}", agent_text, re.S)
    if not match:
        return {"error": "no_json_in_response", "raw": agent_text[:500]}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        return {"error": f"json_parse_failed: {e}", "raw": agent_text[:500]}


def score_post(slug: str) -> dict:
    f = POSTS_DIR / f"{slug}.json"
    if not f.exists():
        return {"slug": slug, "error": "post_not_found"}

    post = json.load(open(f, encoding="utf-8"))
    body_html = str(post.get("html_content", "") or post.get("body", "") or post.get("content", ""))
    body_text = strip_html(body_html)
    word_count = len(body_text.split())

    print(f"  scoring {slug} ({word_count} words)...", flush=True)
    t0 = time.time()
    prompt = build_prompt(post, body_text)
    score = run_codex(prompt)
    elapsed = time.time() - t0

    score = score or {"error": "empty_response"}
    score["slug"] = slug
    score["word_count"] = word_count
    score["live_url"] = f"https://globalhighlevel.com/blog/{slug}/"
    score["json_path"] = f"globalhighlevel-site/posts/{slug}.json"
    score["original_metadata"] = {
        "language": post.get("language") or "",
        "category": post.get("category") or "",
        "title": post.get("title", "")[:100],
    }
    score["scoring_time_s"] = round(elapsed, 1)
    score["scored_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Score the 10-post demo set")
    parser.add_argument("--full", action="store_true", help="Score all 946 posts")
    parser.add_argument("--slugs", nargs="*", help="Score specific slugs")
    parser.add_argument("--out", default=None, help="Output JSON file (default auto-named)")
    args = parser.parse_args()

    if args.demo:
        slugs = DEMO_SLUGS
        out_file = args.out or str(OUT_DIR / "article-scores-demo.json")
    elif args.full:
        slugs = sorted(p.stem for p in POSTS_DIR.glob("*.json"))
        out_file = args.out or str(OUT_DIR / "article-scores.json")
    elif args.slugs:
        slugs = args.slugs
        out_file = args.out or str(OUT_DIR / "article-scores-custom.json")
    else:
        parser.error("Need one of --demo, --full, --slugs")

    print(f"Scoring {len(slugs)} posts. Output: {out_file}")
    OUT_DIR.mkdir(exist_ok=True)

    results = []
    for i, slug in enumerate(slugs, 1):
        print(f"[{i}/{len(slugs)}]", end=" ", flush=True)
        result = score_post(slug)
        results.append(result)
        # Incremental save in case of interruption
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({"results": results, "completed": i, "total": len(slugs)}, f, indent=2)

    print(f"\nDone. {len(results)} results saved to {out_file}")


if __name__ == "__main__":
    main()
