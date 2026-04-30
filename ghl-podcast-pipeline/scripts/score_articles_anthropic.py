"""
score_articles_anthropic.py — Score blog articles via Anthropic API (Claude Sonnet 4.6).

Uses prompt caching on the rubric (saves ~50% on input tokens) and async/parallel
batching for speed. Saves incrementally to forensic-data/article-scores.json.

Usage:
  ghl-podcast-pipeline/venv/bin/python3 ghl-podcast-pipeline/scripts/score_articles_anthropic.py --demo
  ghl-podcast-pipeline/venv/bin/python3 ghl-podcast-pipeline/scripts/score_articles_anthropic.py --full

Auth: reads ANTHROPIC_API_KEY from .env at project root.

Cost: ~$0.012 per article × 946 = ~$11 with prompt caching enabled.
Wall clock: ~15-30 min for full run with 10-way concurrency.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent.parent
POSTS_DIR = ROOT / "globalhighlevel-site" / "posts"
OUT_DIR = ROOT / "forensic-data"
ENV_FILE = ROOT / ".env"

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

MODEL = "claude-sonnet-4-6"
MAX_CONCURRENT = 10

# System prompt — gets cached, saves ~50% on input tokens across 946 calls
SYSTEM_RUBRIC = """You are scoring a blog article on a marketing/SEO recovery review for globalhighlevel.com (a GoHighLevel affiliate site). Apply the rubric below and return ONLY a single JSON object as your final response. No prose before or after. No explanation. Just the JSON.

DIMENSIONS:

1. expertness (1-10): Does this read like someone who actually used GoHighLevel (GHL), or generic SaaS-blog filler?
   - 9-10 = specific feature names, named workflows, "I've seen agencies do X with Y", quotable specifics, practitioner voice
   - 6-8 = mostly accurate, mentions GHL features by name, but generic framing — could have been written by anyone with the docs
   - 3-5 = vague benefits-talk, no specific feature usage
   - 1-2 = Wikipedia-level filler, brand-swappable

2. ai_slop (1-10): AI generation tics in the BODY ONLY (ignore the title). Higher = more sloppy.
   - 1-2 = reads human, varied sentence structure, no formulaic transitions
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
   - "consolidate" = near-duplicate of another article (versioned slug or cluster member)
   - "delete" = both wrong, not worth saving

10. notes: 1 sentence max, only if something is unusual. Empty string if nothing unusual.

OUTPUT FORMAT: respond with ONLY the JSON object, no markdown code fences, no prose. Example:
{"expertness": 8, "ai_slop": 3, "body_language_detected": "en", "corrected_language": null, "metadata_language_match": "yes", "topic_match": "yes", "suggested_category": null, "thin_content": "no", "verdict": "keep", "notes": ""}"""


def load_api_key():
    if "ANTHROPIC_API_KEY" in os.environ:
        return os.environ["ANTHROPIC_API_KEY"]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("ANTHROPIC_API_KEY not found in env or .env")


def strip_html(html):
    text = re.sub(r"<script[^<]*</script>", " ", html, flags=re.S)
    text = re.sub(r"<style[^<]*</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_user_message(post, body_text):
    return f"""CURRENT METADATA:
slug: {post.get('slug', '')}
title: {post.get('title', '')}
language: {post.get('language') or 'EMPTY'}
category: {post.get('category') or 'EMPTY'}

BODY (truncated to 4000 chars):
{body_text[:4000]}

Score this article. Return ONLY the JSON object."""


async def score_one(client, slug, sem):
    async with sem:
        f = POSTS_DIR / f"{slug}.json"
        if not f.exists():
            return {"slug": slug, "error": "post_not_found"}
        try:
            post = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            return {"slug": slug, "error": f"json_load_failed: {e}"}

        body_html = str(post.get("html_content", "") or post.get("body", "") or post.get("content", ""))
        body_text = strip_html(body_html)
        word_count = len(body_text.split())

        t0 = time.time()
        try:
            resp = await client.messages.create(
                model=MODEL,
                max_tokens=400,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_RUBRIC,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": build_user_message(post, body_text)}],
            )
            elapsed = time.time() - t0
            text = "".join(b.text for b in resp.content if hasattr(b, "text"))
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                return {"slug": slug, "error": "no_json_in_response", "raw": text[:300], "word_count": word_count}
            score = json.loads(match.group(0))
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
            score["usage"] = {
                "input": resp.usage.input_tokens,
                "output": resp.usage.output_tokens,
                "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0),
                "cache_create": getattr(resp.usage, "cache_creation_input_tokens", 0),
            }
            return score
        except Exception as e:
            return {"slug": slug, "error": f"api_call_failed: {e}", "word_count": word_count}


async def main_async(slugs, out_file):
    api_key = load_api_key()
    client = anthropic.AsyncAnthropic(api_key=api_key)
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    print(f"Scoring {len(slugs)} posts via {MODEL}, {MAX_CONCURRENT}-way concurrency.")
    print(f"Output: {out_file}")
    OUT_DIR.mkdir(exist_ok=True)

    results = []
    completed = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_create = 0
    t_start = time.time()

    tasks = [score_one(client, slug, sem) for slug in slugs]

    # Run as completed for live progress + incremental save
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        completed += 1

        usage = result.get("usage", {})
        total_input += usage.get("input", 0)
        total_output += usage.get("output", 0)
        total_cache_read += usage.get("cache_read", 0)
        total_cache_create += usage.get("cache_create", 0)

        if completed % 25 == 0 or completed == len(slugs):
            elapsed = time.time() - t_start
            rate = completed / elapsed
            eta = (len(slugs) - completed) / rate if rate > 0 else 0
            # Cost estimate (Sonnet 4.6 pricing approximate)
            cost = (total_input * 3 + total_cache_create * 3.75 + total_cache_read * 0.30 + total_output * 15) / 1_000_000
            print(f"[{completed}/{len(slugs)}] {rate:.1f}/s | elapsed {elapsed:.0f}s | eta {eta:.0f}s | running cost ~${cost:.2f}")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump({"results": results, "completed": completed, "total": len(slugs)}, f, indent=2)

    # Final save
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"results": results, "completed": completed, "total": len(slugs)}, f, indent=2)

    cost = (total_input * 3 + total_cache_create * 3.75 + total_cache_read * 0.30 + total_output * 15) / 1_000_000
    cache_savings = (total_cache_read * (3 - 0.30)) / 1_000_000
    print(f"\nDONE. {completed}/{len(slugs)} scored.")
    print(f"Total input: {total_input:,} | output: {total_output:,} | cache_read: {total_cache_read:,} | cache_create: {total_cache_create:,}")
    print(f"Cost: ~${cost:.2f}  (saved ~${cache_savings:.2f} from prompt caching)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--slugs", nargs="*")
    parser.add_argument("--out", default=None)
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

    asyncio.run(main_async(slugs, out_file))


if __name__ == "__main__":
    main()
