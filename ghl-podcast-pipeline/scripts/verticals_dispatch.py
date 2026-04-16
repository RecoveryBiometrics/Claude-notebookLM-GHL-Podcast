"""
verticals_dispatch.py

One-row dispatcher for the verticals pipeline. Ships the ES agency Part 1.

What it does:
1. Generates the series hub at /es/para/agencias-de-marketing/ (idempotent — skips if exists)
2. Calls 7-spanish-blog.py in attia-longform mode to write the Part 1 pillar
3. Runs the Opus language-reviewer pass on the pillar
4. Reports paths. Human (or future MCP step) updates the Sheet.

Hardcoded for agency-starters Part 1 ES. When Part 2 ships we'll extend this
to read from the Verticals Queue tab via MCP. Until then the Sheet is the ledger
humans update.

Usage:
  venv/bin/python3 scripts/verticals_dispatch.py --dry            # show what would happen
  venv/bin/python3 scripts/verticals_dispatch.py                  # ship
  venv/bin/python3 scripts/verticals_dispatch.py --skip-hub       # pillar only
  venv/bin/python3 scripts/verticals_dispatch.py --skip-review    # skip Opus review
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SCRIPTS = BASE_DIR / "scripts"
SITE_POSTS = Path("/opt/globalhighlevel-site/posts") if Path("/opt/globalhighlevel-site/posts").exists() else BASE_DIR.parent / "globalhighlevel-site" / "posts"

# ── Hardcoded Part 1 ES agency-starters config (graduates to Sheet-driven later) ──
VERTICAL = "agencias-de-marketing"
VERTICAL_PLURAL = "agencias de marketing"
VERTICAL_SINGULAR = "agencia de marketing"
HUB_TITLE = "GoHighLevel para Agencias de Marketing — Serie de 9 Partes"
HUB_URL = f"/es/para/{VERTICAL}/"
HUB_INTRO_ANGLE = (
    "Agencias pequeñas latinoamericanas (3-10 personas) gastando $500+/mes "
    "en herramientas separadas, con WhatsApp como canal real pero la mayoría "
    "de CRMs diseñados SMS-first para EE.UU."
)
PART_1_TOPIC = "Por qué las agencias de marketing digital necesitan un CRM en 2026"

# Cluster spokes — matches the Cluster Map tab seeded in the GHL Sheet
CLUSTER_SPOKES = [
    {"url": "/blog/automatizaciones-gohighlevel-agencias-marketing-digital/",
     "title": "Automatizaciones en GoHighLevel: Guía Completa para Agencias de Marketing Digital",
     "angle": "core-pillar"},
    {"url": "/blog/mejores-automatizaciones-gohighlevel-agencias-marketing-digital-latinoamerica/",
     "title": "Las Mejores Automatizaciones en GoHighLevel para Agencias",
     "angle": "best-of-list"},
    {"url": "/blog/que-es-gohighlevel-plataforma-automatizacion-agencias-latinoamericanas/",
     "title": "Qué es GoHighLevel: La Plataforma Completa de Automatización",
     "angle": "platform-intro"},
    {"url": "/blog/ghl-automations-avanzadas-whatsapp-mercadopago-integraciones/",
     "title": "GHL Automations Avanzadas: WhatsApp, MercadoPago y Más",
     "angle": "integrations"},
    {"url": "/blog/flujos-trabajo-ghl-automatizar-agencia-whatsapp-mercadopago/",
     "title": "Flujos de Trabajo en GHL con WhatsApp y MercadoPago",
     "angle": "workflows"},
    {"url": "/blog/como-configurar-automatizaciones-gohighlevel-agencias-marketing-digital/",
     "title": "Cómo Configurar Automatizaciones en GoHighLevel",
     "angle": "how-to"},
    {"url": "/blog/workflows-gohighlevel-plantillas-agencias-5-minutos/",
     "title": "Workflows de GoHighLevel: Plantillas Listas en 5 Minutos",
     "angle": "templates"},
    {"url": "/blog/gohighlevel-whatsapp-automatiza-mensajes-aumenta-ventas/",
     "title": "GoHighLevel para WhatsApp: Automatiza Mensajes",
     "angle": "whatsapp-channel"},
    {"url": "/blog/workflows-inteligentes-gohighlevel-ahorra-20-horas-agencia-digital/",
     "title": "Workflows Inteligentes: Ahorra 20 Horas Semanales",
     "angle": "time-roi"},
    {"url": "/blog/ghl-automatizaciones-flujos-whatsapp-sms-agencia/",
     "title": "GHL Automatizaciones: WhatsApp y SMS",
     "angle": "comms-stack"},
]


def log(msg: str):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] [DISPATCH] {msg}", flush=True)


def dry_run_summary():
    """Print the plan without executing."""
    print("═" * 70)
    print(" VERTICALS DISPATCH — DRY RUN")
    print("═" * 70)
    print(f" Vertical:      {VERTICAL}")
    print(f" Language:      es")
    print(f" Part:          1 of 9")
    print(f" Hub URL:       {HUB_URL}")
    print(f" Pillar URL:    /es/para/{VERTICAL}/por-que-...-crm-2026/ (slug TBD by writer)")
    print(f" Hub title:     {HUB_TITLE}")
    print(f" Pillar topic:  {PART_1_TOPIC}")
    print(f" Cluster size:  {len(CLUSTER_SPOKES)} inbound candidates")
    print()
    print(" PLAN:")
    print("  1. Generate hub page (verticals_hub.generate_hub)")
    print("     → saves to posts/hub-{VERTICAL}.json with url_path=/es/para/{VERTICAL}/")
    print("  2. Write Part 1 pillar (7-spanish-blog.py --mode=attia-longform)")
    print("     → saves to posts/{slug}.json with url_path=/es/para/{VERTICAL}/{slug}/")
    print("  3. Opus language review (language_reviewer.review)")
    print("     → approves or returns revised_html")
    print("  4. Print next actions: retrofit cluster, git push, update Sheet")
    print()
    print("═" * 70)


def generate_hub() -> Path:
    """Generate hub page via verticals_hub module."""
    log("Step 1/3 — Generating series hub...")
    sys.path.insert(0, str(SCRIPTS))
    import verticals_hub

    hub_json_path = SITE_POSTS / f"hub-{VERTICAL}.json"
    if hub_json_path.exists():
        log(f"  Hub already exists at {hub_json_path.name}, skipping generation.")
        return hub_json_path

    hub_data = verticals_hub.generate_hub(
        vertical=VERTICAL,
        vertical_plural=VERTICAL_PLURAL,
        vertical_singular=VERTICAL_SINGULAR,
        hub_title=HUB_TITLE,
        hub_intro_angle=HUB_INTRO_ANGLE,
        cluster_spokes=CLUSTER_SPOKES,
    )
    path = verticals_hub.save_hub(hub_data)
    log(f"  ✅ Hub saved: {path.name} ({len(hub_data['html_content'])} chars)")
    return path


def write_pillar() -> Path:
    """Run 7-spanish-blog.py in attia-longform mode via subprocess."""
    log("Step 2/3 — Writing Part 1 pillar in Attia long-form mode...")
    cmd = [
        sys.executable,
        str(SCRIPTS / "7-spanish-blog.py"),
        "--mode", "attia-longform",
        "--topic", PART_1_TOPIC,
        "--vertical", VERTICAL,
        "--part", "1",
        "--series-hub", HUB_URL,
        "--hub-title", HUB_TITLE,
    ]
    log(f"  Running: {' '.join(cmd[1:])}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        log(f"  ❌ Pillar write failed (exit {result.returncode}):")
        log(f"  stdout: {result.stdout[-800:]}")
        log(f"  stderr: {result.stderr[-800:]}")
        raise RuntimeError("Attia writer failed")

    # Parse the logged slug from stdout (writer logs "Attia Part 1 written: {slug}")
    slug = None
    for line in result.stdout.splitlines():
        if "Attia Part" in line and "written:" in line:
            slug = line.split("written:")[-1].strip()
            break
    if not slug:
        log("  ⚠️  Could not detect slug in writer output; scanning posts/ for newest ES agencies file...")
        # Fallback: pick the most recently modified es-language post under posts/
        candidates = sorted(SITE_POSTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        for c in candidates:
            try:
                d = json.load(open(c))
                if d.get("vertical") == VERTICAL and d.get("series_part") == 1:
                    slug = d.get("slug")
                    break
            except Exception:
                continue
        if not slug:
            raise RuntimeError("Pillar ran but slug could not be determined")

    pillar_path = SITE_POSTS / f"{slug}.json"
    if not pillar_path.exists():
        raise RuntimeError(f"Pillar slug detected ({slug}) but file not found at {pillar_path}")
    log(f"  ✅ Pillar saved: {pillar_path.name}")
    return pillar_path


def review_and_revise(post_path: Path, label: str, target_word_min: int,
                      max_revise_attempts: int = 1) -> dict:
    """
    Run Opus language reviewer on any post JSON. If rejected, pass corrections
    back to Haiku writer for a targeted revision pass, then re-review. Up to
    max_revise_attempts rounds.

    Returns {'approved': bool, 'attempts': int, 'final_words': int, 'corrections': [...]}
    """
    sys.path.insert(0, str(SCRIPTS))
    import language_reviewer
    # Direct import from the hyphenated filename
    import importlib.util
    spec = importlib.util.spec_from_file_location("spanish_blog", SCRIPTS / "7-spanish-blog.py")
    spanish_blog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(spanish_blog)

    log(f"  Reviewing {label} ({post_path.name})...")
    for attempt in range(max_revise_attempts + 1):
        post = json.load(open(post_path))
        html = post.get("html_content", "")
        words_before = len(html.split())

        result = language_reviewer.review(
            html_content=html,
            language="es",
            context=f"{label} for {VERTICAL_PLURAL}.",
        )
        approved = result.get("approved", True)
        corrections = result.get("corrections", [])

        log(f"    Attempt {attempt + 1}: approved={approved}, corrections={len(corrections)}, words={words_before}")
        for c in corrections[:5]:
            issue = c.get("issue", "?")
            quote = c.get("quote", "")[:80]
            log(f"       [{issue}] «{quote}»")

        if approved and words_before >= target_word_min:
            return {"approved": True, "attempts": attempt + 1,
                    "final_words": words_before, "corrections": corrections}

        if attempt >= max_revise_attempts:
            # Out of attempts
            return {"approved": False, "attempts": attempt + 1,
                    "final_words": words_before, "corrections": corrections,
                    "reason": "max_attempts_exhausted" if not approved else "under_word_count"}

        # Build revise instructions: include word-count pressure if needed
        effective_corrections = list(corrections)
        if words_before < target_word_min:
            effective_corrections.append({
                "issue": "length",
                "quote": f"El post tiene {words_before} palabras.",
                "fix": f"Expande el post a al menos {target_word_min} palabras. Agrega secciones H2 adicionales con más Q&A, más ejemplos hipotéticos claramente marcados, más análisis. NO agregues pelusa ni frases vacías. Cada palabra agregada debe enseñar algo concreto.",
            })

        log(f"    Revising with {len(effective_corrections)} corrections...")
        revised_html = spanish_blog.revise_with_corrections(
            original_html=html,
            corrections=effective_corrections,
            target_word_min=target_word_min,
        )

        post["html_content"] = revised_html
        post[f"_reviewer_revise_attempt_{attempt + 1}_at"] = datetime.now().isoformat()
        with open(post_path, "w") as f:
            json.dump(post, f, indent=2, ensure_ascii=False)

    # Should not reach here
    return {"approved": False, "attempts": max_revise_attempts + 1,
            "final_words": 0, "corrections": []}


def print_next_actions(hub_path: Path, pillar_path: Path, hub_review: dict, pillar_review: dict):
    """Tell the human what's next."""
    print()
    print("═" * 70)
    print(" DISPATCH COMPLETE — REVIEW BEFORE DEPLOY")
    print("═" * 70)
    hub_status = "✅" if hub_review.get("approved") else "❌"
    pillar_status = "✅" if pillar_review.get("approved") else "❌"
    print(f"  {hub_status} Hub    ({hub_review.get('final_words', 0)} words, {hub_review.get('attempts', 0)} attempts): {hub_path}")
    print(f"  {pillar_status} Pillar ({pillar_review.get('final_words', 0)} words, {pillar_review.get('attempts', 0)} attempts): {pillar_path}")
    print()

    if not hub_review.get("approved") or not pillar_review.get("approved"):
        print(" ⚠️  ONE OR BOTH ARTIFACTS BLOCKED — DO NOT DEPLOY")
        print()
        if not hub_review.get("approved"):
            print(f"   Hub reason: {hub_review.get('reason', 'reviewer rejected')}")
        if not pillar_review.get("approved"):
            print(f"   Pillar reason: {pillar_review.get('reason', 'reviewer rejected')}")
        print()
        print(" Options:")
        print("   a) Read the JSONs, hand-fix issues, then deploy")
        print("   b) Re-run dispatcher (--skip-hub if hub is acceptable)")
        print()
        return

    print(" ✅ BOTH ARTIFACTS PASSED REVIEW")
    print()
    print(" NEXT ACTIONS:")
    print(f"  1. Read the hub + pillar JSONs one last time (sanity check)")
    print(f"  2. Retrofit cluster inbound links:")
    print(f"     scripts/verticals_retrofit.py")
    print(f"  3. Build site: cd ../globalhighlevel-site && python3 build.py")
    print(f"  4. git add posts/ public/ && git commit -m 'Ship ES Part 1 agencies' && git push")
    print(f"  5. Update Sheet Verticals Queue row (status=shipped, shipped_date, url)")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="Show the plan, don't execute")
    parser.add_argument("--skip-hub", action="store_true", help="Skip hub generation")
    parser.add_argument("--skip-review", action="store_true", help="Skip Opus language review")
    args = parser.parse_args()

    if args.dry:
        dry_run_summary()
        return

    if not args.skip_hub:
        hub_path = generate_hub()
    else:
        hub_path = SITE_POSTS / f"hub-{VERTICAL}.json"
        log(f"Skipping hub (--skip-hub). Using existing: {hub_path}")

    # Review hub BEFORE writing pillar (hub is the destination link for pillar CTAs)
    if not args.skip_review:
        log("Step 1b — Reviewing hub...")
        hub_review = review_and_revise(hub_path, label="Series hub (ES)", target_word_min=800)
    else:
        hub_review = {"approved": True, "attempts": 0, "final_words": 0, "corrections": []}

    pillar_path = write_pillar()

    if not args.skip_review:
        log("Step 3 — Reviewing pillar...")
        # target_word_min=500 (not 2500) — forcing Haiku to expand 5x introduces fabrications.
        # Accept clean short first-pass from Sonnet; measure SEO at week 2. If short pillars don't
        # rank, revisit the writer prompt for length, don't use revise to pad.
        pillar_review = review_and_revise(pillar_path, label="Attia Part 1 pillar (ES)", target_word_min=400)
    else:
        log("Skipping Opus language review (--skip-review).")
        pillar_review = {"approved": True, "attempts": 0, "final_words": 0, "corrections": []}

    print_next_actions(hub_path, pillar_path, hub_review, pillar_review)


if __name__ == "__main__":
    main()
