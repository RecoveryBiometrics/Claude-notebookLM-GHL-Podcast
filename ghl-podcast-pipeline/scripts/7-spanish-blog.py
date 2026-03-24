"""
7-spanish-blog.py
Generates Spanish-language GHL blog posts for Latin American and Spanish audiences.
Publishes to globalhighlevel.com via posts/ JSON (same as 5-blog.py).

Three-agent pipeline:
  1. Researcher  — DuckDuckGo (Spanish queries) + Reddit
  2. Writer      — Claude Haiku writes Spanish-native blog post
  3. Fact Checker — Claude Haiku checks regional accuracy + natural Spanish

Auto-generates topics from GSC data + Claude when running low.

Run all topics:
  venv/bin/python3 scripts/7-spanish-blog.py

Run one topic:
  venv/bin/python3 scripts/7-spanish-blog.py --topic "Cómo usar GoHighLevel para agencias en México"
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
DATA_FILE   = BASE_DIR / "data" / "spanish-published.json"
TOPICS_FILE = BASE_DIR / "data" / "spanish-topics.json"
SITE_POSTS  = Path("/opt/globalhighlevel-site/posts") if Path("/opt/globalhighlevel-site/posts").exists() else BASE_DIR.parent / "globalhighlevel-site" / "posts"
CATEGORIES_FILE = Path("/opt/globalhighlevel-site/categories.json") if Path("/opt/globalhighlevel-site/categories.json").exists() else BASE_DIR.parent / "globalhighlevel-site" / "categories.json"

ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
GHL_AFFILIATE_LINK = os.getenv("GHL_AFFILIATE_LINK", "https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12")
MODEL = "claude-haiku-4-5-20251001"

DEFAULT_TOPICS = [
    "Cómo usar GoHighLevel para agencias de marketing en México",
    "GoHighLevel vs HubSpot — Comparación de precios para Latinoamérica",
    "Automatización de WhatsApp con GoHighLevel para negocios latinos",
    "Cómo captar más clientes con embudos de GoHighLevel en español",
    "GoHighLevel para inmobiliarias en Latinoamérica — Guía completa",
    "CRM GoHighLevel en español — Todo lo que necesitas saber",
    "Cómo integrar MercadoPago con GoHighLevel para cobrar en pesos",
    "GoHighLevel para consultorios médicos en México y Colombia",
    "Automatización de seguimiento de clientes con GoHighLevel en español",
    "GoHighLevel vs Clientify — ¿Cuál es mejor para agencias hispanas?",
    "Cómo crear landing pages en español con GoHighLevel",
    "GoHighLevel para gimnasios y estudios fitness en Latinoamérica",
    "Marketing por WhatsApp para restaurantes con GoHighLevel",
    "GoHighLevel SaaS Mode — Cómo revender como agencia en Latinoamérica",
    "Guía de precios GoHighLevel 2026 en dólares y pesos mexicanos",
]

SPANISH_FACT_RULES = """
LATIN AMERICA-SPECIFIC GHL FACT CHECK RULES:

COMMUNICATION:
- WhatsApp is THE business messaging tool in all of Latin America — NOT SMS
- WhatsApp Business API is the correct GHL feature to highlight
- Email marketing also works but WhatsApp has 5-10x engagement

PAYMENTS:
- MercadoPago is the dominant payment processor (Argentina, Mexico, Brazil, Colombia)
- Stripe is available but less common in LatAm
- Also mention: Conekta (Mexico), PayU (Colombia), Transbank (Chile)
- Always mention pricing in USD AND local currency where relevant

COMPETITORS:
- Clientify is the main known Spanish-language CRM alternative
- HubSpot is known but considered expensive
- Mailchimp for email, Zoho for CRM
- Always position GHL as all-in-one vs piecing together tools

PRICING (as of 2026):
- GHL Starter: $97/month (USD)
- GHL Agency: $297/month (USD)
- Always justify ROI — $97 replaces 5-10 tools that cost $500+/month combined

MARKETS (use naturally):
- Mexico (largest Spanish-speaking market, agencies + real estate + healthcare)
- Colombia (growing digital marketing scene, agencies)
- Argentina (tech-savvy, startups, agencies)
- Spain (European market, different from LatAm but still relevant)
- Chile, Peru, Ecuador (emerging markets)

CULTURAL:
- Business relationships are personal — mention building client trust
- Many agencies are small (1-5 people) — automation is critical
- Price sensitivity is real but ROI argument works well
- Content should sound like a native Spanish speaker wrote it
- Use Latin American Spanish (not European Spanish) as default
- Avoid literal translations from English — use natural phrasing
- Use "tú" (informal) for blog posts, not "usted" (formal)
"""


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [SPANISH-BLOG] {msg}"
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
        json.dump(records, f, indent=2)


def is_published(topic: str, published: list) -> bool:
    return any(r.get("topic") == topic and r.get("slug") for r in published)


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
    subreddits = ["GoHighLevel", "marketing", "LatinAmerica", "entrepreneur"]
    questions = []
    for subreddit in subreddits:
        if len(questions) >= max_results:
            break
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{subreddit}/search.json",
                params={"q": query, "restrict_sr": 1, "sort": "top", "limit": max_results},
                headers={"User-Agent": "GHLSpanishBlogBot/1.0"},
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
    serp2 = scrape_duckduckgo(f"GoHighLevel agencia marketing latinoamérica 2026")
    time.sleep(2)
    reddit = scrape_reddit(f"GoHighLevel {topic.split()[0]}")
    return {
        "serp": serp1 + serp2,
        "reddit": reddit,
    }


# ── Agent 2: Writer ────────────────────────────────────────────────────────────
def write_blog(topic: str, research_data: dict) -> dict:
    log(f"Agent 2: Writing blog — {topic}")

    utm_campaign = re.sub(r"[^a-z0-9-]", "", topic.lower().replace(" ", "-").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n"))
    affiliate_url = (
        f"{GHL_AFFILIATE_LINK}"
        f"&utm_source=blog&utm_medium=article&utm_campaign={utm_campaign}-es"
    )
    trial_url = "https://globalhighlevel.com/trial"

    serp_context = "\n".join(
        [f"- {r['title']}: {r['snippet']}" for r in research_data["serp"]]
    ) or "No SERP data available."

    reddit_context = "\n".join(
        [f"- {q}" for q in research_data["reddit"]]
    ) or "No Reddit data available."

    prompt = f"""Eres un experto en contenido creando un blog post en ESPAÑOL para agencias de marketing digital y negocios en Latinoamérica que usan GoHighLevel.

TEMA: {topic}

INVESTIGACIÓN — CONTENIDO TOP EN ESTE TEMA:
{serp_context}

INVESTIGACIÓN — QUÉ DICEN LOS MARKETERS:
{reddit_context}

ENLACE DE AFILIADO (incluir 2-3 veces naturalmente):
{trial_url}

ENLACE DIRECTO DE AFILIADO (usar en CTAs principales):
{affiliate_url}

REQUISITOS PARA LATINOAMÉRICA:
- WhatsApp es LA herramienta de comunicación en Latinoamérica — NO SMS
- Mencionar MercadoPago como procesador de pagos principal
- Precios en USD con contexto de valor para Latinoamérica
- GHL Starter: $97/mes, Agency: $297/mes
- Mencionar mercados relevantes: México, Colombia, Argentina, España
- Escribir en español latinoamericano natural (NO traducción del inglés)
- Usar "tú" (informal), NO "usted"
- Dolor principal: demasiadas herramientas, costos altos, equipos pequeños

ESTRUCTURA DEL BLOG:
0. PRIMERA LÍNEA — antes de cualquier heading — incluir este banner CTA:
   <p style="background:#f0fdf4;border-left:4px solid #16a34a;padding:12px 16px;border-radius:4px;"><strong>🚀 Prueba GoHighLevel GRATIS por 30 días</strong> — Sin tarjeta de crédito. <a href="{trial_url}" target="_blank">Empieza tu prueba gratis aquí →</a></p>
1. Hook — hablar de un problema específico de agencias latinas
2. Agitar — hacer el problema real con contexto latinoamericano
3. Presentar GHL como la solución
4. Caso de uso real para una agencia latina (elegir un país/nicho)
5. Precios de GoHighLevel con justificación de ROI
6. Tutorial de automatización de WhatsApp
7. Sección de preguntas frecuentes (FAQ)
8. CTA fuerte con enlace de afiliado

FORMATO: HTML solo (<h2>, <h3>, <p>, <ul>, <li>, <strong>). Sin tags <html>/<head>/<body>.
LONGITUD: 900-1200 palabras
TONO: Profesional, directo, escrito por alguien que entiende negocios en Latinoamérica
IDIOMA: Español latinoamericano 100% natural

Devuelve JSON con estas claves exactas:
{{
  "html_content": "HTML completo del blog post",
  "meta_description": "150-160 caracteres de meta descripción SEO en español",
  "slug": "slug-en-espanol-amigable-url",
  "title": "Título del post en español"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="7-spanish-blog-write")

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

    prompt = f"""Eres un profesional de marketing digital latinoamericano y experto en GoHighLevel.
Tu trabajo es verificar este blog post para precisión regional y autenticidad cultural.

TEMA: {topic}

CONTENIDO DEL BLOG:
{blog_data['html_content'][:3000]}

{SPANISH_FACT_RULES}

VERIFICA:
1. ¿El español suena natural y latinoamericano? (no traducciones literales del inglés)
2. ¿Se mencionan las herramientas de pago correctas? (MercadoPago, no solo Stripe)
3. ¿WhatsApp se destaca como canal principal? (no SMS)
4. ¿Los precios están en USD con contexto de valor?
5. ¿Se menciona algún competidor de forma justa? (Clientify, HubSpot)
6. ¿El contenido es culturalmente apropiado para Latinoamérica?
7. ¿Hay errores gramaticales o de ortografía en español?

Devuelve JSON:
{{
  "approved": true/false,
  "corrections": ["lista de correcciones necesarias"],
  "revised_html": "HTML corregido si hay cambios necesarios, o vacío si está bien"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="7-spanish-blog-factcheck")

    raw = response.content[0].text.strip()
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    log(f"  Fact checker returned non-JSON — assuming approved")
    return {"approved": True, "corrections": [], "revised_html": ""}


# ── Publisher (saves to globalhighlevel-site/posts/) ──────────────────────────
def classify_post(topic: str) -> str:
    """Classify post into a category."""
    topic_lower = topic.lower()
    if any(w in topic_lower for w in ["whatsapp", "sms", "mensaje", "comunicación"]):
        return "SMS & Messaging"
    if any(w in topic_lower for w in ["pago", "mercadopago", "precio", "factura", "cobrar"]):
        return "Payments & Commerce"
    if any(w in topic_lower for w in ["ai", "ia", "inteligencia", "automatización", "bot"]):
        return "AI & Automation"
    if any(w in topic_lower for w in ["crm", "contacto", "cliente", "pipeline"]):
        return "CRM & Contacts"
    if any(w in topic_lower for w in ["email", "correo", "deliverability"]):
        return "Email & Deliverability"
    if any(w in topic_lower for w in ["embudo", "funnel", "landing", "página"]):
        return "Funnels & Websites"
    if any(w in topic_lower for w in ["agencia", "saas", "revend", "white label"]):
        return "Agency & Platform"
    return "AI & Automation"


def ensure_affiliate_links(html: str) -> str:
    """Replace bare gohighlevel.com links with trial redirect and inject CTA if missing."""
    trial_url = "https://globalhighlevel.com/trial"
    # Replace bare GHL links with trial redirect
    html = re.sub(
        r'https?://(?:www\.)?gohighlevel\.com(?!/highlevel-bootcamp)[^\s"<]*(?!fp_ref)',
        trial_url, html
    )
    # If still no affiliate link, inject CTA banner at top
    if trial_url not in html and "fp_ref" not in html:
        cta = (
            '<p style="background:#f0fdf4;border-left:4px solid #16a34a;padding:12px 16px;'
            'border-radius:4px;"><strong>🚀 Prueba GoHighLevel GRATIS por 30 días</strong>'
            f' — Sin tarjeta de crédito. <a href="{trial_url}" target="_blank">'
            'Empieza tu prueba gratis aquí →</a></p>'
        )
        html = cta + html
    return html


def save_post(topic: str, blog_data: dict, final_html: str) -> str:
    """Save post as JSON to globalhighlevel-site/posts/ for Cloudflare Pages deploy."""
    slug = blog_data.get("slug", "")
    if not slug:
        slug = re.sub(r"[^a-z0-9-]", "", topic.lower().replace(" ", "-"))

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
    # Truncate meta description if too long
    meta_desc = blog_data.get("meta_description", "")
    if len(meta_desc) > 160:
        meta_desc = meta_desc[:157] + "..."

    post_data = {
        "title": title,
        "slug": slug,
        "description": meta_desc,
        "html_content": final_html,
        "category": "GoHighLevel en Español",
        "tags": ["gohighlevel", "español", "latinoamérica", "agencia", "crm"],
        "language": "es",
        "publishedAt": datetime.now().isoformat(),
        "author": "Global High Level",
    }

    SITE_POSTS.mkdir(parents=True, exist_ok=True)
    post_path = SITE_POSTS / f"{slug}.json"
    with open(post_path, "w") as f:
        json.dump(post_data, f, indent=2, ensure_ascii=False)

    log(f"  Saved: posts/{slug}.json")
    return slug


# ── Main ───────────────────────────────────────────────────────────────────────
def process_topic(topic: str) -> dict:
    log(f"{'='*50}")
    log(f"Topic: {topic}")

    # Agent 1: Research
    research_data = research(topic)
    time.sleep(2)

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

    return {
        "topic": topic,
        "slug": slug,
        "corrections": check_result.get("corrections", []),
        "publishedAt": datetime.now().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", type=str, help="Run a single specific topic")
    parser.add_argument("--limit", type=int, default=0, help="Max topics to process (0 = all pending)")
    args = parser.parse_args()

    published = load_published()

    if args.topic:
        topics = [args.topic]
    else:
        if TOPICS_FILE.exists():
            with open(TOPICS_FILE) as f:
                topics = json.load(f)
        else:
            topics = DEFAULT_TOPICS
            with open(TOPICS_FILE, "w") as f:
                json.dump(topics, f, indent=2)
            log(f"Created spanish-topics.json with {len(topics)} topics")

    pending = [t for t in topics if not is_published(t, published)]

    # Pull GSC-generated Spanish topics
    if len(pending) < 10 and not args.topic:
        gsc_topics_file = BASE_DIR / "data" / "gsc-topics.json"
        if gsc_topics_file.exists():
            try:
                gsc_data = json.load(open(gsc_topics_file))
                gsc_spanish = gsc_data.get("spanish_topics", [])
                if gsc_spanish:
                    existing_lower = {t.lower() for t in topics}
                    added = 0
                    for t in gsc_spanish:
                        if t.lower() not in existing_lower:
                            topics.append(t)
                            added += 1
                    if added:
                        with open(TOPICS_FILE, "w") as f:
                            json.dump(topics, f, indent=2)
                        pending = [t for t in topics if not is_published(t, published)]
                        log(f"Added {added} GSC-sourced Spanish topics — now {len(pending)} pending")
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
                messages=[{"role": "user", "content": f"""Genera 15 temas de blog sobre GoHighLevel para negocios y agencias en Latinoamérica.

Estos temas ya se han cubierto — NO los repitas:
{done_list}

Requisitos:
- Cada tema debe ser específico y práctico
- Dirigido a agencias de marketing digital, freelancers y negocios locales en Latinoamérica
- Incluir ángulos específicos: WhatsApp, MercadoPago, precios en USD, comparaciones con Clientify/HubSpot
- Mezcla de: guías paso a paso, comparaciones, industrias específicas, casos de automatización
- Escritos en español latinoamericano natural
- Cada tema como título de blog post

Devuelve SOLO los 15 temas, uno por línea, sin numeración, sin viñetas."""}]
            )
            log_api_cost(msg, script="7-spanish-blog-topics")
            new_topics = [line.strip() for line in msg.content[0].text.strip().splitlines() if line.strip()]
            topics.extend(new_topics)
            with open(TOPICS_FILE, "w") as f:
                json.dump(topics, f, indent=2)
            pending = [t for t in topics if not is_published(t, published)]
            log(f"Generated {len(new_topics)} new topics — now {len(pending)} pending")
        except Exception as e:
            log(f"Topic generation failed: {e}")

    if args.limit and args.limit > 0:
        pending = pending[:args.limit]
    log(f"Topics pending: {len(pending)} / {len(topics)}")

    processed = 0
    for i, topic in enumerate(pending):
        try:
            result = process_topic(topic)
            published.append(result)
            save_published(published)
            log(f"Done: {topic[:60]}")
            processed += 1
        except Exception as e:
            log(f"FAILED: {topic[:60]} — {e}")
            published.append({
                "topic": topic,
                "status": "failed",
                "error": str(e),
                "failedAt": datetime.now().isoformat(),
            })
            save_published(published)

        if i < len(pending) - 1:
            time.sleep(5)

    log(f"Spanish blog run complete — {processed} topics processed")


if __name__ == "__main__":
    main()
