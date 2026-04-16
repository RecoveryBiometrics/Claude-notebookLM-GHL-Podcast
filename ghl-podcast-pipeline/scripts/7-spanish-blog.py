"""
7-spanish-blog.py
Generates Spanish-language GHL blog posts for Latin American and Spanish audiences.
Publishes to globalhighlevel.com via posts/ JSON (same as 5-blog.py).

Three-agent pipeline:
  1. Researcher  . DuckDuckGo (Spanish queries) + Reddit
  2. Writer      . Claude Haiku writes Spanish-native blog post
  3. Fact Checker . Claude Haiku checks regional accuracy + natural Spanish

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
GHL_AFFILIATE_LINK = os.getenv("GHL_AFFILIATE_LINK", "")
MODEL = "claude-haiku-4-5-20251001"
MODEL_ATTIA = "claude-haiku-4-5-20251001"  # reverted from Sonnet — Sonnet returned malformed JSON twice.
# Haiku produces ~500-word clean first-pass which matches our relaxed target. If we later need
# 2500+ words reliably, fix prompt structure first, then consider Sonnet with structured-output API.

DEFAULT_TOPICS = [
    "Cómo usar GoHighLevel para agencias de marketing en México",
    "GoHighLevel vs HubSpot . Comparación de precios para Latinoamérica",
    "Automatización de WhatsApp con GoHighLevel para negocios latinos",
    "Cómo captar más clientes con embudos de GoHighLevel en español",
    "GoHighLevel para inmobiliarias en Latinoamérica . Guía completa",
    "CRM GoHighLevel en español . Todo lo que necesitas saber",
    "Cómo integrar MercadoPago con GoHighLevel para cobrar en pesos",
    "GoHighLevel para consultorios médicos en México y Colombia",
    "Automatización de seguimiento de clientes con GoHighLevel en español",
    "GoHighLevel vs Clientify . ¿Cuál es mejor para agencias hispanas?",
    "Cómo crear landing pages en español con GoHighLevel",
    "GoHighLevel para gimnasios y estudios fitness en Latinoamérica",
    "Marketing por WhatsApp para restaurantes con GoHighLevel",
    "GoHighLevel SaaS Mode . Cómo revender como agencia en Latinoamérica",
    "Guía de precios GoHighLevel 2026 en dólares y pesos mexicanos",
]

SPANISH_FACT_RULES = """
RULE #0 . NEVER FABRICATE (HARD FAIL, BLOCKS SHIP):
- NO invented people (no "Matías manejaba una agencia", no "María en Medellín", no named person)
- NO invented companies or client names
- NO invented dollar figures, revenue numbers, client counts, or ROI percentages
- NO invented case studies, testimonials, or first-person anecdotes
- NO "trusted by X agencies", "used by X businesses", or any social-proof count
- ALLOWED: public data with a cited source (GHL pricing page, Clientify public pricing, competitor published docs)
- ALLOWED: clearly-marked hypothetical examples ("Imagina una agencia de 3 personas en Guadalajara . ejemplo hipotético, no un cliente real")
- If a number appears without a source footnote, REWRITE the sentence to remove the number.
- If a named person or business appears without written approval, STRIP the name.

LATIN AMERICA-SPECIFIC GHL FACT CHECK RULES:

COMMUNICATION:
- WhatsApp is THE business messaging tool in all of Latin America . NOT SMS
- WhatsApp Business API is the correct GHL feature to highlight
- Email marketing also works but WhatsApp typically shows higher engagement for service/agency messaging (use qualitative language only. do NOT cite a specific multiplier like "5-10x" without a primary source)

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
- Always justify ROI . $97 replaces 5-10 tools that cost $500+/month combined

MARKETS (use naturally):
- Mexico (largest Spanish-speaking market, agencies + real estate + healthcare)
- Colombia (growing digital marketing scene, agencies)
- Argentina (tech-savvy, startups, agencies)
- Spain (European market, different from LatAm but still relevant)
- Chile, Peru, Ecuador (emerging markets)

CULTURAL:
- Business relationships are personal . mention building client trust
- Many agencies are small (1-5 people) . automation is critical
- Price sensitivity is real but ROI argument works well
- Content should sound like a native Spanish speaker wrote it
- Use Latin American Spanish (not European Spanish) as default
- Avoid literal translations from English . use natural phrasing
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
    log(f"Agent 1: Researching . {topic}")
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
def write_blog(topic: str, research_data: dict, mode: str = "standard",
               vertical: str = "", part: int = 0, series_hub: str = "",
               hub_title: str = "") -> dict:
    if mode == "attia-longform":
        return write_blog_attia(topic, research_data, vertical, part, series_hub, hub_title)
    log(f"Agent 2: Writing blog . {topic}")

    utm_campaign = re.sub(r"[^a-z0-9-]", "", topic.lower().replace(" ", "-").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n"))
    affiliate_url = (
        f"{GHL_AFFILIATE_LINK}"
        f"&utm_source=blog&utm_medium=article&utm_campaign={utm_campaign}-es"
    )
    trial_url = "https://globalhighlevel.com/es/trial/"

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
ARTÍCULO FUENTE EN INGLÉS (de help.gohighlevel.com . ADAPTAR, no traducir literalmente):
Título: {src.get('title', '')}
Descripción: {src.get('description', '')}
Contenido (primeros 3000 caracteres):
{src.get('content_preview', '')[:2000]}

IMPORTANTE: Este artículo es tu fuente principal. Cubre las mismas funciones de GoHighLevel
pero ADAPTA el contenido para el mercado latinoamericano. No traduzcas . reescribe con
contexto local (WhatsApp, MercadoPago, precios en USD con contexto de valor LatAm).
"""

    prompt = f"""Eres un experto en contenido creando un blog post en ESPAÑOL para agencias de marketing digital y negocios en Latinoamérica que usan GoHighLevel.

TEMA: {topic}
{english_source}
INVESTIGACIÓN . CONTENIDO TOP EN ESTE TEMA:
{serp_context}

INVESTIGACIÓN . QUÉ DICEN LOS MARKETERS:
{reddit_context}

ENLACE DE AFILIADO (incluir 2-3 veces naturalmente):
{trial_url}

ENLACE DIRECTO DE AFILIADO (usar en CTAs principales):
{affiliate_url}

REQUISITOS PARA LATINOAMÉRICA:
- WhatsApp es LA herramienta de comunicación en Latinoamérica . NO SMS
- Mencionar MercadoPago como procesador de pagos principal
- Precios en USD con contexto de valor para Latinoamérica
- GHL Starter: $97/mes, Agency: $297/mes
- Mencionar mercados relevantes: México, Colombia, Argentina, España
- Escribir en español latinoamericano natural (NO traducción del inglés)
- Usar "tú" (informal), NO "usted"
- Dolor principal: demasiadas herramientas, costos altos, equipos pequeños

ESTRUCTURA DEL BLOG:
0. PRIMERA LÍNEA . antes de cualquier heading . incluir este banner CTA:
   <p style="background:#111520;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:4px;color:#eef2ff;"><strong>🚀 Prueba GoHighLevel GRATIS por 30 días</strong> . Sin tarjeta de crédito. <a href="{trial_url}" style="color:#f59e0b;" target="_blank">Empieza tu prueba gratis aquí →</a></p>
1. Hook . hablar de un problema específico de agencias latinas
2. Agitar . hacer el problema real con contexto latinoamericano
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


# ── Agent 2b: Writer (Attia long-form mode) ────────────────────────────────────
def write_blog_attia(topic: str, research_data: dict, vertical: str, part: int,
                     series_hub: str, hub_title: str) -> dict:
    log(f"Agent 2 [ATTIA]: Writing Part {part} . {topic}")

    utm_campaign = re.sub(r"[^a-z0-9-]", "", topic.lower().replace(" ", "-").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n"))
    affiliate_url = (
        f"{GHL_AFFILIATE_LINK}"
        f"&utm_source=blog&utm_medium=article&utm_campaign=verticals-{vertical}-part{part}-es"
    )
    trial_url = "https://globalhighlevel.com/es/trial/"
    extendly_url = "https://extendly.com/gohighlevel/?deal=vqzoli"

    serp_context = "\n".join([f"- {r['title']}: {r['snippet']}" for r in research_data["serp"]]) or "No SERP data available."
    reddit_context = "\n".join([f"- {q}" for q in research_data["reddit"]]) or "No Reddit data available."

    prompt = f"""Eres un practicante experimentado escribiendo para una agencia de marketing digital hispanohablante. Escribes como alguien que ha implementado el sistema, lo ha visto funcionar, y explica por qué funciona sin vender. Estilo Peter Attia "Straight Dope" . pedagógico, concreto, denso en información, con analogías sostenidas.

TEMA (H1 sugerido): {topic}
VERTICAL: {vertical}
PARTE DE LA SERIE: Parte {part} de 9
HUB DE LA SERIE: {series_hub} (título: "{hub_title}")

INVESTIGACIÓN . SERP:
{serp_context}

INVESTIGACIÓN . REDDIT:
{reddit_context}

ENLACE DE AFILIADO PRIMARIO (CTA principal . arriba y abajo): {trial_url}
ENLACE DE AFILIADO CON UTM: {affiliate_url}
ENLACE EXTENDLY (CTA secundario . mitad del post): {extendly_url}

═══════════════════════════════════════════════════════════════════
ESTRUCTURA OBLIGATORIA . LOS 12 ELEMENTOS DE PETER ATTIA "STRAIGHT DOPE"
═══════════════════════════════════════════════════════════════════

1. PRE-INTRO (1 párrafo, sin heading, máx 80 palabras)
   - Nombra al lector concretamente ("Si manejas una agencia de marketing de 3 a 5 personas en México o Colombia...")
   - Nombra el problema en términos concretos (no vagos)
   - Promete qué explica el post
   - NO menciones GoHighLevel aún
   - NO frases tipo "en el mundo actual", "en este post exploraremos"

2. OBJETIVOS DE APRENDIZAJE (caja destacada, numerada 1-5)
   Formato: <p style="background:#f5f5f0;border-left:4px solid #111520;padding:16px;">
   <strong>Al terminar este post entenderás:</strong></p>
   <ol><li>...</li></ol>

3. CONCEPTOS CLAVE (3-5 modelos mentales, no glosario)
   <h2>Conceptos clave</h2>
   Para cada concepto: <p><strong>Nombre del concepto.</strong> Una frase de definición. Una frase de por qué importa.</p>

4. CUERPO (H2 + H3 jerarquía, 5-8 H2, al menos 2 H3 tipo pregunta)
   - H2 como declaración directa o pregunta ("Por qué WhatsApp gana sobre email para agencias")
   - H3 como preguntas que el lector haría de forma natural
   - Sin H4 o más profundo

5. UNA ANALOGÍA SOSTENIDA (una sola por parte)
   - Introducida a mitad del post
   - Referenciada al menos 2 veces más en secciones posteriores
   - Debe aclarar la idea técnica, no solo ser linda

6. Q&A EMBEBIDO (al menos 2 H3 en formato pregunta)
   - Preguntas como las haría un dueño de agencia de verdad
   - Respuestas de 1-3 párrafos, no bullets

7. NEGRITA EN PRIMER USO DE CADA TÉRMINO TÉCNICO
   - Solo la primera vez que aparece el término
   - Solo términos técnicos reales, no palabras de marketing

8. FOOTNOTES PARA DATOS FACTUALES (2-5 por parte)
   - Todo número, porcentaje, precio, o feature claim debe tener footnote citando fuente primaria
   - Formato: frase con número.[^1] ... al final: <p><small>[^1]: Fuente, URL, fecha.</small></p>
   - Si un número no tiene fuente primaria, REESCRIBE la frase sin el número

9. CTA SECUNDARIO A MITAD DEL POST (entre H2 #3 y H2 #4)
   <p style="background:#fefbf0;border:1px solid #f59e0b;padding:16px;border-radius:4px;">
   <strong>¿Prefieres implementación hecha por expertos?</strong> Extendly maneja el onboarding de GoHighLevel, soporte white-label 24/7 en español, y snapshots pre-construidos para agencias. Los recomendamos para quien quiere el sistema funcionando sin hacer el setup. <a href="{extendly_url}" target="_blank" rel="nofollow noopener">Ver Extendly →</a></p>

10. UP-NEXT TEASER (párrafo final antes del footer CTA, 50-80 palabras)
    <h2>Próximamente en la Parte {part + 1}</h2>
    <p>Una frase sobre de qué trata la Parte {part + 1}. Una frase sobre por qué importa para quien leyó esta parte.</p>

11. CTA PRIMARIO ARRIBA (primera línea, antes de pre-intro)
    <p style="background:#111520;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:4px;color:#eef2ff;"><strong>🚀 Prueba GoHighLevel GRATIS por 30 días</strong> . Sin tarjeta de crédito. <a href="{trial_url}" style="color:#f59e0b;" target="_blank">Empieza tu prueba gratis aquí →</a></p>

12. CTA PRIMARIO ABAJO (después del up-next teaser)
    <p style="background:#111520;border-left:4px solid #f59e0b;padding:16px;border-radius:4px;color:#eef2ff;text-align:center;"><strong>Empieza tu prueba de 30 días de GoHighLevel</strong><br>Sin tarjeta de crédito. Cancela cuando quieras. <br><a href="{trial_url}" style="color:#f59e0b;font-weight:bold;" target="_blank">Empezar prueba gratis →</a></p>

═══════════════════════════════════════════════════════════════════
REGLA #0 . NUNCA FABRICAR (BLOQUEA PUBLICACIÓN)
═══════════════════════════════════════════════════════════════════
- NO personas inventadas (NO "Matías en Buenos Aires", NO "María en Medellín")
- NO empresas inventadas ni nombres de clientes
- NO cifras de dólares, ingresos, clientes, o ROI inventadas
- NO testimonios, anécdotas en primera persona, o casos de estudio inventados
- NO "confiado por X agencias" ni social proof con conteos
- PERMITIDO: datos públicos con fuente citada (precios GHL, precios Clientify, docs de competidores)
- PERMITIDO: ejemplos hipotéticos claramente marcados ("Imagina una agencia de 3 personas . ejemplo hipotético, no cliente real")

═══════════════════════════════════════════════════════════════════
LONGITUD Y TONO
═══════════════════════════════════════════════════════════════════
LONGITUD (OBLIGATORIA, NO NEGOCIABLE): 2500-3500 palabras. Bajo 2500 = FALLA, no cuenta como entregable.
Para llegar a 2500+ sin relleno: incluye 6-8 H2 completos, cada uno con 400-500 palabras de contenido real. Dentro de cada H2, 1-2 H3 como preguntas + respuestas de 150-250 palabras. Los conceptos técnicos se explican con analogías concretas y casos hipotéticos claramente marcados (sin nombres propios).

TONO: practicante experimentado hablando a dueño de agencia en un café. No académico. No marketero.
IDIOMA: español latinoamericano NEUTRO (no rioplatense/voseo). Usar "tú" + "tienes/necesitas/diriges". NUNCA "vos/tenés/necesitás". NO traducción del inglés.
SIN EM-DASHES. Usa coma, punto, o paréntesis.
SIN frases-IA prohibidas: "aprovechar", "utilizar" (usa "usar"), "sumergirnos", "en el mundo actual", "en este post exploraremos", "llevar al siguiente nivel", "desbloquear", "revolucionar", "ecosistema" (para no-biología), "landscape", "journey", "robusto", "de clase mundial", "sin fisuras", "delve", "holístico".

═══════════════════════════════════════════════════════════════════
CONTEXTO LATINOAMERICANO OBLIGATORIO
═══════════════════════════════════════════════════════════════════
- WhatsApp es EL canal de comunicación (NO SMS)
- MercadoPago, Conekta (México), PayU (Colombia), Transbank (Chile) antes que Stripe
- Precios GHL: Starter $97 USD/mes, Agency $297 USD/mes (citar como fuente primaria GHL pricing page)
- Competidores: Clientify (principal alternativa en español), HubSpot (conocido, caro)
- Mercados: México, Colombia, Argentina, España, Chile, Perú

═══════════════════════════════════════════════════════════════════
FORMATO DE SALIDA
═══════════════════════════════════════════════════════════════════
Devuelve JSON con estas claves exactas:
{{
  "html_content": "HTML completo del post con TODOS los 12 elementos arriba en orden",
  "meta_description": "150-158 caracteres con palabra clave principal en los primeros 80 chars",
  "slug": "slug-espanol-descriptivo-parte-{part}",
  "title": "H1 en español . título del post"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL_ATTIA,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="7-spanish-blog-write-attia")

    raw = response.content[0].text.strip()
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        raise ValueError("Attia writer did not return valid JSON")

    result = json.loads(json_match.group())
    log(f"  Attia blog written: {len(result.get('html_content', ''))} chars")
    return result


# ── Agent 2c: Revise with corrections (Opus reviewer feedback loop) ────────────
def revise_with_corrections(original_html: str, corrections: list, target_word_min: int = 2500) -> str:
    """
    Second-pass Haiku write. Takes the original HTML + list of reviewer corrections,
    produces v2 HTML that fixes each correction IN PLACE without shortening the post.

    corrections = list of dicts {issue, quote, fix} from language_reviewer.review()
    Returns revised html_content string.
    """
    if not corrections:
        return original_html

    correction_block = "\n".join(
        f"  - [{c.get('issue', 'other')}] Cita: «{c.get('quote', '')[:200]}»  → Arreglo: {c.get('fix', '')}"
        for c in corrections[:30]  # cap to avoid prompt overflow
    )

    prompt = f"""Eres el mismo writer que produjo este post. Un reviewer nativo latinoamericano identificó problemas específicos. Tu trabajo: aplicar CADA corrección EN SU LUGAR sin acortar el post, sin resumir, sin recompactar. El post debe quedar de la misma longitud o más largo, NO más corto.

REGLA #0. NUNCA FABRICAR (CRÍTICO DURANTE LA EXPANSIÓN):
- NO inventes personas con nombre (NO "María", NO "Carlos", NO "Matías", NO "Ana"). Si necesitas ejemplo, usa "una agencia hipotética de N personas" SIN nombres propios.
- NO inventes empresas cliente (NO "Agencia XYZ en CDMX").
- NO inventes cifras específicas: NO "pierden 5 prospectos/mes", NO "invierten 15 min buscando email", NO "3.5x más engagement", NO "reduce costos $450 a $97". Usa lenguaje cualitativo o elimina el número.
- NO inventes testimonios ni anécdotas en primera persona.
- PERMITIDO: "Imagina una agencia de 5 personas . ejemplo hipotético" (claramente marcado).
- Si el reviewer marcó una fabricación, REEMPLAZA con lenguaje cualitativo, NO con otra fabricación.

DIALECTO LATINOAMERICANO NEUTRO (evitar voseo):
- Usar "tú" con verbos: "tienes", "necesitas", "puedes", "diriges".
- NUNCA voseo argentino: NO "tenés", NO "necesitás", NO "podés", NO "dirigís".

REGLAS DURAS PARA EXPANDIR:
1. NO resumas el post. NO compactes párrafos. NO elimines secciones.
2. Cada corrección se aplica en su lugar. Encuentra la frase citada, arréglala como indica el "Arreglo", conserva el resto del párrafo.
3. Si el arreglo elimina un número fabricado, REEMPLAZA la frase con una equivalente cualitativa (no la borres).
4. El post debe tener AL MENOS {target_word_min} palabras después de tu revisión.
5. Para expandir a {target_word_min}+ palabras: agrega análisis técnico concreto, más H3 de preguntas que un dueño de agencia haría, más matices sobre compliance/stack tecnológico/equipo, más detalle en conceptos. NO agregues casos de estudio inventados. NO agregues personas con nombre. NO agregues cifras sin fuente.
6. Devuelve el HTML completo corregido, no fragmentos.

CORRECCIONES DEL REVIEWER (aplica cada una):
{correction_block}

HTML ORIGINAL:
{original_html}

Devuelve JSON:
{{
  "html_content": "HTML completo v2 con todas las correcciones aplicadas, longitud preservada o mayor"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=12000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="7-spanish-blog-revise")

    raw = response.content[0].text.strip()
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        log(f"  Reviser returned non-JSON, returning original")
        return original_html

    try:
        result = json.loads(json_match.group())
    except json.JSONDecodeError:
        log(f"  Reviser JSON decode failed, returning original")
        return original_html

    revised = result.get("html_content", "") or original_html
    orig_words = len(original_html.split())
    new_words = len(revised.split())
    log(f"  Revise: {orig_words} → {new_words} words ({new_words - orig_words:+d})")
    return revised


# ── Agent 3: Fact Checker ──────────────────────────────────────────────────────
def fact_check(topic: str, blog_data: dict) -> dict:
    log(f"Agent 3: Fact checking . {topic}")

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

    log(f"  Fact checker returned non-JSON . assuming approved")
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
        return "Agency & Platform"
    if any(w in topic_lower for w in ["agencia", "saas", "revend", "white label"]):
        return "Agency & Platform"
    return "Agency & Platform"


def ensure_affiliate_links(html: str) -> str:
    """Replace bare gohighlevel.com links with trial redirect and inject CTA if missing."""
    trial_url = "https://globalhighlevel.com/es/trial/"
    # Replace bare GHL links with trial redirect
    html = re.sub(
        r'https?://(?:www\.)?gohighlevel\.com(?!/highlevel-bootcamp)[^\s"<]*(?!fp_ref)',
        trial_url, html
    )
    # If still no affiliate link, inject CTA banner at top
    if trial_url not in html and "fp_ref" not in html:
        cta = (
            '<p style="background:#111520;border-left:4px solid #f59e0b;padding:12px 16px;'
            'border-radius:4px;color:#eef2ff;"><strong>🚀 Prueba GoHighLevel GRATIS por 30 días</strong>'
            f' . Sin tarjeta de crédito. <a href="{trial_url}" style="color:#f59e0b;" target="_blank">'
            'Empieza tu prueba gratis aquí →</a></p>'
        )
        html = cta + html
    return html


def save_post(topic: str, blog_data: dict, final_html: str,
              url_path: str = "", hub_url: str = "", hub_title: str = "",
              vertical: str = "", part: int = 0) -> str:
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

    from lang_check import classify_post_language
    try:
        from ops_log import ops_log as _warn
    except ImportError:
        _warn = None
    actual_lang = classify_post_language(final_html, expected="es",
                                         source="7-spanish-blog", warn_fn=_warn)

    post_data = {
        "title": title,
        "slug": slug,
        "description": meta_desc,
        "html_content": final_html,
        "category": classify_post(topic),
        "tags": ["gohighlevel", "español", "latinoamérica", "agencia", "crm"],
        "language": actual_lang,
        "publishedAt": datetime.now().isoformat(),
        "author": "Global High Level",
    }
    if url_path:
        post_data["url_path"] = url_path
    if hub_url:
        post_data["hub_url"] = hub_url
        post_data["hub_title"] = hub_title
    if vertical:
        post_data["vertical"] = vertical
    if part:
        post_data["series_part"] = part

    SITE_POSTS.mkdir(parents=True, exist_ok=True)
    post_path = SITE_POSTS / f"{slug}.json"
    with open(post_path, "w") as f:
        json.dump(post_data, f, indent=2, ensure_ascii=False)

    log(f"  Saved: posts/{slug}.json")
    return slug


# ── Main ───────────────────────────────────────────────────────────────────────
def process_topic(topic: str, source_data: dict = None, mode: str = "standard",
                  vertical: str = "", part: int = 0, series_hub: str = "",
                  hub_title: str = "") -> dict:
    """Process a topic. source_data contains Tier 1 English source material if available.
    When mode='attia-longform', produces 2500+ word Attia-structured pillar at /es/para/[vertical]/."""
    log(f"{'='*50}")
    source = source_data.get("source", "tier3-market") if source_data else "tier3-market"
    if mode == "attia-longform":
        source = f"verticals-{vertical}-part{part}"
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
            blog_data = write_blog(topic, research_data, mode=mode, vertical=vertical,
                                   part=part, series_hub=series_hub, hub_title=hub_title)
            break
        except (ValueError, json.JSONDecodeError) as e:
            log(f"  Writer attempt {attempt + 1} failed: {e} . {'retrying...' if attempt == 0 else 'giving up'}")
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

    # Compute url_path for Attia mode (e.g., /es/para/agencias-de-marketing/<slug>/)
    url_path = ""
    if mode == "attia-longform" and vertical:
        slug = blog_data.get("slug", "")
        url_path = f"/es/para/{vertical}/{slug}/"

    # Save to globalhighlevel-site/posts/
    slug = save_post(topic, blog_data, final_html, url_path=url_path,
                     hub_url=series_hub, hub_title=hub_title,
                     vertical=vertical, part=part)

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
    parser.add_argument("--mode", type=str, default="standard",
                        choices=["standard", "attia-longform"],
                        help="Writing mode. attia-longform = 2500+ word pillar in Peter Attia style")
    parser.add_argument("--vertical", type=str, default="",
                        help="Vertical slug (e.g., agencias-de-marketing). Required with --mode=attia-longform")
    parser.add_argument("--part", type=int, default=0,
                        help="Part number in the series (1-9). Required with --mode=attia-longform")
    parser.add_argument("--series-hub", type=str, default="",
                        help="URL path of the series hub (e.g., /es/para/agencias-de-marketing/)")
    parser.add_argument("--hub-title", type=str, default="",
                        help="Human-readable title of the series hub for breadcrumb")
    args = parser.parse_args()

    # Attia mode: run a single part immediately and exit
    if args.mode == "attia-longform":
        if not args.topic or not args.vertical or not args.part:
            parser.error("--mode=attia-longform requires --topic, --vertical, and --part")
        log(f"Attia long-form run: vertical={args.vertical} part={args.part}")
        result = process_topic(args.topic, mode="attia-longform",
                               vertical=args.vertical, part=args.part,
                               series_hub=args.series_hub, hub_title=args.hub_title)
        published = load_published()
        published.append(result)
        save_published(published)
        log(f"✅ Attia Part {args.part} written: {result.get('slug')}")
        return

    published = load_published()

    if args.topic:
        topics = [args.topic]
        sourced_topics = []
    else:
        # Tier 1 + 2: Get properly sourced topics from the topic sourcer
        try:
            from topic_sourcer import get_topics
            sourced_topics = get_topics(language="es", published=published, limit=args.limit or 5)
            log(f"Topic sourcer: {len(sourced_topics)} topics ({sum(1 for t in sourced_topics if t['tier']==1)} docs, {sum(1 for t in sourced_topics if t['tier']==2)} GSC)")
        except Exception as e:
            log(f"Topic sourcer unavailable ({e}) . falling back to topic list")
            sourced_topics = []

        # Tier 3 fallback: existing topic list + auto-generation
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
                        log(f"Added {added} GSC-sourced Spanish topics . now {len(pending)} pending")
            except Exception:
                pass

    # Auto-generate topics if still running low
    if len(pending) < 10 and not args.topic:
        log(f"Only {len(pending)} topics left . generating 15 more...")
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            already_done = [t for t in topics if is_published(t, published)]
            done_list = "\n".join(f"- {t}" for t in already_done[-20:])
            msg = client.messages.create(
                model=MODEL,
                max_tokens=1500,
                messages=[{"role": "user", "content": f"""Genera 15 temas de blog sobre GoHighLevel para negocios y agencias en Latinoamérica.

Estos temas ya se han cubierto . NO los repitas:
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
            log(f"Generated {len(new_topics)} new topics . now {len(pending)} pending")
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
            log(f"FAILED: {topic[:60]} . {e}")
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

    log(f"Spanish blog run complete . {processed} topics processed")


if __name__ == "__main__":
    main()
