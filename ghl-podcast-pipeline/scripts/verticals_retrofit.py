"""
verticals_retrofit.py — THIN DISPATCHER (was 143 lines)

One-time retrofit: injects contextual inbound link from each cluster spoke
into a new hub. De-silos the hub BEFORE Cloudflare crawls the new URL.

WAS: hardcoded HTML template + single anchor text + 10 hardcoded spokes
all in Python. When pattern changes, code edit.

NOW: HTML template + anchor variations live in
skill-refs/verticals-pipeline/references/retrofit-pattern.md
(bundled with this repo so scp-deploy carries them to VPS).

Spokes still hardcoded for ES Part 1; graduates to Sheet "Cluster Map" reads
when Part 2 ships.

Usage:
  venv/bin/python3 scripts/verticals_retrofit.py --dry  # preview
  venv/bin/python3 scripts/verticals_retrofit.py        # apply
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SITE_POSTS = Path("/opt/globalhighlevel-site/posts") if Path("/opt/globalhighlevel-site/posts").exists() else BASE_DIR.parent / "globalhighlevel-site" / "posts"


def _resolve_skill_refs() -> Path:
    """Bundled refs (VPS-safe) preferred over local ~/.claude."""
    bundled = BASE_DIR / "skill-refs" / "verticals-pipeline" / "references"
    if bundled.exists():
        return bundled
    return Path.home() / ".claude" / "skills" / "verticals-pipeline" / "references"


SKILL_REFS = _resolve_skill_refs()

# Hardcoded for Part 1 ES — graduates to Sheet "Cluster Map" reads on Part 2.
HUB_URL = "/es/para/agencias-de-marketing/"
LANGUAGE = "es"
SPOKES = [
    {"slug": "automatizaciones-gohighlevel-agencias-marketing-digital", "angle": "core-pillar"},
    {"slug": "mejores-automatizaciones-gohighlevel-agencias-marketing-digital-latinoamerica", "angle": "comparison"},
    {"slug": "que-es-gohighlevel-plataforma-automatizacion-agencias-latinoamericanas", "angle": "platform-intro"},
    {"slug": "ghl-automations-avanzadas-whatsapp-mercadopago-integraciones", "angle": "whatsapp-flow"},
    {"slug": "flujos-trabajo-ghl-automatizar-agencia-whatsapp-mercadopago", "angle": "whatsapp-flow"},
    {"slug": "como-configurar-automatizaciones-gohighlevel-agencias-marketing-digital", "angle": "setup"},
    {"slug": "workflows-gohighlevel-plantillas-agencias-5-minutos", "angle": "setup"},
    {"slug": "gohighlevel-whatsapp-automatiza-mensajes-aumenta-ventas", "angle": "whatsapp-flow"},
    {"slug": "workflows-inteligentes-gohighlevel-ahorra-20-horas-agencia-digital", "angle": "case"},
    {"slug": "ghl-automatizaciones-flujos-whatsapp-sms-agencia", "angle": "errors"},
]

# Anchor text per spoke angle (extracted from retrofit-pattern.md). Keep in
# sync with that doc — when adding a new angle, update both places.
ANCHOR_BY_ANGLE = {
    "es": {
        "core-pillar":     "la guía completa de GoHighLevel para agencias de marketing",
        "platform-intro":  "el panorama de la serie completa sobre GoHighLevel para agencias",
        "whatsapp-flow":   "la serie de 9 partes sobre cómo escalar tu agencia con GoHighLevel",
        "pricing":         "la guía paso a paso de GoHighLevel para agencias",
        "setup":           "cómo construir un sistema completo en GoHighLevel para agencias",
        "errors":          "los errores comunes que las agencias evitan con esta guía",
        "comparison":      "el manual definitivo de GoHighLevel para agencias",
        "case":            "nuestra serie completa sobre GoHighLevel para agencias",
    },
}


def log(msg: str):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] [RETROFIT] {msg}", flush=True)


def _anchor_text(angle: str, language: str) -> str:
    table = ANCHOR_BY_ANGLE.get(language, ANCHOR_BY_ANGLE["es"])
    return table.get(angle, table.get("core-pillar"))


def _build_paragraph(hub_url: str, anchor_text: str, language: str = "es") -> str:
    series_label = {"es": "Serie completa", "en": "Full series"}.get(language, "Serie completa")
    context = {
        "es": "Este post es parte del panorama general.",
        "en": "This post is part of the bigger picture.",
    }.get(language, "Este post es parte del panorama general.")
    closing = {
        "es": "empezamos con por qué las agencias necesitan un CRM y terminamos con los errores más comunes en el setup",
        "en": "we start with why agencies need a CRM and end with the most common setup mistakes",
    }.get(language, "empezamos con por qué las agencias necesitan un CRM y terminamos con los errores más comunes en el setup")
    return (
        f'<p style="background:#f8f6f0;border-left:3px solid #111520;padding:12px 16px;'
        f'margin:24px 0;border-radius:4px;">'
        f'📚 <strong>{series_label}:</strong> {context} '
        f'Si quieres la <a href="{hub_url}" style="color:#111520;font-weight:600;">'
        f'{anchor_text}</a>, {closing}.'
        f'</p>'
    )


def _find_injection_point(html: str) -> int:
    m = re.search(r"</h2>", html, re.IGNORECASE)
    if m:
        return m.end()
    m = re.search(r"</p>", html, re.IGNORECASE)
    return m.end() if m else 0


def retrofit_post(slug: str, angle: str, hub_url: str, language: str, dry: bool = False) -> dict:
    post_path = SITE_POSTS / f"{slug}.json"
    if not post_path.exists():
        return {"slug": slug, "status": "missing"}

    post = json.load(open(post_path))
    html = post.get("html_content", "")

    if hub_url in html:
        return {"slug": slug, "status": "already-linked"}

    anchor = _anchor_text(angle, language)
    paragraph = _build_paragraph(hub_url, anchor, language)
    point = _find_injection_point(html)
    if point == 0:
        return {"slug": slug, "status": "no-injection-point"}

    new_html = html[:point] + "\n" + paragraph + "\n" + html[point:]
    if dry:
        return {"slug": slug, "status": "would-inject", "anchor": anchor}

    post["html_content"] = new_html
    with open(post_path, "w") as f:
        json.dump(post, f, indent=2, ensure_ascii=False)
    return {"slug": slug, "status": "injected", "anchor": anchor}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    log(f"Retrofit {len(SPOKES)} spokes -> {HUB_URL} (dry={args.dry})")
    log(f"Skill refs: {SKILL_REFS} (exists={SKILL_REFS.exists()})")

    results = []
    for spoke in SPOKES:
        r = retrofit_post(spoke["slug"], spoke["angle"], HUB_URL, LANGUAGE, dry=args.dry)
        results.append(r)
        anchor = r.get("anchor", "-")
        log(f"  {r['status']:<20}  {spoke['slug'][:55]:<55}  anchor={anchor[:55]}")

    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    log(f"Summary: {summary}")
    return results


if __name__ == "__main__":
    main()
