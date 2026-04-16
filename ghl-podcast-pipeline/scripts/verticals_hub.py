"""
verticals_hub.py

Generates the series hub page for a vertical. Hub lives at /es/para/[vertical]/
and acts as the topical authority landing page for the 9-part series.

The hub JSON is saved the same way as a blog post (with url_path set so build.py
routes it to the correct directory). It's not a "post" in the analytics sense . it's
a landing page that frames the series and lists spokes.

Called by verticals-dispatch.py BEFORE Part 1 ships (the hub must exist so Part 1
can link back to it, and so retrofit links into it aren't broken).
"""

import os
import re
import json
import anthropic
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

try:
    from cost_logger import log_api_cost
except ImportError:
    def log_api_cost(*a, **kw):
        return {}

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"

BASE_DIR = Path(__file__).parent.parent
SITE_POSTS = Path("/opt/globalhighlevel-site/posts") if Path("/opt/globalhighlevel-site/posts").exists() else BASE_DIR.parent / "globalhighlevel-site" / "posts"


# Title templates for the 9-part series (per verticals-pipeline SKILL.md)
PART_TITLES_ES = {
    1: "Por qué {vertical_plural} necesitan un CRM en 2026",
    2: "El mejor CRM para {vertical_plural} este año",
    3: "GoHighLevel vs Clientify para {vertical_plural}: comparación honesta",
    4: "Cómo configurar GoHighLevel para una {vertical_singular}",
    5: "Los workflows de GoHighLevel que {vertical_plural} usan de verdad",
    6: "Precios de GoHighLevel para una {vertical}: los números reales",
    7: "Qué cambia en el mes 1 cuando una {vertical_singular} adopta GoHighLevel",
    8: "¿Vale la pena GoHighLevel para una {vertical_singular} solo?",
    9: "Errores comunes que {vertical_plural} cometen al configurar GoHighLevel",
}


def generate_hub(vertical: str, vertical_plural: str, vertical_singular: str,
                 hub_title: str, hub_intro_angle: str,
                 cluster_spokes: list[dict], language: str = "es") -> dict:
    """
    Generate the hub page content.

    Args:
        vertical: slug (e.g., "agencias-de-marketing")
        vertical_plural: e.g., "agencias de marketing"
        vertical_singular: e.g., "agencia de marketing"
        hub_title: e.g., "GoHighLevel para Agencias de Marketing"
        hub_intro_angle: one-line framing of why this vertical
        cluster_spokes: list of {"url": "/blog/...", "title": "...", "angle": "..."}
        language: "es" (only ES supported for now)

    Returns:
        post-shaped dict ready to be saved as JSON
    """
    trial_url = "https://globalhighlevel.com/trial"
    extendly_url = "https://extendly.com/gohighlevel/?deal=vqzoli"

    # Build part list for the Attia writer
    part_list_prompt = "\n".join(
        f"  Parte {n}: {tpl.format(vertical_plural=vertical_plural, vertical_singular=vertical_singular, vertical=vertical_plural)}"
        for n, tpl in PART_TITLES_ES.items()
    )

    spoke_list_prompt = "\n".join(
        f"  - {s.get('title', s['url'])} ({s['url']}) . ángulo: {s.get('angle', 'related')}"
        for s in cluster_spokes
    )

    prompt = f"""Eres un editor que escribe la página hub de una serie de 9 partes sobre GoHighLevel para {vertical_plural}. El hub vive en /es/para/{vertical}/ y es la página de autoridad topical de la serie. Estilo Peter Attia "Straight Dope" . concreto, denso, pedagógico, sin marketing vacío.

VERTICAL: {vertical_plural}
ÁNGULO DEL HUB: {hub_intro_angle}

LA SERIE COMPLETA (9 partes):
{part_list_prompt}

SPOKES EXISTENTES EN EL SITIO (linkear dentro del hub cuando sea tópicamente relevante):
{spoke_list_prompt}

ENLACE DE PRUEBA (CTA principal): {trial_url}
ENLACE EXTENDLY (CTA secundario): {extendly_url}

═══════════════════════════════════════════════════════════════════
ESTRUCTURA OBLIGATORIA DEL HUB
═══════════════════════════════════════════════════════════════════

1. CTA PRIMARIO ARRIBA (primera línea):
<p style="background:#111520;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:4px;color:#eef2ff;"><strong>🚀 Prueba GoHighLevel GRATIS por 30 días</strong> . Sin tarjeta de crédito. <a href="{trial_url}" style="color:#f59e0b;" target="_blank">Empieza tu prueba gratis aquí →</a></p>

2. PRE-INTRO (1 párrafo, máx 100 palabras, sin heading):
   Nombra al lector concretamente (dueño de {vertical_singular}). Nombra el problema en términos concretos. Promete qué explica la serie completa. NO menciones GHL aún.

3. "¿QUÉ VAS A APRENDER EN ESTA SERIE?" (caja destacada con 5-7 objetivos de aprendizaje de alto nivel que cubran toda la serie):
<p style="background:#f5f5f0;border-left:4px solid #111520;padding:16px;"><strong>Al terminar esta serie entenderás:</strong></p>
<ol><li>...</li></ol>

4. "LAS 9 PARTES DE LA SERIE" (H2 + lista numerada con 1 línea de resumen por parte):
<h2>Las 9 partes de la serie</h2>
<ol>
  <li><strong>Parte 1.</strong> [título de Parte 1] . [1 línea de qué cubre y para quién]</li>
  <li><strong>Parte 2.</strong> [título de Parte 2] . [1 línea] <em>(próximamente)</em></li>
  ... (Parts 2-9 marcados "próximamente")
</ol>
Marca TODAS las partes 2-9 con "(próximamente)". Solo la Parte 1 NO lleva ese marcador.

5. "LECTURA RELACIONADA EN ESPAÑOL" (H2 + lista de spokes existentes):
<h2>Lectura relacionada</h2>
<p>Mientras escribimos las Partes 2-9, estos posts existentes cubren ángulos específicos para {vertical_plural}:</p>
<ul>
  <li><a href="[spoke url]">[título del spoke]</a> . [1 línea de ángulo]</li>
  ... (todos los spokes proporcionados arriba, enlaces directos a sus URLs)
</ul>

6. CTA SECUNDARIO EXTENDLY (mitad del hub):
<p style="background:#fefbf0;border:1px solid #f59e0b;padding:16px;border-radius:4px;"><strong>¿Prefieres implementación hecha por expertos?</strong> Extendly maneja el onboarding de GoHighLevel, soporte white-label 24/7 en español, y snapshots pre-construidos para {vertical_plural}. Los recomendamos para quien quiere el sistema funcionando sin hacer el setup. <a href="{extendly_url}" target="_blank" rel="nofollow noopener">Ver Extendly →</a></p>

7. "POR QUÉ ESTA SERIE EXISTE" (H2 + 1-2 párrafos sobre el ángulo único):
   El ángulo concreto que motiva la serie: {hub_intro_angle}. Por qué no otro CRM, por qué 9 partes, por qué ahora.

8. CTA PRIMARIO ABAJO:
<p style="background:#111520;border-left:4px solid #f59e0b;padding:16px;border-radius:4px;color:#eef2ff;text-align:center;"><strong>Empieza tu prueba de 30 días de GoHighLevel</strong><br>Sin tarjeta de crédito. Cancela cuando quieras.<br><a href="{trial_url}" style="color:#f59e0b;font-weight:bold;" target="_blank">Empezar prueba gratis →</a></p>

═══════════════════════════════════════════════════════════════════
REGLA #0 . NUNCA FABRICAR
═══════════════════════════════════════════════════════════════════
- NO personas inventadas, NO clientes inventados
- NO cifras inventadas sin fuente (ingresos, % crecimiento, conteo de clientes)
- NO "confiado por X agencias" ni social proof con conteos
- Precios GHL: Starter $97/mes, Agency $297/mes (solo menciona si cita fuente primaria)

LONGITUD: 800-1500 palabras
IDIOMA: español latinoamericano NEUTRO. Usar "tú" + formas verbales neutras: "tienes", "necesitas", "puedes", "diriges". NUNCA usar voseo argentino/rioplatense: NO "tenés", NO "necesitás", NO "podés", NO "dirigís", NO "sos". NO traducción literal del inglés.
SIN em-dashes en absoluto. Usa coma, punto, o paréntesis.
SIN frases-IA prohibidas: "aprovechar", "utilizar", "sumergirnos", "en el mundo actual", "llevar al siguiente nivel", "desbloquear", "revolucionar", "ecosistema" (no-biología), "journey", "robusto", "holístico", "onboarding" (usa "incorporación" o mejor, describe qué es).

Devuelve JSON:
{{
  "html_content": "HTML completo del hub con los 8 elementos arriba en orden",
  "meta_description": "150-158 chars, con 'GoHighLevel' y '{vertical_plural}' en los primeros 80 chars",
  "title": "H1 del hub en español"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="verticals_hub-generate")

    raw = response.content[0].text.strip()
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        raise ValueError("Hub generator did not return valid JSON")

    generated = json.loads(json_match.group())

    # Build the post-shaped dict
    url_path = f"/es/para/{vertical}/"
    hub_slug = f"hub-{vertical}"

    meta_desc = generated.get("meta_description", "")
    if len(meta_desc) > 160:
        meta_desc = meta_desc[:157] + "..."

    post_data = {
        "title": generated.get("title", hub_title),
        "slug": hub_slug,
        "description": meta_desc,
        "html_content": generated.get("html_content", ""),
        "category": "Agency & Platform",
        "tags": ["gohighlevel", "español", "latinoamérica", vertical, "serie"],
        "language": "es",
        "publishedAt": datetime.now().isoformat(),
        "author": "Global High Level",
        "url_path": url_path,
        "vertical": vertical,
        "is_series_hub": True,
    }

    return post_data


def save_hub(hub_data: dict) -> Path:
    """Save hub JSON to posts/ directory. Returns the path."""
    SITE_POSTS.mkdir(parents=True, exist_ok=True)
    slug = hub_data["slug"]
    post_path = SITE_POSTS / f"{slug}.json"
    with open(post_path, "w") as f:
        json.dump(hub_data, f, indent=2, ensure_ascii=False)
    return post_path


if __name__ == "__main__":
    # Manual test
    spokes = [
        {"url": "/blog/automatizaciones-gohighlevel-agencias-marketing-digital/",
         "title": "Automatizaciones en GoHighLevel para Agencias",
         "angle": "core-pillar"},
        {"url": "/blog/que-es-gohighlevel-plataforma-automatizacion-agencias-latinoamericanas/",
         "title": "¿Qué es GoHighLevel?",
         "angle": "platform-intro"},
    ]
    hub = generate_hub(
        vertical="agencias-de-marketing",
        vertical_plural="agencias de marketing",
        vertical_singular="agencia de marketing",
        hub_title="GoHighLevel para Agencias de Marketing",
        hub_intro_angle="Agencias latinoamericanas pequeñas (3-10 personas) gastando $500+/mes en herramientas separadas, con WhatsApp como canal real pero SMS-first tools",
        cluster_spokes=spokes,
    )
    path = save_hub(hub)
    print(f"Hub saved: {path}")
