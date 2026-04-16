"""
localize_cta_retrofit.py

One-time retrofit: rewrites bare /trial and /start URLs in existing non-English
post JSONs to their language-appropriate localized variant (/es/trial/, /in/trial/,
/ar/trial/, etc.).

Why: posts written before 2026-04-16 hardcoded https://globalhighlevel.com/trial
regardless of post language. After localized landing pages shipped, non-EN readers
clicking those CTAs still landed on English pages. This script fixes the backlog.

Idempotent: skips any URL already localized. Safe to re-run.

Usage:
  venv/bin/python3 scripts/localize_cta_retrofit.py --dry   # show counts, no writes
  venv/bin/python3 scripts/localize_cta_retrofit.py         # apply + save
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SITE_POSTS = Path("/opt/globalhighlevel-site/posts") if Path("/opt/globalhighlevel-site/posts").exists() else BASE_DIR.parent / "globalhighlevel-site" / "posts"

# language code → URL prefix. All keys lowercase for case-insensitive match.
LANG_PREFIX = {
    "es": "es",
    "ar": "ar",
    "in": "in",
    "en-in": "in",
    "hi": "in",
}


def log(msg: str):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] [CTA-RETROFIT] {msg}", flush=True)


def localize_url(url: str, lang_prefix: str) -> str:
    """Rewrite an English globalhighlevel.com trial/start URL to the localized variant.
    Preserves query strings. Idempotent — doesn't rewrite already-localized URLs."""
    # Already localized? skip
    if re.search(rf'globalhighlevel\.com/{lang_prefix}/(trial|start)', url):
        return url
    # Rewrite patterns: /trial and /start, with or without trailing slash, with or without query
    url = re.sub(
        r'(https?://(?:www\.)?globalhighlevel\.com)/trial(/?)(\?[^"\'\s<>]*)?',
        rf'\1/{lang_prefix}/trial/\3', url
    )
    url = re.sub(
        r'(https?://(?:www\.)?globalhighlevel\.com)/start(/?)(\?[^"\'\s<>]*)?',
        rf'\1/{lang_prefix}/start/\3', url
    )
    return url


def retrofit_post(post_path: Path, dry: bool = False) -> dict:
    """Rewrite trial/start URLs inside one post JSON. Returns summary dict."""
    try:
        post = json.load(open(post_path))
    except Exception as e:
        return {"path": post_path.name, "status": "read-error", "error": str(e)[:200]}

    lang = (post.get("language") or "").strip().lower()
    if lang not in LANG_PREFIX:
        return {"path": post_path.name, "status": "skip-non-target-lang", "lang": lang}

    prefix = LANG_PREFIX[lang]
    html = post.get("html_content", "")
    if not html:
        return {"path": post_path.name, "status": "skip-no-html", "lang": lang}

    # Count replacements by regexing the whole html_content
    def replace_all(html_in: str) -> tuple[str, int]:
        count = 0
        def _sub(m):
            nonlocal count
            count += 1
            return m.group(0).replace("/trial", f"/{prefix}/trial/").replace("//" + prefix + "/trial//", f"/{prefix}/trial/")
        # trial
        before_trial = html_in
        html_in = re.sub(
            rf'(?<![/{prefix}]){re.escape("https://globalhighlevel.com")}/trial(/|\?|[^a-zA-Z0-9_/])',
            rf'https://globalhighlevel.com/{prefix}/trial/\1',
            html_in,
        )
        trial_replaced = html_in.count(f"/{prefix}/trial/") - before_trial.count(f"/{prefix}/trial/")
        # start
        before_start = html_in
        html_in = re.sub(
            rf'(?<![/{prefix}]){re.escape("https://globalhighlevel.com")}/start(/|\?|[^a-zA-Z0-9_/])',
            rf'https://globalhighlevel.com/{prefix}/start/\1',
            html_in,
        )
        start_replaced = html_in.count(f"/{prefix}/start/") - before_start.count(f"/{prefix}/start/")
        # Clean up any double-slash artifacts from regex boundaries
        html_in = html_in.replace(f"/{prefix}/trial//", f"/{prefix}/trial/")
        html_in = html_in.replace(f"/{prefix}/start//", f"/{prefix}/start/")
        return html_in, trial_replaced + start_replaced

    new_html, count = replace_all(html)

    if count == 0:
        return {"path": post_path.name, "status": "no-change", "lang": lang}

    if dry:
        return {"path": post_path.name, "status": "would-update", "lang": lang, "replacements": count}

    post["html_content"] = new_html
    post["_cta_localized_at"] = datetime.now().isoformat()
    with open(post_path, "w") as f:
        json.dump(post, f, indent=2, ensure_ascii=False)
    return {"path": post_path.name, "status": "updated", "lang": lang, "replacements": count}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="Show what would change, no writes")
    args = parser.parse_args()

    if not SITE_POSTS.exists():
        log(f"Posts dir not found: {SITE_POSTS}")
        return

    all_posts = sorted(SITE_POSTS.glob("*.json"))
    log(f"Scanning {len(all_posts)} posts in {SITE_POSTS}")
    if args.dry:
        log("DRY RUN — no writes")

    counts = {"updated": 0, "would-update": 0, "no-change": 0,
              "skip-non-target-lang": 0, "skip-no-html": 0, "read-error": 0}
    by_lang = {"es": 0, "ar": 0, "in": 0}
    total_replacements = 0

    for p in all_posts:
        res = retrofit_post(p, dry=args.dry)
        counts[res["status"]] = counts.get(res["status"], 0) + 1
        if res["status"] in ("updated", "would-update"):
            by_lang[LANG_PREFIX.get(res.get("lang", ""), "?")] = by_lang.get(
                LANG_PREFIX.get(res.get("lang", ""), "?"), 0
            ) + 1
            total_replacements += res.get("replacements", 0)

    print()
    print("═" * 60)
    print(" CTA LOCALIZATION RETROFIT — SUMMARY")
    print("═" * 60)
    print(f"  Total posts scanned: {len(all_posts)}")
    for k, v in counts.items():
        if v:
            print(f"  {k}: {v}")
    print(f"  Total CTA URL replacements: {total_replacements}")
    print(f"  By language: ES={by_lang['es']}, IN={by_lang['in']}, AR={by_lang['ar']}")
    print()
    if not args.dry and counts.get("updated", 0) > 0:
        print(" NEXT: cd ../globalhighlevel-site && python3 build.py && git commit")


if __name__ == "__main__":
    main()
