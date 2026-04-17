#!/usr/bin/env python3
"""Consolidate N pages into 1 canonical — merge content, redirect losers, update internal links.

Usage:
    python3 scripts/consolidate.py --canonical SLUG --losers SLUG1,SLUG2,... [--dry-run]

What it does:
1. Extracts unique H2 sections + FAQ entries from each loser
2. Appends them to the canonical post
3. Adds 301 redirects to _redirects
4. Updates internal links across all posts (old slug → canonical)
5. Removes loser JSON files
6. Reports everything it changed
"""
import argparse, json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SITE_POSTS = ROOT / "globalhighlevel-site" / "posts"
PIPE_POSTS = ROOT / "posts"
REDIRECTS  = ROOT / "globalhighlevel-site" / "_redirects"

def load_post(slug: str):
    p = SITE_POSTS / f"{slug}.json"
    if p.exists():
        return json.loads(p.read_text())
    return None

def save_post(slug: str, data: dict):
    for d in [SITE_POSTS, PIPE_POSTS]:
        p = d / f"{slug}.json"
        if p.exists() or d == SITE_POSTS:
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"  ✓ wrote {p.relative_to(ROOT)}")

def extract_h2_sections(html: str) -> list[dict]:
    """Extract H2 sections with their content until the next H2."""
    parts = re.split(r'(<h2[^>]*>)', html)
    sections = []
    for i, part in enumerate(parts):
        if re.match(r'<h2[^>]*>', part) and i + 1 < len(parts):
            heading = re.sub(r'<[^>]+>', '', part + parts[i+1].split('</h2>')[0]).strip()
            body = parts[i+1].split('</h2>', 1)[-1] if '</h2>' in parts[i+1] else parts[i+1]
            sections.append({"heading": heading, "html": part + parts[i+1]})
    return sections

def extract_faq_items(html: str) -> list[tuple[str, str]]:
    """Extract FAQ Q&A pairs from <h3>Q</h3><p>A</p> patterns."""
    pairs = re.findall(r'<h3[^>]*>(.*?)</h3>\s*<p>(.*?)</p>', html, re.DOTALL)
    return [(re.sub(r'<[^>]+>','',q).strip(), re.sub(r'<[^>]+>','',a).strip()) for q, a in pairs]

def update_internal_links(old_slug: str, canonical_slug: str, dry_run: bool) -> int:
    """Replace all internal links to old_slug with canonical_slug across all posts."""
    count = 0
    old_patterns = [f'/blog/{old_slug}/', f'"/blog/{old_slug}/"', f"'/blog/{old_slug}/'"]
    for posts_dir in [SITE_POSTS, PIPE_POSTS]:
        if not posts_dir.exists():
            continue
        for f in posts_dir.glob("*.json"):
            text = f.read_text()
            if f'/blog/{old_slug}/' in text:
                if not dry_run:
                    text = text.replace(f'/blog/{old_slug}/', f'/blog/{canonical_slug}/')
                    f.write_text(text)
                count += 1
                print(f"    {'would update' if dry_run else 'updated'} link in {f.name}")
    return count

def main():
    parser = argparse.ArgumentParser(description="Consolidate N pages into 1 canonical")
    parser.add_argument("--canonical", required=True, help="Slug of the winning page")
    parser.add_argument("--losers", required=True, help="Comma-separated slugs to merge and redirect")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without changing files")
    args = parser.parse_args()

    canonical_slug = args.canonical
    loser_slugs = [s.strip() for s in args.losers.split(",") if s.strip()]
    dry_run = args.dry_run

    print(f"\n{'DRY RUN — ' if dry_run else ''}Consolidating {len(loser_slugs)} pages → {canonical_slug}\n")

    # Load canonical
    canonical = load_post(canonical_slug)
    if not canonical:
        print(f"  ✗ canonical post not found: {canonical_slug}")
        sys.exit(1)

    canonical_body = canonical.get("html_content") or canonical.get("body") or ""
    canonical_h2s = {s["heading"].lower() for s in extract_h2_sections(canonical_body)}
    canonical_faqs = {q.lower() for q, a in extract_faq_items(canonical_body)}

    merged_sections = []
    merged_faqs = []
    total_links_updated = 0

    # Process each loser
    for slug in loser_slugs:
        post = load_post(slug)
        if not post:
            print(f"  ⚠ not found: {slug}")
            continue

        body = post.get("html_content") or post.get("body") or ""

        # Extract unique H2 sections
        for section in extract_h2_sections(body):
            if section["heading"].lower() not in canonical_h2s:
                merged_sections.append(section)
                canonical_h2s.add(section["heading"].lower())
                print(f"  + unique section from {slug[:40]}: \"{section['heading'][:50]}\"")

        # Extract unique FAQ entries
        for q, a in extract_faq_items(body):
            if q.lower() not in canonical_faqs:
                merged_faqs.append((q, a))
                canonical_faqs.add(q.lower())
                print(f"  + unique FAQ from {slug[:40]}: \"{q[:50]}\"")

        # Update internal links
        link_count = update_internal_links(slug, canonical_slug, dry_run)
        total_links_updated += link_count

        # Delete loser files
        if not dry_run:
            for d in [SITE_POSTS, PIPE_POSTS]:
                p = d / f"{slug}.json"
                if p.exists():
                    p.unlink()
                    print(f"  ✗ deleted {p.relative_to(ROOT)}")

    # Append merged content to canonical
    if merged_sections or merged_faqs:
        additions = ""
        if merged_sections:
            additions += "\n\n<!-- Merged from consolidated pages -->\n"
            additions += "\n".join(s["html"] for s in merged_sections)
        if merged_faqs:
            faq_html = "\n".join(
                f'  <div class="faq-item">\n    <h3>{q}</h3>\n    <p>{a}</p>\n  </div>'
                for q, a in merged_faqs
            )
            additions += f"\n\n<h2>Preguntas Adicionales</h2>\n{faq_html}"

        body_key = "html_content" if "html_content" in canonical else "body"
        canonical[body_key] = canonical_body + additions

        if not dry_run:
            save_post(canonical_slug, canonical)

    # Add 301 redirects
    redirect_lines = [f"/blog/{slug}/ /blog/{canonical_slug}/ 301" for slug in loser_slugs]
    if not dry_run:
        existing = REDIRECTS.read_text() if REDIRECTS.exists() else ""
        REDIRECTS.write_text(existing.rstrip() + "\n" + "\n".join(redirect_lines) + "\n")
        print(f"\n  ✓ added {len(redirect_lines)} redirects to _redirects")

    # Summary
    print(f"\n{'DRY RUN ' if dry_run else ''}SUMMARY:")
    print(f"  Canonical: {canonical_slug}")
    print(f"  Losers merged: {len(loser_slugs)}")
    print(f"  Unique sections added: {len(merged_sections)}")
    print(f"  Unique FAQs added: {len(merged_faqs)}")
    print(f"  Internal links updated: {total_links_updated}")
    print(f"  301 redirects added: {len(redirect_lines)}")

if __name__ == "__main__":
    main()
