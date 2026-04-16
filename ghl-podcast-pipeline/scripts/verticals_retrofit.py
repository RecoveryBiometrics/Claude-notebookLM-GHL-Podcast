"""
verticals_retrofit.py

One-time retrofit: injects a contextual inbound link from each cluster spoke
post into the new hub. De-silos the hub BEFORE Cloudflare crawls the new URL.

Hardcoded for the ES agency cluster (10 spokes → /es/para/agencias-de-marketing/).
Idempotent: skips any post where the hub link already exists.

Usage:
  venv/bin/python3 scripts/verticals_retrofit.py --dry  # show what would change
  venv/bin/python3 scripts/verticals_retrofit.py        # apply + save
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SITE_POSTS = Path("/opt/globalhighlevel-site/posts") if Path("/opt/globalhighlevel-site/posts").exists() else BASE_DIR.parent / "globalhighlevel-site" / "posts"

HUB_URL = "/es/para/agencias-de-marketing/"
HUB_ANCHOR_TEXT_DEFAULT = "la guía completa de GoHighLevel para agencias de marketing"

# Slugs of the 10 cluster spokes (matches the Cluster Map tab in the Sheet)
SPOKES = [
    "automatizaciones-gohighlevel-agencias-marketing-digital",
    "mejores-automatizaciones-gohighlevel-agencias-marketing-digital-latinoamerica",
    "que-es-gohighlevel-plataforma-automatizacion-agencias-latinoamericanas",
    "ghl-automations-avanzadas-whatsapp-mercadopago-integraciones",
    "flujos-trabajo-ghl-automatizar-agencia-whatsapp-mercadopago",
    "como-configurar-automatizaciones-gohighlevel-agencias-marketing-digital",
    "workflows-gohighlevel-plantillas-agencias-5-minutos",
    "gohighlevel-whatsapp-automatiza-mensajes-aumenta-ventas",
    "workflows-inteligentes-gohighlevel-ahorra-20-horas-agencia-digital",
    "ghl-automatizaciones-flujos-whatsapp-sms-agencia",
]

# Inline paragraph template — soft, natural, not spammy
RETROFIT_PARAGRAPH_TEMPLATE = (
    '<p style="background:#f8f6f0;border-left:3px solid #111520;padding:12px 16px;'
    'margin:24px 0;border-radius:4px;">'
    '📚 <strong>Serie completa:</strong> Este post es parte del panorama general. '
    f'Si quieres la <a href="{HUB_URL}" style="color:#111520;font-weight:600;">'
    '{anchor_text}</a>, empezamos con por qué las agencias necesitan un CRM y '
    'terminamos con los errores más comunes en el setup.'
    '</p>'
)


def log(msg: str):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] [RETROFIT] {msg}", flush=True)


def find_injection_point(html: str) -> int:
    """Find a good place to inject the retrofit paragraph.
    Returns character index. Prefers: after the 2nd <h2>, falling back to after the
    first <p>, falling back to end of content."""
    import re
    # Try: after the second H2 block (closing </h2>)
    h2_positions = [m.end() for m in re.finditer(r'</h2>', html, re.IGNORECASE)]
    if len(h2_positions) >= 2:
        return h2_positions[1]
    # Fallback: after first closing </p>
    p_match = re.search(r'</p>', html, re.IGNORECASE)
    if p_match:
        return p_match.end()
    # Fallback: end of content
    return len(html)


def retrofit_post(slug: str, dry: bool = False) -> dict:
    """Add a hub link to one spoke. Returns summary dict."""
    path = SITE_POSTS / f"{slug}.json"
    if not path.exists():
        return {"slug": slug, "status": "missing", "reason": f"file not found at {path}"}

    with open(path) as f:
        post = json.load(f)

    html = post.get("html_content", "")
    if HUB_URL in html:
        return {"slug": slug, "status": "already-linked"}

    injection_idx = find_injection_point(html)
    retrofit_html = RETROFIT_PARAGRAPH_TEMPLATE.format(
        anchor_text=HUB_ANCHOR_TEXT_DEFAULT
    )
    new_html = html[:injection_idx] + "\n" + retrofit_html + "\n" + html[injection_idx:]

    if dry:
        return {"slug": slug, "status": "would-update",
                "injection_char": injection_idx,
                "bytes_added": len(retrofit_html)}

    post["html_content"] = new_html
    post["_retrofit_hub_link"] = HUB_URL
    post["_retrofit_at"] = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(post, f, indent=2, ensure_ascii=False)

    return {"slug": slug, "status": "updated", "bytes_added": len(retrofit_html)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="Show what would change, do not write")
    args = parser.parse_args()

    log(f"Retrofitting {len(SPOKES)} spokes with inbound link to {HUB_URL}")
    if args.dry:
        log("DRY RUN — no files will be changed")

    updated = skipped = missing = 0
    for slug in SPOKES:
        result = retrofit_post(slug, dry=args.dry)
        status = result["status"]
        if status in ("updated", "would-update"):
            updated += 1
            log(f"  ✅ {slug} — {status} (+{result.get('bytes_added', 0)} bytes)")
        elif status == "already-linked":
            skipped += 1
            log(f"  ⏭  {slug} — already linked, skipped")
        elif status == "missing":
            missing += 1
            log(f"  ❌ {slug} — MISSING: {result.get('reason', '')}")

    print()
    print("═" * 50)
    print(f" RETROFIT SUMMARY")
    print("═" * 50)
    print(f"  Updated: {updated}")
    print(f"  Already linked (skipped): {skipped}")
    print(f"  Missing files: {missing}")
    print()
    if not args.dry and updated > 0:
        print(" NEXT: cd globalhighlevel-site && python3 build.py && git commit")


if __name__ == "__main__":
    main()
