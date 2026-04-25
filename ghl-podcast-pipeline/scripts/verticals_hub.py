"""
verticals_hub.py — THIN DISPATCHER (was 228 lines, now ~110)

Generates the series hub page for a vertical. Hub lives at /es/para/[vertical]/
and acts as topical authority for the 9-part series.

WAS: ~150 lines of embedded prompt (8-element structure + Spanish style + CTA
patterns) baked into Python. When the structure rules change, code edit.

NOW: Reads judgment from skill markdown references:
  - references/voice.md           — universal AI-tell banlist
  - references/hub-structure.md   — 8-element hub template + per-language CTAs
  - references/spanish-style.md   — Spanish-specific banlist + voseo rules
  - references/article-template.md — pre-intro / learning objectives style

Python only does deterministic plumbing: load files, call API, parse, save.
When references are edited, next run uses them automatically. No code change.

Called by verticals_dispatch.py BEFORE the pillar ships.
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
def _resolve_skill_refs() -> Path:
    """Prefer the bundled-in-repo refs (works on VPS via scp deploy) over local ~/.claude.

    On VPS: BASE_DIR/skill-refs/verticals-pipeline/references/ (deployed via scp).
    Locally for dev: ~/.claude/skills/verticals-pipeline/references/.
    """
    bundled = BASE_DIR / "skill-refs" / "verticals-pipeline" / "references"
    if bundled.exists():
        return bundled
    return Path.home() / ".claude" / "skills" / "verticals-pipeline" / "references"

SKILL_REFS = _resolve_skill_refs()

# 9-part title templates — kept here (small, deterministic). Could move to a
# data file. Per language. ES is the only fully-shipped language for now.
PART_TITLES = {
    "es": {
        1: "Por qué {vertical_plural} necesitan un CRM en 2026",
        2: "El mejor CRM para {vertical_plural} este año",
        3: "GoHighLevel vs Clientify para {vertical_plural}: comparación honesta",
        4: "Cómo configurar GoHighLevel para una {vertical_singular}",
        5: "Los workflows de GoHighLevel que {vertical_plural} usan de verdad",
        6: "Precios de GoHighLevel para una {vertical_singular}: los números reales",
        7: "Qué cambia en el mes 1 cuando una {vertical_singular} adopta GoHighLevel",
        8: "¿Vale la pena GoHighLevel para una {vertical_singular} solo?",
        9: "Errores comunes que {vertical_plural} cometen al configurar GoHighLevel",
    },
}

LANGUAGE_BANLIST_REF = {
    "es": "spanish-style.md",
    # "en": "english-style.md", "in": "india-style.md", "ar": "arabic-style.md" — future
}


def _load_skill_refs(language: str) -> str:
    """Load all relevant markdown references and concat as system prompt."""
    refs = ["voice.md", "hub-structure.md", "article-template.md"]
    lang_ref = LANGUAGE_BANLIST_REF.get(language)
    if lang_ref:
        refs.append(lang_ref)
    parts = []
    for r in refs:
        path = SKILL_REFS / r
        if path.exists():
            parts.append(f"# {r}\n\n{path.read_text()}")
    return "\n\n---\n\n".join(parts)


def generate_hub(vertical: str, vertical_plural: str, vertical_singular: str,
                 hub_title: str, hub_intro_angle: str,
                 cluster_spokes: list[dict], language: str = "es") -> dict:
    """Generate the hub page content. Returns post-shaped dict ready to save."""
    system_prompt = _load_skill_refs(language)

    titles = PART_TITLES.get(language, PART_TITLES["es"])
    part_list = "\n".join(
        f"  Parte {n}: {tpl.format(vertical_plural=vertical_plural, vertical_singular=vertical_singular)}"
        for n, tpl in titles.items()
    )
    spoke_list = "\n".join(
        f"  - {s.get('title', s['url'])} ({s['url']}) — angle: {s.get('angle', 'related')}"
        for s in cluster_spokes
    )

    user_msg = f"""Generate the series hub page for this vertical, following ALL rules in your system prompt:
- voice.md banlist (no em-dashes, no AI-tell phrases)
- hub-structure.md (8 elements in exact order, per-language CTA wording)
- spanish-style.md if language=es (no voseo, neutral LatAm "tú")
- article-template.md pre-intro and learning objectives style

VERTICAL: {vertical_plural}
VERTICAL_SINGULAR: {vertical_singular}
SLUG: {vertical}
LANGUAGE: {language}
HUB_INTRO_ANGLE: {hub_intro_angle}

THE 9 PARTS OF THIS SERIES (titles for hub element 4):
{part_list}

EXISTING CLUSTER SPOKES (for hub element 5 — link these by their real URLs):
{spoke_list}

CTA URLs:
- trial_url: https://globalhighlevel.com/{language}/trial/
- extendly_url: https://extendly.com/gohighlevel/?deal=vqzoli

Length: 800-1500 words.
Meta description: 150-158 chars, with "GoHighLevel" + "{vertical_plural}" in first 80 chars.

Output JSON ONLY (no prose, no code fences):
{{
  "html_content": "Full HTML of hub with all 8 elements in order from hub-structure.md",
  "meta_description": "150-158 chars",
  "title": "H1 of hub in {language}"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )
    log_api_cost(response, script="verticals_hub-generate")

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        raise ValueError("Hub generator did not return valid JSON")

    generated = json.loads(json_match.group())

    meta_desc = generated.get("meta_description", "")
    if len(meta_desc) > 160:
        meta_desc = meta_desc[:157] + "..."

    return {
        "title": generated.get("title", hub_title),
        "slug": f"hub-{vertical}",
        "description": meta_desc,
        "html_content": generated.get("html_content", ""),
        "category": "Agency & Platform",
        "tags": ["gohighlevel", language, vertical, "serie"],
        "language": language,
        "publishedAt": datetime.now().isoformat(),
        "author": "Global High Level",
        "url_path": f"/{language}/para/{vertical}/" if language == "es" else f"/{language}/for/{vertical}/",
        "vertical": vertical,
        "is_series_hub": True,
    }


def save_hub(hub_data: dict) -> Path:
    """Save hub JSON to posts/ directory. Returns the path."""
    SITE_POSTS.mkdir(parents=True, exist_ok=True)
    post_path = SITE_POSTS / f"{hub_data['slug']}.json"
    with open(post_path, "w") as f:
        json.dump(hub_data, f, indent=2, ensure_ascii=False)
    return post_path


if __name__ == "__main__":
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
