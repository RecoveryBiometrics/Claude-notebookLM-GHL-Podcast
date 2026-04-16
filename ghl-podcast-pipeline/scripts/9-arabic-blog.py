"""
9-arabic-blog.py
Generates Arabic-language GHL blog posts for MENA markets (UAE, Saudi Arabia, Egypt, Qatar, Oman).
Publishes to globalhighlevel.com via posts/ JSON (same as 5-blog.py).

Three-agent pipeline:
  1. Researcher  — DuckDuckGo (Arabic queries) + Reddit
  2. Writer      — Claude Haiku writes Arabic-native blog post
  3. Fact Checker — Claude Haiku checks regional accuracy + natural Arabic

Auto-generates topics from GSC data + Claude when running low.

Run all topics:
  venv/bin/python3 scripts/9-arabic-blog.py

Run one topic:
  venv/bin/python3 scripts/9-arabic-blog.py --topic "كيفية استخدام GoHighLevel لوكالات التسويق في الإمارات"
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

# -- Config --------------------------------------------------------------------
BASE_DIR    = Path(__file__).parent.parent
LOG_FILE    = BASE_DIR / "logs" / "pipeline.log"
DATA_FILE   = BASE_DIR / "data" / "arabic-published.json"
TOPICS_FILE = BASE_DIR / "data" / "arabic-topics.json"
SITE_POSTS  = Path("/opt/globalhighlevel-site/posts") if Path("/opt/globalhighlevel-site/posts").exists() else BASE_DIR.parent / "globalhighlevel-site" / "posts"
CATEGORIES_FILE = Path("/opt/globalhighlevel-site/categories.json") if Path("/opt/globalhighlevel-site/categories.json").exists() else BASE_DIR.parent / "globalhighlevel-site" / "categories.json"

ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
GHL_AFFILIATE_LINK = os.getenv("GHL_AFFILIATE_LINK", "")
MODEL = "claude-haiku-4-5-20251001"

DEFAULT_TOPICS = [
    "كيفية استخدام GoHighLevel لوكالات التسويق في الإمارات",
    "GoHighLevel مقابل HubSpot — مقارنة الأسعار للشرق الأوسط",
    "أتمتة واتساب مع GoHighLevel للأعمال العربية",
    "كيفية إنشاء صفحات هبوط بالعربية في GoHighLevel",
    "GoHighLevel للعقارات في دبي والسعودية",
    "CRM GoHighLevel بالعربية — دليل شامل",
    "GoHighLevel للمطاعم والمقاهي في الخليج",
    "أتمتة متابعة العملاء مع GoHighLevel بالعربية",
    "GoHighLevel SaaS Mode — كيف تبيع كوكالة في الشرق الأوسط",
    "دليل أسعار GoHighLevel 2026 بالدولار والدرهم الإماراتي",
    "GoHighLevel للعيادات الطبية في السعودية والإمارات",
    "كيفية إعداد حملات واتساب في GoHighLevel للسوق العربي",
    "GoHighLevel للتجارة الإلكترونية في الشرق الأوسط",
    "مقارنة GoHighLevel و Zoho CRM للوكالات العربية",
    "كيفية أتمتة التسويق عبر البريد الإلكتروني مع GoHighLevel بالعربية",
]

ARABIC_FACT_RULES = """
MENA-SPECIFIC GHL FACT CHECK RULES:

COMMUNICATION:
- WhatsApp is THE primary business communication tool across all MENA markets
- WhatsApp Business API is the correct GHL feature to highlight
- Email marketing works but WhatsApp has 5-10x engagement in the region
- SMS is used for OTP/verification but NOT for marketing in most MENA countries

PAYMENTS:
- Stripe is available in UAE and Saudi Arabia
- PayTabs is a major MENA payment processor (UAE, Saudi, Egypt, Oman, Qatar)
- Tap Payments is popular in GCC countries (Kuwait, Bahrain, UAE, Saudi)
- Do NOT mention MercadoPago — that is Latin America only
- Always mention pricing in USD AND local currency (AED, SAR, EGP) where relevant

COMPETITORS:
- Zoho is well-known in MENA (has Arabic support, Dubai office)
- HubSpot is known but considered expensive for the region
- Odoo has some presence in MENA
- Always position GHL as all-in-one vs piecing together tools

PRICING (as of 2026):
- GHL Starter: $97/month (USD) ~ 356 AED / 364 SAR / 4,750 EGP
- GHL Agency: $297/month (USD) ~ 1,090 AED / 1,114 SAR / 14,550 EGP
- Always justify ROI — $97 replaces 5-10 tools that cost $500+/month combined

MARKETS (use naturally):
- UAE (most tech-forward, Dubai is the business hub)
- Saudi Arabia (Vision 2030 driving massive digital transformation)
- Egypt (largest Arabic-speaking market, growing startup scene)
- Qatar (high GDP per capita, digital government initiatives)
- Oman (emerging digital economy)

CULTURAL:
- Business relationships are deeply personal — trust and rapport are essential
- Many agencies and businesses are small to medium — automation is critical
- Use Modern Standard Arabic (فصحى) — accessible across all Arabic countries
- Avoid dialect-specific terms (no Egyptian colloquial, no Gulf slang)
- Content must be culturally appropriate for conservative markets
- Friday is the weekend in most MENA countries (not Sunday)
- Ramadan and Islamic holidays affect business cycles
- Gender-neutral language is preferred in professional content
"""


# -- Logging -------------------------------------------------------------------
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [ARABIC-BLOG] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_published() -> list:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return []


def save_published(records: list):
    with open(DATA_FILE, "w") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def is_published(topic: str, published: list) -> bool:
    return any(r.get("topic") == topic and r.get("slug") for r in published)


# -- Agent 1: Researcher -------------------------------------------------------
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
    subreddits = ["GoHighLevel", "dubai", "saudiarabia", "Egypt", "marketing", "entrepreneur"]
    questions = []
    for subreddit in subreddits:
        if len(questions) >= max_results:
            break
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{subreddit}/search.json",
                params={"q": query, "restrict_sr": 1, "sort": "top", "limit": max_results},
                headers={"User-Agent": "GHLArabicBlogBot/1.0"},
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
    serp1 = scrape_duckduckgo(f"{topic}")
    time.sleep(2)
    serp2 = scrape_duckduckgo(f"GoHighLevel marketing agency Middle East MENA 2026")
    time.sleep(2)
    reddit = scrape_reddit(f"GoHighLevel {topic.split()[0]}")
    return {
        "serp": serp1 + serp2,
        "reddit": reddit,
    }


# -- Agent 2: Writer -----------------------------------------------------------
def write_blog(topic: str, research_data: dict) -> dict:
    log(f"Agent 2: Writing blog — {topic}")

    utm_campaign = re.sub(r"[^a-z0-9-]", "", "arabic-" + re.sub(r"[\u0600-\u06FF]+", "", topic).strip().lower().replace(" ", "-"))[:80]
    affiliate_url = (
        f"{GHL_AFFILIATE_LINK}"
        f"&utm_source=blog&utm_medium=article&utm_campaign={utm_campaign}"
    )
    trial_url = "https://globalhighlevel.com/ar/trial/"

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
ENGLISH SOURCE ARTICLE (from help.gohighlevel.com — ADAPT for MENA market, write in Arabic):
Title: {src.get('title', '')}
Description: {src.get('description', '')}
Content (first 3000 chars):
{src.get('content_preview', '')[:2000]}

IMPORTANT: This article is your primary source. Cover the same GoHighLevel features
but ADAPT the content for the MENA market. Don't translate literally — rewrite in
Modern Standard Arabic with local context (WhatsApp, PayTabs/Tap Payments, pricing in AED/SAR/EGP).
"""

    prompt = f"""You are an expert content creator writing a blog post in MODERN STANDARD ARABIC (فصحى) for marketing agencies and businesses in the Middle East (UAE, Saudi Arabia, Egypt, Qatar, Oman) that use GoHighLevel.

IMPORTANT: All blog content must be written in Arabic. Your instructions are in English but ALL output text (title, html_content, meta_description) must be in Arabic.

TOPIC: {topic}
{english_source}
RESEARCH — TOP CONTENT ON THIS TOPIC:
{serp_context}

RESEARCH — WHAT MARKETERS ARE SAYING:
{reddit_context}

AFFILIATE LINK (include 2-3 times naturally):
{trial_url}

DIRECT AFFILIATE LINK (use in main CTAs):
{affiliate_url}

MENA MARKET REQUIREMENTS:
- WhatsApp is THE communication tool in MENA — NOT SMS
- Payment processors: Stripe, PayTabs, Tap Payments (NOT MercadoPago)
- Prices in USD with AED/SAR/EGP equivalents
- GHL Starter: $97/month (~356 AED / 364 SAR / 4,750 EGP)
- GHL Agency: $297/month (~1,090 AED / 1,114 SAR / 14,550 EGP)
- Mention relevant markets: UAE, Saudi Arabia (Vision 2030), Egypt
- Write in Modern Standard Arabic (فصحى) — no dialect-specific terms
- Key pain point: too many tools, high costs, small teams needing automation
- Business culture: relationships and trust are paramount

BLOG STRUCTURE:
0. FIRST LINE — before any heading — include this CTA banner:
   <p style="background:#111520;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:4px;color:#eef2ff;"><strong>🚀 جرّب GoHighLevel مجاناً لمدة 30 يوماً</strong> — بدون بطاقة ائتمان. <a href="{trial_url}" style="color:#f59e0b;" target="_blank">ابدأ تجربتك المجانية هنا ←</a></p>
1. Hook — address a specific problem for MENA agencies/businesses
2. Agitate — make the problem real with Middle East business context
3. Present GHL as the solution
4. Real use case for a MENA business (pick a country/niche)
5. GoHighLevel pricing with ROI justification in local currencies
6. WhatsApp automation tutorial section
7. FAQ section (frequently asked questions)
8. Strong CTA with affiliate link

FORMAT: HTML only (<h2>, <h3>, <p>, <ul>, <li>, <strong>). No <html>/<head>/<body> tags.
RTL: Wrap the ENTIRE html_content in <div dir="rtl" style="text-align:right"> ... </div>
LENGTH: 900-1200 words
TONE: Professional, direct, written by someone who understands MENA business culture
LANGUAGE: 100% Modern Standard Arabic (فصحى)

Return JSON with these exact keys:
{{
  "html_content": "Complete HTML of the blog post (wrapped in RTL div)",
  "meta_description": "150-160 character SEO meta description in Arabic",
  "slug": "url-friendly-slug-in-english",
  "title": "Post title in Arabic"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="9-arabic-blog-write")

    raw = response.content[0].text.strip()
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        raise ValueError("Writer did not return valid JSON")

    result = json.loads(json_match.group())
    log(f"  Blog written: {len(result.get('html_content', ''))} chars")
    return result


# -- Agent 3: Fact Checker -----------------------------------------------------
def fact_check(topic: str, blog_data: dict) -> dict:
    log(f"Agent 3: Fact checking — {topic}")

    prompt = f"""You are a digital marketing professional based in the Middle East and a GoHighLevel expert.
Your job is to verify this Arabic blog post for regional accuracy and cultural authenticity.

TOPIC: {topic}

BLOG CONTENT:
{blog_data['html_content'][:3000]}

{ARABIC_FACT_RULES}

VERIFY:
1. Is the Arabic natural Modern Standard Arabic (فصحى)? No dialect-specific terms?
2. Are the correct payment tools mentioned? (PayTabs, Tap Payments, Stripe — NOT MercadoPago)
3. Is WhatsApp highlighted as the primary channel? (not SMS)
4. Are prices in USD with AED/SAR/EGP equivalents?
5. Are competitors mentioned fairly? (Zoho, HubSpot)
6. Is the content culturally appropriate for MENA markets?
7. Are there grammar or spelling errors in the Arabic?
8. Is the HTML wrapped in an RTL div?
9. Is Vision 2030 context used appropriately for Saudi Arabia references?

Return JSON:
{{
  "approved": true/false,
  "corrections": ["list of needed corrections"],
  "revised_html": "corrected HTML if changes needed, or empty string if fine"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="9-arabic-blog-factcheck")

    raw = response.content[0].text.strip()
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    log(f"  Fact checker returned non-JSON — assuming approved")
    return {"approved": True, "corrections": [], "revised_html": ""}


# -- Publisher (saves to globalhighlevel-site/posts/) --------------------------
def classify_post(topic: str) -> str:
    """Classify post into a category based on topic keywords."""
    topic_lower = topic.lower()
    # Check Arabic and English keywords
    if any(w in topic_lower for w in ["واتساب", "whatsapp", "sms", "رسائل", "رسالة"]):
        return "SMS & Messaging"
    if any(w in topic_lower for w in ["دفع", "أسعار", "سعر", "تجارة", "payment", "paytabs", "stripe", "دولار", "درهم"]):
        return "Payments & Commerce"
    if any(w in topic_lower for w in ["ai", "ذكاء", "أتمتة", "automation", "بوت", "متابعة"]):
        return "AI & Automation"
    if any(w in topic_lower for w in ["crm", "عملاء", "عميل", "contacts", "pipeline"]):
        return "CRM & Contacts"
    if any(w in topic_lower for w in ["email", "بريد", "إلكتروني", "deliverability"]):
        return "Email & Deliverability"
    if any(w in topic_lower for w in ["تحليل", "analytics", "تقرير", "reporting"]):
        return "Analytics & Reporting"
    if any(w in topic_lower for w in ["هاتف", "phone", "صوت", "voice", "مكالمات"]):
        return "Phone & Voice"
    if any(w in topic_lower for w in ["وكالة", "وكالات", "saas", "agency", "white label", "صفحات هبوط", "landing"]):
        return "Agency & Platform"
    return "Agency & Platform"


def ensure_affiliate_links(html: str) -> str:
    """Replace bare gohighlevel.com links with trial redirect and inject CTA if missing."""
    trial_url = "https://globalhighlevel.com/ar/trial/"
    # Replace bare GHL links with trial redirect
    html = re.sub(
        r'https?://(?:www\.)?gohighlevel\.com(?!/highlevel-bootcamp)[^\s"<]*(?!fp_ref)',
        trial_url, html
    )
    # If still no affiliate link, inject CTA banner at top
    if trial_url not in html and "fp_ref" not in html:
        cta = (
            '<p style="background:#111520;border-left:4px solid #f59e0b;padding:12px 16px;'
            'border-radius:4px;color:#eef2ff;"><strong>🚀 جرّب GoHighLevel مجاناً لمدة 30 يوماً</strong>'
            f' — بدون بطاقة ائتمان. <a href="{trial_url}" style="color:#f59e0b;" target="_blank">'
            'ابدأ تجربتك المجانية هنا ←</a></p>'
        )
        html = cta + html
    return html


def ensure_rtl_wrapper(html: str) -> str:
    """Ensure the HTML content is wrapped in an RTL div."""
    if 'dir="rtl"' not in html:
        html = f'<div dir="rtl" style="text-align:right">{html}</div>'
    return html


def save_post(topic: str, blog_data: dict, final_html: str) -> str:
    """Save post as JSON to globalhighlevel-site/posts/ for Cloudflare Pages deploy."""
    slug = blog_data.get("slug", "")
    if not slug:
        # Generate slug from English transliteration of topic
        slug = re.sub(r"[^a-z0-9-]", "", "arabic-ghl-" + str(int(time.time()))[-6:])

    # Ensure unique slug
    existing = {f.stem for f in SITE_POSTS.glob("*.json")}
    base_slug = slug
    counter = 1
    while slug in existing:
        slug = f"{base_slug}-{counter}"
        counter += 1

    title = blog_data.get("title", topic)
    # Force affiliate links into the HTML
    final_html = ensure_affiliate_links(final_html)
    # Ensure RTL wrapper
    final_html = ensure_rtl_wrapper(final_html)
    # Truncate meta description if too long
    meta_desc = blog_data.get("meta_description", "")
    if len(meta_desc) > 160:
        meta_desc = meta_desc[:157] + "..."

    from lang_check import classify_post_language
    try:
        from ops_log import ops_log as _warn
    except ImportError:
        _warn = None
    actual_lang = classify_post_language(final_html, expected="ar",
                                         source="9-arabic-blog", warn_fn=_warn)

    post_data = {
        "title": title,
        "slug": slug,
        "description": meta_desc,
        "html_content": final_html,
        "category": classify_post(topic),
        "tags": ["gohighlevel", "عربي", "الشرق الأوسط", "وكالة", "crm"],
        "language": actual_lang,
        "publishedAt": datetime.now().isoformat(),
        "author": "Global High Level",
    }

    SITE_POSTS.mkdir(parents=True, exist_ok=True)
    post_path = SITE_POSTS / f"{slug}.json"
    with open(post_path, "w") as f:
        json.dump(post_data, f, indent=2, ensure_ascii=False)

    log(f"  Saved: posts/{slug}.json")
    return slug


# -- Main ----------------------------------------------------------------------
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

    # Save to globalhighlevel-site/posts/
    slug = save_post(topic, blog_data, final_html)

    result = {
        "topic": topic,
        "slug": slug,
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
            sourced_topics = get_topics(language="ar", published=published, limit=args.limit or 5)
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
                json.dump(topics, f, indent=2, ensure_ascii=False)
            log(f"Created arabic-topics.json with {len(topics)} topics")

    pending = [t for t in topics if not is_published(t, published)]

    # Pull GSC-generated Arabic topics
    if len(pending) < 10 and not args.topic:
        gsc_topics_file = BASE_DIR / "data" / "gsc-topics.json"
        if gsc_topics_file.exists():
            try:
                gsc_data = json.load(open(gsc_topics_file))
                gsc_arabic = gsc_data.get("arabic_topics", [])
                if gsc_arabic:
                    existing_lower = {t.lower() for t in topics}
                    added = 0
                    for t in gsc_arabic:
                        if t.lower() not in existing_lower:
                            topics.append(t)
                            added += 1
                    if added:
                        with open(TOPICS_FILE, "w") as f:
                            json.dump(topics, f, indent=2, ensure_ascii=False)
                        pending = [t for t in topics if not is_published(t, published)]
                        log(f"Added {added} GSC-sourced Arabic topics — now {len(pending)} pending")
            except Exception:
                pass

    # Auto-generate topics if still running low
    if len(pending) < 10 and not args.topic:
        log(f"Only {len(pending)} topics left — generating 15 more...")
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            already_done = [t for t in topics if is_published(t, published)]
            done_list = "\n".join(f"- {t}" for t in already_done[-20:])
            msg = client.messages.create(
                model=MODEL,
                max_tokens=1500,
                messages=[{"role": "user", "content": f"""Generate 15 blog topics about GoHighLevel for businesses and marketing agencies in the Middle East (MENA region).

These topics have already been covered — do NOT repeat them:
{done_list}

Requirements:
- Each topic must be specific and practical
- Target marketing agencies, freelancers, and local businesses in UAE, Saudi Arabia, Egypt, Qatar, Oman
- Include specific angles: WhatsApp automation, PayTabs/Tap Payments, pricing in AED/SAR/EGP, comparisons with Zoho/HubSpot
- Mix of: step-by-step guides, comparisons, industry-specific use cases, automation workflows
- Written in Modern Standard Arabic (فصحى)
- Each topic as a blog post title

Return ONLY the 15 topics, one per line, no numbering, no bullets. All in Arabic."""}]
            )
            log_api_cost(msg, script="9-arabic-blog-topics")
            new_topics = [line.strip() for line in msg.content[0].text.strip().splitlines() if line.strip()]
            topics.extend(new_topics)
            with open(TOPICS_FILE, "w") as f:
                json.dump(topics, f, indent=2, ensure_ascii=False)
            pending = [t for t in topics if not is_published(t, published)]
            log(f"Generated {len(new_topics)} new topics — now {len(pending)} pending")
        except Exception as e:
            log(f"Topic generation failed: {e}")

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

    log(f"Arabic blog run complete — {processed} topics processed")


if __name__ == "__main__":
    main()
