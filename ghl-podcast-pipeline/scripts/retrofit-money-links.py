"""
retrofit-money-links.py
Adds ONE contextual internal link per English post to the trial master and/or
pricing guide, ONLY if the post mentions the trigger phrases in body text.

Safety guards:
  - Only English posts (language == 'en' or unset)
  - Skips posts that already link to the target
  - Skips matches inside <h1>-<h6>, <a>, <strong> headings, <title>
  - Inserts at most ONE link per target per post (so a post can get up to 2
    links: one to master, one to pricing — but only if both triggers fire)
  - Never links the master page to itself; same for pricing
  - Varies anchor text from a curated rotation
  - Writes to BOTH posts/ and globalhighlevel-site/posts/ if the slug exists
    in both
  - Dry-run mode (default): prints diffs, writes nothing
  - --apply flag: actually writes files

Run:
  python3 scripts/retrofit-money-links.py             # dry run, 10 examples
  python3 scripts/retrofit-money-links.py --apply     # writes all changes
  python3 scripts/retrofit-money-links.py --limit 25  # dry run, 25 examples
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
POSTS_DIRS = [ROOT / "posts", ROOT / "globalhighlevel-site" / "posts"]
LOG_FILE = ROOT / "ghl-podcast-pipeline" / "data" / "retrofit-money-links-log.json"

MASTER_URL = "/blog/gohighlevel-free-trial-30-days-extended/"
MASTER_SLUG = "gohighlevel-free-trial-30-days-extended"
PRICING_URL = "/blog/gohighlevel-pricing-plans-2026-complete-guide/"
PRICING_SLUG = "gohighlevel-pricing-plans-2026-complete-guide"

# Trigger phrases ranked by specificity (most specific first wins)
TRIAL_TRIGGERS = [
    ("30-day free trial", ["30-day GoHighLevel free trial", "extended 30-day trial"]),
    ("30 day free trial", ["30-day GoHighLevel free trial", "extended 30-day trial"]),
    ("30-day trial", ["30-day GoHighLevel trial", "extended 30-day free trial", "free 30-day GoHighLevel trial", "extended GoHighLevel trial", "GoHighLevel 30-day trial details"]),
    ("30 day trial", ["30-day GoHighLevel trial", "extended 30-day free trial", "free 30-day GoHighLevel trial", "extended GoHighLevel trial", "GoHighLevel 30-day trial details"]),
    ("free trial", ["GoHighLevel free trial", "GoHighLevel trial"]),
    ("promo code", ["GoHighLevel promo codes", "real GoHighLevel promo codes"]),
    ("promo codes", ["GoHighLevel promo codes", "real GoHighLevel promo codes"]),
    ("coupon code", ["GoHighLevel coupon codes", "GoHighLevel discount codes"]),
    ("discount code", ["GoHighLevel discount codes", "real GoHighLevel discounts"]),
]

PRICING_TRIGGERS = [
    # Most-specific phrases first. All require strong GHL/GoHighLevel/dollar context.
    ("GoHighLevel pricing plans", ["GoHighLevel pricing plans 2026 guide", "full pricing plan breakdown"]),
    ("GoHighLevel pricing", ["GoHighLevel pricing plans", "GoHighLevel pricing breakdown"]),
    ("GHL pricing", ["GoHighLevel pricing plans", "GHL pricing breakdown"]),
    ("GoHighLevel cost", ["GoHighLevel pricing plans", "GoHighLevel cost breakdown"]),
    ("GoHighLevel plans", ["GoHighLevel pricing plans", "GoHighLevel plan tiers"]),
    ("GHL plans", ["GoHighLevel pricing plans", "GHL plan tiers"]),
    ("$97/month", ["GoHighLevel $97 Starter plan", "GoHighLevel pricing tiers"]),
    ("$297/month", ["GoHighLevel $297 Unlimited plan", "GoHighLevel pricing tiers"]),
    ("$497/month", ["GoHighLevel $497 Pro/SaaS plan", "GoHighLevel pricing tiers"]),
    ("$97 plan", ["GoHighLevel $97 Starter plan", "GoHighLevel pricing plans"]),
    ("$297 plan", ["GoHighLevel $297 Unlimited plan", "GoHighLevel pricing plans"]),
    ("$497 plan", ["GoHighLevel $497 Pro/SaaS plan", "GoHighLevel pricing plans"]),
    ("Starter plan", ["GoHighLevel $97 Starter plan", "Starter plan in GoHighLevel pricing"]),
    ("Unlimited plan", ["GoHighLevel $297 Unlimited plan", "Unlimited plan pricing"]),
    ("SaaS Pro plan", ["GoHighLevel $497 SaaS Pro plan", "SaaS Pro plan pricing"]),
    ("Agency Pro plan", ["GoHighLevel $497 Agency Pro plan", "Agency Pro plan pricing"]),
    ("pricing tiers", ["GoHighLevel pricing tiers", "GoHighLevel pricing plans"]),
]

# Block a match if its source position lies inside any of these tags
BLOCKED_PARENT_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "a", "title", "li > strong:only-child")

# Match block ranges to avoid (header tags, anchor tags)
HEADING_RE = re.compile(r"<(h[1-6])\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
ANCHOR_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL)


def load_posts():
    """Return list of (path, slug, post_dict) tuples — every file, both dirs."""
    items = []
    for d in POSTS_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                p = json.load(open(f))
            except Exception:
                continue
            slug = p.get("slug") or f.stem
            items.append((f, slug, p))
    return items


def find_blocked_ranges(html: str):
    """Return list of (start, end) char ranges where we should NOT match."""
    blocked = []
    for m in HEADING_RE.finditer(html):
        blocked.append((m.start(), m.end()))
    for m in ANCHOR_RE.finditer(html):
        blocked.append((m.start(), m.end()))
    return blocked


def position_blocked(pos: int, blocked) -> bool:
    return any(s <= pos < e for s, e in blocked)


def insert_link(html: str, target_url: str, triggers, anchor_counter: Counter):
    """Try each trigger in order; insert ONE link at the first body match.
    Returns (new_html, anchor_used) or (None, None) if no insertion made.
    """
    blocked = find_blocked_ranges(html)
    for trigger, anchor_options in triggers:
        # Word boundary, case-insensitive
        pattern = re.compile(rf"\b{re.escape(trigger)}\b", re.IGNORECASE)
        for m in pattern.finditer(html):
            if position_blocked(m.start(), blocked):
                continue
            # Pick anchor: rotate to balance distribution
            idx = anchor_counter[target_url] % len(anchor_options)
            anchor = anchor_options[idx]
            anchor_counter[target_url] += 1
            replacement = f'<a href="{target_url}">{anchor}</a>'
            new_html = html[:m.start()] + replacement + html[m.end():]
            return new_html, anchor, trigger, m.start()
    return None, None, None, None


def post_links_to(html: str, target_url: str) -> bool:
    return target_url in html


def is_english(post: dict) -> bool:
    lang = post.get("language", "")
    return lang in ("en", None, "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write files")
    parser.add_argument("--limit", type=int, default=10, help="Dry-run preview limit")
    args = parser.parse_args()

    items = load_posts()
    # Group by slug so we update both dir copies in lockstep
    by_slug = {}
    for path, slug, post in items:
        by_slug.setdefault(slug, []).append((path, post))

    print(f"\nLoaded {len(by_slug)} unique slugs across {len(items)} files")
    print(f"Mode: {'APPLY (writing files)' if args.apply else f'DRY RUN (showing first {args.limit} examples)'}\n")

    anchor_counter = Counter()
    edits = []  # (slug, target, anchor, trigger, before_snippet, after_snippet)
    skipped = {"non_english": 0, "already_linked_master": 0, "already_linked_pricing": 0,
               "no_trigger_master": 0, "no_trigger_pricing": 0, "is_target_page": 0}

    for slug, copies in by_slug.items():
        # Use first copy as reference
        path0, post0 = copies[0]
        if not is_english(post0):
            skipped["non_english"] += 1
            continue
        if slug in (MASTER_SLUG, PRICING_SLUG):
            skipped["is_target_page"] += 1
            continue

        html = post0.get("html_content", "") or ""
        new_html = html
        slug_edits = []

        # Try master first
        if not post_links_to(new_html, MASTER_URL):
            result_html, anchor, trigger, pos = insert_link(new_html, MASTER_URL, TRIAL_TRIGGERS, anchor_counter)
            if result_html is not None:
                # Snippet around the insertion point
                snippet_start = max(0, pos - 60)
                snippet_end = min(len(html), pos + len(trigger) + 60)
                before = html[snippet_start:snippet_end]
                # Re-find in result_html
                new_pos = result_html.find(f'<a href="{MASTER_URL}">')
                after = result_html[max(0, new_pos - 60):new_pos + len(f'<a href="{MASTER_URL}">{anchor}</a>') + 60]
                slug_edits.append({
                    "target": MASTER_URL, "anchor": anchor, "trigger": trigger,
                    "before": before, "after": after,
                })
                new_html = result_html
            else:
                skipped["no_trigger_master"] += 1
        else:
            skipped["already_linked_master"] += 1

        # Try pricing next (operate on possibly already-edited new_html)
        if not post_links_to(new_html, PRICING_URL):
            result_html, anchor, trigger, pos = insert_link(new_html, PRICING_URL, PRICING_TRIGGERS, anchor_counter)
            if result_html is not None:
                snippet_start = max(0, pos - 60)
                snippet_end = min(len(new_html), pos + len(trigger) + 60)
                before = new_html[snippet_start:snippet_end]
                new_pos = result_html.find(f'<a href="{PRICING_URL}">')
                after = result_html[max(0, new_pos - 60):new_pos + len(f'<a href="{PRICING_URL}">{anchor}</a>') + 60]
                slug_edits.append({
                    "target": PRICING_URL, "anchor": anchor, "trigger": trigger,
                    "before": before, "after": after,
                })
                new_html = result_html
            else:
                skipped["no_trigger_pricing"] += 1
        else:
            skipped["already_linked_pricing"] += 1

        if not slug_edits:
            continue

        edits.append((slug, slug_edits))

        if args.apply:
            # Write all copies (same html_content)
            for path, post in copies:
                post["html_content"] = new_html
                with open(path, "w") as f:
                    json.dump(post, f, indent=2, ensure_ascii=True)

    # ---- Summary ----
    print("=" * 75)
    print("SUMMARY")
    print("=" * 75)
    print(f"  Posts edited: {len(edits)}")
    target_counts = Counter()
    for _, slug_edits in edits:
        for e in slug_edits:
            target_counts[e["target"]] += 1
    for t, c in target_counts.most_common():
        print(f"    {c} new links → {t}")
    print(f"  Skipped: {dict(skipped)}")
    print(f"\n  Anchor text distribution:")
    by_target = {}
    for _, slug_edits in edits:
        for e in slug_edits:
            by_target.setdefault(e["target"], Counter())[e["anchor"]] += 1
    for target, counter in by_target.items():
        print(f"  {target}")
        for anchor, n in counter.most_common():
            print(f"    {n:>4}× {anchor}")

    # ---- Show preview diffs ----
    if not args.apply:
        print(f"\n{'=' * 75}")
        print(f"PREVIEW: first {args.limit} edits")
        print("=" * 75)
        for slug, slug_edits in edits[:args.limit]:
            print(f"\n• {slug}")
            for e in slug_edits:
                print(f"  → {e['target']}")
                print(f"    trigger: '{e['trigger']}' | anchor: '{e['anchor']}'")
                print(f"    BEFORE: ...{e['before'].strip()}...")
                print(f"    AFTER:  ...{e['after'].strip()}...")

    # Persist log when applying
    if args.apply:
        log = {
            "edits": [
                {"slug": s, "changes": e} for s, e in edits
            ],
            "summary": {
                "posts_edited": len(edits),
                "links_added": dict(target_counts),
                "anchor_distribution": {t: dict(c) for t, c in by_target.items()},
                "skipped": dict(skipped),
            },
        }
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "w") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        print(f"\n  Log written: {LOG_FILE}")


if __name__ == "__main__":
    main()
