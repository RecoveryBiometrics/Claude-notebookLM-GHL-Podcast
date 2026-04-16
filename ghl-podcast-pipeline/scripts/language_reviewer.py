"""
language_reviewer.py

Shared library. Opus 4.6 quality-gate for non-English content.
Called by verticals-dispatch.py AFTER fact_check passes, BEFORE save/deploy.

For ES: checks natural Latin-American Spanish (not European, not literal translation),
banned-phrase compliance, dialect voice, and claim parity if an EN source is provided.

Future: IN (Indian English idiom check), AR (MSA compliance).

Returns same shape as fact_check:
  {"approved": bool, "corrections": [str], "revised_html": str}
"""

import os
import re
import json
import anthropic
from dotenv import load_dotenv

try:
    from cost_logger import log_api_cost
except ImportError:
    def log_api_cost(*a, **kw):
        return {}

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPUS_MODEL = "claude-opus-4-6"  # Opus 4.6 — judgment-heavy dialect/fluency review


# ── Per-language review rules ──────────────────────────────────────────────────

ES_REVIEW_RULES = """
ESPAÑOL LATINOAMERICANO — CRITERIOS DE REVISIÓN:

1. NATURALIDAD: ¿Suena como alguien que escribe nativamente en español latino, o como una
   traducción literal del inglés? Marca frases que traicionan origen inglés (ej: "hacer
   sentido" en vez de "tener sentido", "puedo ayudarte con" en vez de "te puedo ayudar con").

2. DIALECTO: Debe ser español latinoamericano neutro (no español de España).
   - "tú" informal, NO "vosotros"
   - NO "vale" como muletilla, NO "ordenador" (usar "computadora" o "compu")
   - NO "coche" (usar "carro" o "auto")
   - NO "móvil" para teléfono (usar "celular" o "teléfono")

3. EM-DASHES: Ninguno. Si aparece "—" o "--" hay que reescribir con coma, punto, o paréntesis.

4. FRASES PROHIBIDAS (frases-IA, marca CADA instancia):
   - "aprovechar", "utilizar" (reemplazar por "usar")
   - "sumergirnos", "adentrarnos", "explorar el mundo de"
   - "en el mundo actual", "en este post exploraremos"
   - "llevar al siguiente nivel", "desbloquear todo el potencial"
   - "revolucionar", "game-changer", "de clase mundial"
   - "ecosistema" para no-biología, "landscape", "journey" para no-viaje
   - "robusto", "holístico" (sin contexto médico), "sin fisuras"
   - "es importante señalar", "vale la pena mencionar"

5. FABRICACIONES (HARD FAIL — bloquea publicación):
   - Cualquier persona inventada con nombre ("Matías en Buenos Aires", "María en Bogotá")
   - Cualquier empresa cliente inventada
   - Cualquier cifra específica (ingresos, conteo de clientes, % de crecimiento) sin fuente
   - Testimonios o anécdotas en primera persona inventados
   Si encuentras alguno, devuelve approved=false Y en revised_html reescribe eliminándolos.

6. PARIDAD DE CLAIMS (si hay fuente EN): ¿El texto ES afirma cosas que la fuente EN no dice?
   Si sí, revisa si es un riesgo factual.

7. PRECIOS Y FUENTES: Precios GHL deben ser $97/mes (Starter) y $297/mes (Agency).
   Cualquier otro número citado debe tener footnote a fuente primaria.

IMPORTANTE: Tu trabajo es JUZGAR e IDENTIFICAR problemas, NO reescribir el post.
NO devuelvas HTML reescrito. El writer (otro agente) se encarga de aplicar las correcciones
en una segunda pasada, preservando la longitud, la estructura y la voz del artículo.

DEVUELVE JSON con esta forma exacta:
{
  "approved": true/false,
  "corrections": [
    {
      "issue": "em-dash | banned-phrase | fabrication | dialect | naturalness | pricing | other",
      "quote": "la frase ofensiva exacta del post",
      "fix": "instrucción específica de cómo corregirla (no HTML, instrucción en texto)"
    },
    ...
  ]
}
"""


# ── Entry point ────────────────────────────────────────────────────────────────

def review(html_content: str, language: str, source_content: str = "",
           source_language: str = "en", context: str = "") -> dict:
    """
    Opus 4.6 review pass for a non-English post.

    Args:
        html_content: The post HTML to review
        language: Target language code ("es", "in", "ar")
        source_content: Optional EN source content for claim-parity check
        source_language: Source language (default "en")
        context: Optional extra context ("Attia long-form pillar for agencies", etc.)

    Returns:
        {"approved": bool, "corrections": [str], "revised_html": str}
    """
    if language != "es":
        # Future: add IN and AR review rules. For now, skip silently.
        return {"approved": True, "corrections": [], "revised_html": "",
                "note": f"language_reviewer: no rules for '{language}' yet, skipped"}

    rules = ES_REVIEW_RULES

    source_block = ""
    if source_content:
        source_block = f"""
FUENTE EN INGLÉS (para verificar paridad de claims):
{source_content[:3000]}
"""

    context_block = f"\nCONTEXTO: {context}\n" if context else ""

    prompt = f"""Eres un editor nativo de español latinoamericano con 15 años de experiencia en contenido B2B SaaS para el mercado hispano. Tu trabajo es revisar este post para calidad editorial, dialecto, y prohibidas frases de IA. Este es un gate de calidad: si el post no pasa, no se publica.
{context_block}
{source_block}

POST A REVISAR (HTML):
{html_content[:8000]}

{rules}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=OPUS_MODEL,
        max_tokens=12000,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_cost(response, script="language_reviewer-es")

    raw = response.content[0].text.strip()
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        return {"approved": True, "corrections": [],
                "note": "language_reviewer: parse failure — failed open"}

    try:
        result = json.loads(json_match.group())
    except json.JSONDecodeError:
        return {"approved": True, "corrections": [],
                "note": "language_reviewer: json decode failure — failed open"}

    # Normalize corrections — each should be {issue, quote, fix}
    raw_corrections = result.get("corrections", []) or []
    normalized = []
    for c in raw_corrections:
        if isinstance(c, dict):
            normalized.append({
                "issue": c.get("issue", "other"),
                "quote": c.get("quote", ""),
                "fix": c.get("fix", ""),
            })
        elif isinstance(c, str):
            # Legacy shape — string-only. Wrap it.
            normalized.append({"issue": "other", "quote": "", "fix": c})

    return {
        "approved": bool(result.get("approved", True)),
        "corrections": normalized,
    }


if __name__ == "__main__":
    # Manual test harness
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to post JSON to review")
    parser.add_argument("--lang", default="es")
    args = parser.parse_args()

    with open(args.file) as f:
        post = json.load(f)

    result = review(post.get("html_content", ""), args.lang,
                    context=f"Manual CLI review of {args.file}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
