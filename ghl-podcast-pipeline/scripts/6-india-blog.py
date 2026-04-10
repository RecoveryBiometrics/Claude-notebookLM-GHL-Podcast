"""
6-india-blog.py
Generates and publishes India-specific GHL blog posts to reiamplifi.com.

Three-agent pipeline:
  1. Researcher  — DuckDuckGo + Reddit (India-specific queries)
  2. Writer      — Claude Haiku writes India-native blog post
  3. Fact Checker — Claude Haiku checks GHL regional accuracy + cultural authenticity

Run all topics:
  venv/bin/python3 scripts/6-india-blog.py

Run one topic:
  venv/bin/python3 scripts/6-india-blog.py --topic "GoHighLevel WhatsApp Integration Complete India Guide"
"""

import argparse
import json
import os
import re
import time
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic
try:
    from cost_logger import log_api_cost
except ImportError:
    def log_api_cost(*a, **kw): return {}
from bs4 import BeautifulSoup

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
LOG_FILE    = BASE_DIR / "logs" / "pipeline.log"
DATA_FILE   = BASE_DIR / "data" / "india-published.json"
TOPICS_FILE = BASE_DIR / "data" / "india-topics.json"

ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
GHL_AFFILIATE_LINK = os.getenv("GHL_AFFILIATE_LINK")

SITE_POSTS = BASE_DIR.parent / "globalhighlevel-site" / "posts"

# ── Phase 1-3 Topic Queue ──────────────────────────────────────────────────────
DEFAULT_TOPICS = [
    # Phase 1 — Foundation
    "GoHighLevel vs Zoho CRM for Indian Agencies",
    "GoHighLevel Pricing in India Rupees Breakdown 2026",
    "How Indian Agencies Are Replacing 10 Tools With GoHighLevel",
    "GoHighLevel WhatsApp Integration Complete India Guide",
    # Phase 2 — Problem/Solution
    "How to Scale Your Indian Agency Without Hiring More Staff",
    "Best CRM for Digital Marketing Agencies in India 2026",
    "How to Automate Client Follow-Ups in India Using GoHighLevel",
    "GoHighLevel for Real Estate Agencies in India",
    "GoHighLevel for Healthcare Marketing India",
    "How Indian Agencies Win More Clients Using GoHighLevel Funnels",
]

# ── India Fact-Check Rules ─────────────────────────────────────────────────────
INDIA_FACT_RULES = """
INDIA-SPECIFIC GHL FACT CHECK RULES:

COMMUNICATION:
- India uses WhatsApp, NOT SMS for business communication
- WhatsApp Business API is the correct GHL feature to highlight
- Cold outreach = WhatsApp first, then call — never SMS blast

PAYMENTS:
- Indians use Razorpay, PayU, or UPI — NOT Stripe primarily
- Always mention UPI as a payment option
- Pricing must be in ₹ rupees (not just dollars)

COMPETITORS:
- Zoho CRM and Freshworks are the main known alternatives (both Indian companies)
- HubSpot/Salesforce are known but considered expensive/foreign
- Always position GHL against Zoho specifically

PRICING (as of 2026):
- GHL Starter: $97/month (~₹8,000/month)
- GHL Agency: $297/month (~₹24,700/month)
- Always justify ROI in rupees

COMPLIANCE:
- Mention GST compliance for invoicing where relevant
- Reference DPDP Act (India's data protection law) where relevant

CITIES (use naturally, not forced):
- Mumbai (finance, media, real estate)
- Bangalore (tech startups, IT agencies)
- Delhi/NCR (enterprise, government)
- Hyderabad (pharma, tech)
- Pune (IT, manufacturing)
- Chennai (manufacturing, IT)

CULTURAL:
- Business relationships are trust-based — mention building client trust
- Indian agencies often run lean with small teams — automation angle is key
- Price sensitivity is real — always show rupee ROI
- Content should sound like an Indian professional wrote it, not an American
- Avoid American idioms and phrases
"""


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [INDIA-BLOG] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Published tracker ──────────────────────────────────────────────────────────
def load_published() -> list:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return []


def save_published(records: list):
    with open(DATA_FILE, "w") as f:
        json.dump(records, f, indent=2)


def is_published(topic: str, published: list) -> bool:
    return any(r.get("topic") == topic and r.get("blogPostId") for r in published)


# ── Agent 1: Researcher ────────────────────────────────────────────────────────
def scrape_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"},
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for result in soup.select(".result__body")[:max_results + 3]:
            if result.select_one(".badge--ad"):
                continue
            title_el = result.select_one(".result__title")
            snippet_el = result.select_one(".result__snippet")
            if title_el and snippet_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True),
                })
            if len(results) >= max_results:
                break
        log(f"  SERP ({query[:50]}): {len(results)} results")
        return results
    except Exception as e:
        log(f"  DuckDuckGo failed: {e}")
        return []


def scrape_reddit(query: str, max_results: int = 5) -> list[str]:
    subreddits = ["IndiaMarketing", "india", "GoHighLevel", "digitalnomad"]
    questions = []
    for subreddit in subreddits:
        if len(questions) >= max_results:
            break
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{subreddit}/search.json",
                params={"q": query, "restrict_sr": 1, "sort": "top", "limit": max_results},
                headers={"User-Agent": "GHLIndiaBlogBot/1.0"},
                timeout=15,
            )
            posts = resp.json().get("data", {}).get("children", [])
            for post in posts:
                title = post.get("data", {}).get("title", "")
                if title and title not in questions:
                    questions.append(title)
        except Exception:
            pass
    log(f"  Reddit ({query[:50]}): {len(questions)} posts")
    return questions[:max_results]


def research(topic: str) -> dict:
    log(f"Agent 1: Researching — {topic}")
    serp1 = scrape_duckduckgo(f"{topic} India")
    time.sleep(2)
    serp2 = scrape_duckduckgo(f"GoHighLevel India agency 2026")
    time.sleep(2)
    reddit = scrape_reddit(f"GoHighLevel India {topic.split()[0]}")
    return {
        "serp": serp1 + serp2,
        "reddit": reddit,
    }


# ── Agent 2: Writer ────────────────────────────────────────────────────────────
def write_blog(topic: str, research_data: dict) -> dict:
    log(f"Agent 2: Writing blog — {topic}")

    utm_campaign = re.sub(r"[^a-z0-9-]", "", topic.lower().replace(" ", "-"))
    affiliate_url = (
        f"{GHL_AFFILIATE_LINK}"
        f"&utm_source=blog&utm_medium=article&utm_campaign={utm_campaign}-india&utm_country=IN"
    )

    serp_context = "\n".join(
        [f"- {r['title']}: {r['snippet']}" for r in research_data["serp"]]
    ) or "No SERP data available."

    reddit_context = "\n".join(
        [f"- {q}" for q in research_data["reddit"]]
    ) or "No Reddit data available."

    # Tier 1: Include English source material if available
    english_source = ""
    if research_data.get("english_source"):
        src = research_data["english_source"]
        english_source = f"""
ENGLISH SOURCE ARTICLE (from help.gohighlevel.com — ADAPT for Indian market):
Title: {src.get('title', '')}
Description: {src.get('description', '')}
Content (first 3000 chars):
{src.get('content_preview', '')[:2000]}

IMPORTANT: This article is your primary source. Cover the same GoHighLevel features
but ADAPT the content for the Indian market. Don't just copy — rewrite with
local context (WhatsApp, Razorpay/UPI, pricing in rupees with ROI justification).
"""

    prompt = f"""You are an expert content writer creating a blog post specifically for Indian digital marketing agencies and business owners considering GoHighLevel.

TOPIC: {topic}
{english_source}
RESEARCH — TOP RANKING CONTENT ON THIS TOPIC:
{serp_context}

RESEARCH — WHAT INDIAN MARKETERS ARE SAYING:
{reddit_context}

AFFILIATE LINK (include 2-3 times naturally):
{affiliate_url}

INDIA-SPECIFIC REQUIREMENTS:
- WhatsApp automation (NOT SMS) is the primary communication tool in India
- Reference Zoho CRM as the main competitor Indians know
- All pricing in ₹ rupees AND $ dollars (e.g. $97/month — approximately ₹8,000/month)
- GHL Starter plan: $97/month (~₹8,000/month), Agency plan: $297/month (~₹24,700/month)
- Reference relevant Indian cities naturally (Mumbai, Bangalore, Delhi, Hyderabad, Pune)
- Mention GST compliance where relevant
- Use Razorpay/PayU/UPI when discussing payments — not Stripe
- Write as an Indian business professional, not an American
- Pain points: talent shortage, managing too many tools, scaling lean teams

BLOG STRUCTURE:
0. FIRST LINE of the post — before any heading — include this CTA banner:
   <p style="background:#111520;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:4px;color:#eef2ff;"><strong>🚀 Try GoHighLevel FREE for 30 days</strong> — No credit card required. <a href="{affiliate_url}" style="color:#f59e0b;" target="_blank">Start your free trial here →</a></p>
1. Hook — speak to a specific Indian agency pain point
2. Agitate — make the problem feel real with Indian context
3. Introduce GHL as the solution
4. Show a real use case for an Indian agency (pick a specific city/niche)
5. GoHighLevel pricing in ₹ rupees with ROI justification
6. WhatsApp automation walkthrough (India-specific)
7. FAQ section (use Reddit questions that contain ?)
8. Strong CTA with affiliate link

FORMAT: HTML only (<h2>, <h3>, <p>, <ul>, <li>, <strong>). No <html>/<head>/<body> tags.
LENGTH: 900-1200 words
TONE: Professional, direct, written by someone who understands Indian business culture

Return JSON with these exact keys:
{{
  "html_content": "full blog post HTML",
  "meta_description": "150-160 char SEO meta description",
  "slug": "url-friendly-slug-india"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="6-india-blog-write")

    raw = response.content[0].text.strip()
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        raise ValueError("Writer did not return valid JSON")

    result = json.loads(json_match.group())
    log(f"  Blog written: {len(result.get('html_content', ''))} chars")
    return result


# ── Agent 3: Fact Checker ──────────────────────────────────────────────────────
def fact_check(topic: str, blog_data: dict) -> dict:
    log(f"Agent 3: Fact checking — {topic}")

    prompt = f"""You are an Indian digital marketing professional and GoHighLevel expert.
Your job is to fact-check this blog post for regional accuracy and cultural authenticity.

{INDIA_FACT_RULES}

BLOG POST TO REVIEW:
{blog_data['html_content']}

Check for:
1. Any mention of SMS instead of WhatsApp
2. Any mention of Stripe instead of Razorpay/PayU/UPI
3. Missing rupee pricing or incorrect rupee amounts
4. American idioms or phrases that sound foreign
5. Incorrect GHL pricing (Starter=$97, Agency=$297)
6. Any factually wrong claims about GHL features in India
7. Does it sound like it was written by an Indian professional?

Return JSON:
{{
  "approved": true or false,
  "corrections": ["list of specific corrections needed"] or [],
  "revised_html": "corrected HTML if changes needed, or empty string if approved as-is"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="6-india-blog-factcheck")

    raw = response.content[0].text.strip()
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        log("  Fact checker returned invalid JSON — using original")
        return {"approved": True, "corrections": [], "revised_html": ""}

    result = json.loads(json_match.group())

    if result.get("corrections"):
        log(f"  Corrections needed: {len(result['corrections'])}")
        for c in result["corrections"]:
            log(f"    - {c}")
        if result.get("revised_html"):
            log("  Revised HTML provided — using corrected version")
        else:
            log("  No revised HTML — publishing with writer's version")
    else:
        log("  Fact check passed — no corrections needed")

    return result


# ── Publisher (saves to globalhighlevel-site/posts/) ──────────────────────────
def make_unique_slug(slug: str) -> str:
    base = slug
    counter = 1
    while (SITE_POSTS / f"{slug}.json").exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def ensure_affiliate_links(html: str) -> str:
    """Replace bare gohighlevel.com links with trial redirect and inject CTA if missing."""
    trial_url = "https://globalhighlevel.com/trial"
    html = re.sub(
        r'https?://(?:www\.)?gohighlevel\.com(?!/highlevel-bootcamp)[^\s"<]*(?!fp_ref)',
        trial_url, html
    )
    if trial_url not in html and "fp_ref" not in html:
        cta = (
            '<p style="background:#111520;border-left:4px solid #f59e0b;padding:12px 16px;'
            'border-radius:4px;color:#eef2ff;"><strong>🚀 Try GoHighLevel FREE for 30 days</strong>'
            f' — No credit card required. <a href="{trial_url}" style="color:#f59e0b;" target="_blank">'
            'Start your free trial here →</a></p>'
        )
        html = cta + html
    return html


def publish(topic: str, html_content: str, meta_description: str, slug: str) -> str:
    log(f"Publishing: {topic[:60]}")
    SITE_POSTS.mkdir(parents=True, exist_ok=True)
    unique_slug = make_unique_slug(slug)

    # Force affiliate links
    html_content = ensure_affiliate_links(html_content)
    # Truncate meta description if too long
    if len(meta_description) > 160:
        meta_description = meta_description[:157] + "..."

    # Classify into real topic category
    topic_lower = topic.lower()
    if any(w in topic_lower for w in ["whatsapp", "sms", "message"]):
        category = "SMS & Messaging"
    elif any(w in topic_lower for w in ["payment", "razorpay", "upi", "pricing", "price", "cost"]):
        category = "Payments & Commerce"
    elif any(w in topic_lower for w in ["automation", "workflow", "ai", "bot"]):
        category = "AI & Automation"
    elif any(w in topic_lower for w in ["crm", "contact", "pipeline", "lead", "client"]):
        category = "CRM & Contacts"
    elif any(w in topic_lower for w in ["email", "deliverability"]):
        category = "Email & Deliverability"
    elif any(w in topic_lower for w in ["analytics", "report", "tracking"]):
        category = "Analytics & Reporting"
    else:
        category = "Agency & Platform"

    site_post = {
        "slug":         unique_slug,
        "title":        topic,
        "description":  meta_description,
        "html_content": html_content,
        "category":     category,
        "language":     "en-IN",
        "publishedAt":  datetime.now().isoformat(),
    }
    post_file = SITE_POSTS / f"{unique_slug}.json"
    with open(post_file, "w") as f:
        json.dump(site_post, f, indent=2)

    log(f"  Published to globalhighlevel.com → posts/{unique_slug}.json")
    return unique_slug


# ── Main ───────────────────────────────────────────────────────────────────────
def process_topic(topic: str, source_data: dict = None) -> dict:
    """Process a topic. source_data contains Tier 1 English source material if available."""
    log(f"{'='*50}")
    source = source_data.get("source", "tier3-market") if source_data else "tier3-market"
    log(f"Topic: {topic} [source: {source}]")

    # Agent 1: Research
    research_data = research(topic)
    time.sleep(2)

    # For Tier 1 topics, inject the English source material into research
    if source_data and source_data.get("english_content_preview"):
        research_data["english_source"] = {
            "title": source_data.get("english_title", ""),
            "description": source_data.get("english_description", ""),
            "content_preview": source_data.get("english_content_preview", ""),
        }

    # Agent 2: Write (retry once on JSON failure)
    blog_data = None
    for attempt in range(2):
        try:
            blog_data = write_blog(topic, research_data)
            break
        except (ValueError, json.JSONDecodeError) as e:
            log(f"  Writer attempt {attempt + 1} failed: {e} — {'retrying...' if attempt == 0 else 'giving up'}")
            time.sleep(5)
    if not blog_data:
        raise ValueError("Writer failed after 2 attempts")
    time.sleep(2)

    # Agent 3: Fact check
    check_result = fact_check(topic, blog_data)

    # Use revised HTML if corrections were made
    final_html = check_result.get("revised_html") or blog_data["html_content"]
    if not final_html.strip():
        final_html = blog_data["html_content"]

    # Publish
    post_id = publish(
        topic=topic,
        html_content=final_html,
        meta_description=blog_data["meta_description"],
        slug=blog_data["slug"],
    )

    result = {
        "topic": topic,
        "blogPostId": post_id,
        "blogSlug": blog_data["slug"],
        "source": source,
        "corrections": check_result.get("corrections", []),
        "publishedAt": datetime.now().isoformat(),
    }
    if source_data and source_data.get("articleId"):
        result["articleId"] = source_data["articleId"]

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", type=str, help="Run a single specific topic")
    parser.add_argument("--limit", type=int, default=0, help="Max topics to process (0 = all pending)")
    args = parser.parse_args()

    published = load_published()

    if args.topic:
        topics = [args.topic]
        sourced_topics = []
    else:
        # Tier 1 + 2: Get properly sourced topics from the topic sourcer
        try:
            from topic_sourcer import get_topics
            sourced_topics = get_topics(language="en-IN", published=published, limit=args.limit or 5)
            log(f"Topic sourcer: {len(sourced_topics)} topics ({sum(1 for t in sourced_topics if t['tier']==1)} docs, {sum(1 for t in sourced_topics if t['tier']==2)} GSC)")
        except Exception as e:
            log(f"Topic sourcer unavailable ({e}) — falling back to topic list")
            sourced_topics = []

        # Tier 3 fallback: existing topic list + auto-generation
        if TOPICS_FILE.exists():
            with open(TOPICS_FILE) as f:
                topics = json.load(f)
        else:
            topics = DEFAULT_TOPICS
            with open(TOPICS_FILE, "w") as f:
                json.dump(topics, f, indent=2)
            log(f"Created india-topics.json with {len(topics)} topics")

    pending = [t for t in topics if not is_published(t, published)]

    # Pull GSC-generated India topics
    if len(pending) < 10 and not args.topic:
        gsc_topics_file = BASE_DIR / "data" / "gsc-topics.json"
        if gsc_topics_file.exists():
            try:
                gsc_data = json.load(open(gsc_topics_file))
                gsc_india = gsc_data.get("india_topics", [])
                if gsc_india:
                    existing_lower = {t.lower() for t in topics}
                    added = 0
                    for t in gsc_india:
                        if t.lower() not in existing_lower:
                            topics.append(t)
                            added += 1
                    if added:
                        with open(TOPICS_FILE, "w") as f:
                            json.dump(topics, f, indent=2)
                        pending = [t for t in topics if not is_published(t, published)]
                        log(f"Added {added} GSC-sourced India topics — now {len(pending)} pending")
            except Exception:
                pass

    # Auto-generate topics if still running low
    if len(pending) < 10 and not args.topic:
        log(f"Only {len(pending)} topics left — generating 25 more...")
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            already_done = [t for t in topics if is_published(t, published)]
            done_list = "\n".join(f"- {t}" for t in already_done[-30:])
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": f"""Generate 25 blog post topics about GoHighLevel for Indian businesses and agencies.

These topics have already been covered — do NOT repeat them:
{done_list}

Requirements:
- Each topic must be specific and actionable (not generic)
- Target Indian digital marketing agencies, freelancers, and local businesses
- Include India-specific angles: WhatsApp, Razorpay/UPI, rupee pricing, Zoho comparisons, Indian cities/industries
- Mix of: how-to guides, comparisons, industry-specific (real estate, healthcare, education, etc.), and automation use cases
- Each topic should be a single line, suitable as a blog post title

Return ONLY the 25 topics, one per line, no numbering, no bullets, no other text."""}]
            )
            log_api_cost(msg, script="6-india-blog-topics")
            new_topics = [line.strip() for line in msg.content[0].text.strip().splitlines() if line.strip()]
            topics.extend(new_topics)
            with open(TOPICS_FILE, "w") as f:
                json.dump(topics, f, indent=2)
            pending = [t for t in topics if not is_published(t, published)]
            log(f"Generated {len(new_topics)} new topics — now {len(pending)} pending")
        except Exception as e:
            log(f"Topic generation failed (continuing with existing): {e}")

    # Build the final processing queue: sourced topics first, then Tier 3 (pending)
    max_total = args.limit if args.limit and args.limit > 0 else 5
    process_queue = []

    # Add sourced topics (Tier 1 + 2)
    for st in sourced_topics:
        if len(process_queue) >= max_total:
            break
        process_queue.append({"topic": st["topic"], "source_data": st})

    # Fill remaining with Tier 3 (existing topic list)
    if len(process_queue) < max_total:
        remaining = max_total - len(process_queue)
        tier3_pending = [t for t in pending[:remaining]]
        for t in tier3_pending:
            process_queue.append({"topic": t, "source_data": {"source": "tier3-market"}})

    log(f"Processing {len(process_queue)} topics: {sum(1 for q in process_queue if q['source_data'].get('tier')==1)} docs + {sum(1 for q in process_queue if q['source_data'].get('tier')==2)} GSC + {sum(1 for q in process_queue if q['source_data'].get('source')=='tier3-market')} market")

    processed = 0
    for i, item in enumerate(process_queue):
        topic = item["topic"]
        source_data = item.get("source_data")
        try:
            result = process_topic(topic, source_data=source_data)
            published.append(result)
            save_published(published)
            log(f"Done: {topic[:60]}")
            processed += 1
        except Exception as e:
            log(f"FAILED: {topic[:60]} — {e}")
            published.append({
                "topic": topic,
                "source": source_data.get("source", "tier3-market") if source_data else "tier3-market",
                "status": "failed",
                "error": str(e),
                "failedAt": datetime.now().isoformat(),
            })
            save_published(published)

        if i < len(process_queue) - 1:
            time.sleep(5)

    log(f"India blog run complete — {processed} topics processed")


if __name__ == "__main__":
    main()
