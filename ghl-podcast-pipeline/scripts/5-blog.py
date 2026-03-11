"""
5-blog.py
Generates an SEO blog post and saves it to globalhighlevel-site/posts/ for auto-deploy to globalhighlevel.com.

Flow:
  1. Scrape DuckDuckGo for top results on the episode topic
  2. Scrape Reddit for real user questions about the topic
  3. Claude writes a full SEO blog post using transcript + SERP data + Reddit questions
  4. Save post JSON to globalhighlevel-site/posts/{slug}.json
     → scheduler.py Step 4 git pushes to GitHub → Netlify deploys globalhighlevel.com
"""

import json
import os
import re
import time
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from bs4 import BeautifulSoup

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
LOG_FILE   = BASE_DIR / "logs" / "pipeline.log"
SITE_POSTS = BASE_DIR.parent / "globalhighlevel-site" / "posts"

ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
GHL_AFFILIATE_LINK = os.getenv("GHL_AFFILIATE_LINK")

HEADERS_DDG = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [BLOG] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── DuckDuckGo SERP Scrape ─────────────────────────────────────────────────────
def scrape_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """Scrape top DuckDuckGo results for a query. Returns list of {title, snippet, url}."""
    log(f"  Scraping DuckDuckGo: {query}")
    try:
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(
            url,
            data={"q": query},
            headers=HEADERS_DDG,
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for result in soup.select(".result__body")[:max_results + 3]:
            title_el = result.select_one(".result__title")
            snippet_el = result.select_one(".result__snippet")
            url_el = result.select_one(".result__url")
            # Skip ads (DuckDuckGo injects them with "Ad" badge)
            if result.select_one(".badge--ad"):
                continue
            if title_el and snippet_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True),
                    "url": url_el.get_text(strip=True) if url_el else "",
                })
            if len(results) >= max_results:
                break
        log(f"  Found {len(results)} SERP results")
        for r in results:
            log(f"    SERP: {r['title']}")
        return results
    except Exception as e:
        log(f"  DuckDuckGo scrape failed: {e}")
        return []


# ── Reddit Scrape ──────────────────────────────────────────────────────────────
def scrape_reddit(query: str, max_results: int = 5) -> list[str]:
    """Fetch top Reddit questions about the topic from relevant subreddits."""
    log(f"  Scraping Reddit: {query}")
    subreddits = ["GoHighLevel", "marketing", "automation", "entrepreneur"]
    questions = []

    for subreddit in subreddits:
        if len(questions) >= max_results:
            break
        try:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            params = {"q": query, "restrict_sr": 1, "sort": "top", "limit": max_results, "type": "link"}
            resp = requests.get(
                url,
                params=params,
                headers={"User-Agent": "GHLBlogBot/1.0"},
                timeout=15,
            )
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                title = post.get("data", {}).get("title", "")
                if title and title not in questions:
                    questions.append(title)
        except Exception as e:
            log(f"  Reddit r/{subreddit} failed: {e}")

    log(f"  Found {len(questions)} Reddit questions")
    for q in questions:
        log(f"    REDDIT: {q}")
    return questions[:max_results]


# ── Claude Blog Writer ─────────────────────────────────────────────────────────
def generate_blog_post(
    title: str,
    description: str,
    tags: str,
    transcript: str | None,
    serp_results: list[dict],
    reddit_questions: list[str],
    utm_campaign: str,
) -> dict:
    """Use Claude to write a full SEO blog post. Returns {html_content, meta_description, slug}."""
    log(f"  Generating blog post with Claude...")

    affiliate_url = (
        f"{GHL_AFFILIATE_LINK}"
        f"&utm_source=blog&utm_medium=article&utm_campaign={utm_campaign}"
    )

    serp_context = "\n".join(
        [f"- {r['title']}: {r['snippet']}" for r in serp_results]
    ) or "No SERP data available."

    reddit_context = "\n".join(
        [f"- {q}" for q in reddit_questions]
    ) or "No Reddit questions available."

    transcript_context = (
        f"PODCAST TRANSCRIPT (use this as your primary source):\n{transcript[:6000]}"
        if transcript
        else f"EPISODE DESCRIPTION:\n{description}"
    )

    prompt = f"""You are an expert SEO content writer. Write a comprehensive, visually styled blog post that will rank on Google for the topic below.

TOPIC: {title}
TAGS: {tags}

{transcript_context}

WHAT TOP RANKING PAGES COVER (use these to build your H2 structure — match and beat their depth):
{serp_context}

REDDIT INSIGHTS (only use posts that are actual questions ending in ? as FAQ items — do NOT use as H2 headings):
{reddit_context}

AFFILIATE LINK:
{affiliate_url}

═══════════════════════════════════════
STRUCTURE (in this exact order):
═══════════════════════════════════════

1. INTRO PARAGRAPH — hook that addresses the reader's pain point. Include affiliate link naturally here.

2. TABLE OF CONTENTS — styled jump-link box listing all H2 sections:
<div style="background:#f0f4ff;border-left:4px solid #1a73e8;padding:16px 24px;margin:28px 0;border-radius:6px;">
<p style="font-weight:700;margin:0 0 10px 0;font-size:16px;">📋 In This Guide</p>
<ul style="margin:0;padding-left:20px;">
<li><a href="#section-1" style="color:#1a73e8;text-decoration:none;">Section title</a></li>
... one per H2
</ul>
</div>

3. BODY SECTIONS — each H2 gets id="section-N" for the TOC links to work:
<h2 id="section-1">Section Title</h2>

4. MID-ARTICLE CTA BOX — after the 2nd or 3rd H2:
<div style="background:#1a73e8;color:#ffffff;padding:28px 24px;margin:36px 0;border-radius:8px;text-align:center;">
<p style="font-size:20px;font-weight:700;margin:0 0 8px 0;">Try GoHighLevel FREE for 30 Days</p>
<p style="margin:0 0 18px 0;opacity:0.9;">Double the standard trial. No credit card required to start.</p>
<a href="AFFILIATE_URL" style="background:#ffffff;color:#1a73e8;padding:14px 28px;border-radius:6px;font-weight:700;text-decoration:none;display:inline-block;font-size:16px;">Start My Free Trial →</a>
</div>
Replace AFFILIATE_URL with the actual affiliate link above.

5. PRO TIP CALLOUT — include at least one where relevant:
<div style="background:#fff8e1;border-left:4px solid #ffc107;padding:16px 20px;margin:24px 0;border-radius:4px;">
<p style="font-weight:700;margin:0 0 6px 0;">💡 Pro Tip</p>
<p style="margin:0;">Tip content here.</p>
</div>

6. FAQ SECTION — only if Reddit questions with ? are available:
<div style="background:#f8f9fa;padding:24px;border-radius:8px;margin:36px 0;">
<h2 style="margin-top:0;">Frequently Asked Questions</h2>
... Q&A pairs using <h3> for questions, <p> for answers
</div>

7. CLOSING CTA — final paragraph + styled button:
<div style="background:#f0f4ff;border:2px solid #1a73e8;padding:24px;margin:36px 0;border-radius:8px;text-align:center;">
<p style="font-size:18px;font-weight:700;margin:0 0 8px 0;">Ready to Get Started with GoHighLevel?</p>
<p style="margin:0 0 16px 0;">Get a free 30-day trial — double the standard 14-day trial.</p>
<a href="AFFILIATE_URL" style="background:#1a73e8;color:#ffffff;padding:14px 28px;border-radius:6px;font-weight:700;text-decoration:none;display:inline-block;font-size:16px;">Claim Your Free Trial →</a>
</div>
Replace AFFILIATE_URL with the actual affiliate link above.

8. FAQ SCHEMA — if FAQ section exists, append this JSON-LD at the very end of html_content:
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{{"@type":"Question","name":"Question text?","acceptedAnswer":{{"@type":"Answer","text":"Answer text."}}}}]}}
</script>
Include one object per FAQ question.

═══════════════════════════════════════
RULES:
═══════════════════════════════════════
- 900-1300 words of actual content (not counting HTML tags)
- H2s must be clear steps or questions directly about the topic
- Do NOT include <html>, <head>, or <body> tags
- Do NOT wrap output in markdown code blocks
- Write as William Welch, GoHighLevel expert for agencies and businesses
- Tone: direct, practical, authoritative — no fluff
- Replace every instance of AFFILIATE_URL with the actual affiliate link

Return a JSON object with these exact keys:
{{
  "html_content": "the complete styled HTML including all components above",
  "meta_description": "150-160 char SEO meta description",
  "slug": "url-friendly-slug-from-title"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Extract JSON from response
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        raise ValueError("Claude did not return valid JSON")

    result = json.loads(json_match.group())
    log(f"  Blog post generated: {len(result.get('html_content',''))} chars")
    return result


# ── Main ──────────────────────────────────────────────────────────────────────
def create_blog_post(article: dict) -> dict:
    """
    Create and publish a blog post for an episode.
    article must have: seoTitle, seoDescription, seoTags
    Optional: driveTranscriptId (transcript text passed directly if available)
    Returns updated article dict with blogPostId.
    """
    title = article["seoTitle"]
    description = article["seoDescription"]
    tags = article.get("seoTags", "")
    transcript = article.get("transcript")  # passed directly if available

    # Build UTM campaign slug
    utm_campaign = re.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-"))

    log(f"Starting blog post: {title[:60]}")

    # Simplify query to core topic for better search results
    core_topic = title.split("—")[0].strip().split(" in ")[0].strip()

    # Research phase
    serp_results = scrape_duckduckgo(f"{core_topic} GoHighLevel")
    time.sleep(2)  # polite delay
    reddit_questions = scrape_reddit(f"GoHighLevel {core_topic}")

    # Generate post
    post_data = generate_blog_post(
        title=title,
        description=description,
        tags=tags,
        transcript=transcript,
        serp_results=serp_results,
        reddit_questions=reddit_questions,
        utm_campaign=utm_campaign,
    )

    # Save post to globalhighlevel-site/posts/ — scheduler git pushes → Netlify deploys
    SITE_POSTS.mkdir(parents=True, exist_ok=True)
    site_post = {
        "slug":         post_data["slug"],
        "title":        title,
        "description":  post_data["meta_description"],
        "html_content": post_data["html_content"],
        "category":     article.get("category", "GoHighLevel Tutorials"),
        "articleId":    str(article.get("id", "")),
        "publishedAt":  datetime.now().isoformat(),
    }
    post_file = SITE_POSTS / f"{post_data['slug']}.json"
    with open(post_file, "w") as f:
        json.dump(site_post, f, indent=2)
    log(f"  Published to globalhighlevel.com → site/posts/{post_data['slug']}.json")

    return {
        **article,
        "blogPostId": post_data["slug"],   # used by scheduler to count blogs published
        "blogSlug":   post_data["slug"],
        "blogPostedAt": datetime.now().isoformat(),
    }


# Allow running standalone for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python 5-blog.py <path/to/article.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        article = json.load(f)

    result = create_blog_post(article)
    print(json.dumps(result, indent=2))
