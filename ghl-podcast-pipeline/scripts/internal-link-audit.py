"""
internal-link-audit.py
Counts how many posts link to each internal page in html_content.
Surfaces money pages and shows anchor-text distribution.

Run: python3 scripts/internal-link-audit.py
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
POSTS_DIRS = [ROOT / "posts", ROOT / "globalhighlevel-site" / "posts"]

MONEY_PAGES = {
    "trial_master": "/blog/gohighlevel-free-trial-30-days-extended/",
    "pricing": "/blog/gohighlevel-pricing-plans-2026-complete-guide/",
    "ai_pricing": "/blog/leverage-ai-pricing-updates-gohighlevel-save-more/",
    "trial_attribution": "/trial/",
    "coupon_attribution": "/coupon/",
    "start_attribution": "/start/",
    "promo_old_301": "/blog/gohighlevel-promo-code-discount-2026-real-ways-to-save/",
}

# Match <a href="...">anchor</a> in html_content
LINK_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)


def normalize(href: str) -> str:
    href = href.strip()
    href = href.replace("https://globalhighlevel.com", "")
    # Strip query/fragment for counting
    href = re.split(r"[?#]", href)[0]
    if not href.endswith("/") and "." not in href.split("/")[-1]:
        href += "/"
    return href


def load_posts():
    seen_slugs = set()
    posts = []
    for d in POSTS_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                p = json.load(open(f))
            except Exception:
                continue
            slug = p.get("slug") or f.stem
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            posts.append((slug, p))
    return posts


def main():
    posts = load_posts()
    total = len(posts)
    print(f"\nLoaded {total} unique posts (deduped across {len(POSTS_DIRS)} dirs)\n")

    # Counter: target_url -> count of posts linking to it
    inbound = Counter()
    # target_url -> list of anchor texts
    anchors = defaultdict(list)
    # target_url -> set of source slugs
    sources = defaultdict(set)

    for slug, p in posts:
        html = p.get("html_content", "") or ""
        for m in LINK_RE.finditer(html):
            href, anchor = m.group(1), m.group(2)
            href = normalize(href)
            # Skip external, hashes, mailto
            if href.startswith(("http", "mailto", "#", "tel:")):
                continue
            # Strip HTML inside anchor
            anchor_text = re.sub(r"<[^>]+>", "", anchor).strip()
            inbound[href] += 1
            sources[href].add(slug)
            if anchor_text:
                anchors[href].append(anchor_text.lower())

    # ---- Money pages report ----
    print("=" * 75)
    print("MONEY PAGE INTERNAL LINK COUNTS")
    print("=" * 75)
    print(f"{'PAGE':<60} {'INBOUND':>8} {'% POSTS':>8}")
    for label, url in MONEY_PAGES.items():
        c = inbound.get(url, 0)
        pct = c / total * 100
        flag = ""
        if "_attribution" in label or "old_301" in label:
            flag = "  ← should be 0 (301'd / robots-blocked)"
        print(f"{url:<60} {c:>8} {pct:>7.1f}%{flag}")

    # ---- Top 20 most-linked pages ----
    print(f"\n{'=' * 75}")
    print("TOP 20 MOST INTERNALLY-LINKED PAGES")
    print("=" * 75)
    print(f"{'PAGE':<60} {'INBOUND':>8} {'% POSTS':>8}")
    for url, c in inbound.most_common(20):
        u = url if len(url) < 60 else url[:57] + "..."
        print(f"{u:<60} {c:>8} {c/total*100:>7.1f}%")

    # ---- Anchor text distribution for master ----
    master = MONEY_PAGES["trial_master"]
    pricing = MONEY_PAGES["pricing"]
    print(f"\n{'=' * 75}")
    print(f"ANCHOR TEXT DISTRIBUTION — TRIAL MASTER  ({inbound.get(master, 0)} links)")
    print("=" * 75)
    a_master = Counter(anchors.get(master, []))
    for anchor, n in a_master.most_common(10):
        a = anchor if len(anchor) < 65 else anchor[:62] + "..."
        print(f"  {n:>4}× {a}")

    print(f"\n{'=' * 75}")
    print(f"ANCHOR TEXT DISTRIBUTION — PRICING GUIDE  ({inbound.get(pricing, 0)} links)")
    print("=" * 75)
    a_pricing = Counter(anchors.get(pricing, []))
    for anchor, n in a_pricing.most_common(10):
        a = anchor if len(anchor) < 65 else anchor[:62] + "..."
        print(f"  {n:>4}× {a}")

    # ---- Posts that mention trial/promo/discount but DON'T link to master ----
    miss_keywords = ["free trial", "30-day trial", "30 day trial", "promo code", "discount", "coupon"]
    candidates = []
    for slug, p in posts:
        html_l = (p.get("html_content", "") or "").lower()
        if any(k in html_l for k in miss_keywords):
            if slug not in sources.get(master, set()):
                # Only count English posts (master is English)
                if p.get("language", "en") in ("en", None, ""):
                    candidates.append(slug)

    print(f"\n{'=' * 75}")
    print(f"GAP: English posts mentioning trial/promo/discount that DO NOT link to master")
    print("=" * 75)
    print(f"  Found: {len(candidates)} posts")
    print(f"  (Showing first 15)")
    for s in candidates[:15]:
        print(f"  - {s}")

    # ---- Same gap, for pricing ----
    pricing_keywords = ["pricing", "price", "cost", "plan", "$97", "$297", "$497"]
    candidates_p = []
    for slug, p in posts:
        html_l = (p.get("html_content", "") or "").lower()
        if any(k in html_l for k in pricing_keywords):
            if slug not in sources.get(pricing, set()):
                if p.get("language", "en") in ("en", None, ""):
                    candidates_p.append(slug)

    print(f"\n{'=' * 75}")
    print(f"GAP: English posts mentioning pricing/cost/plans that DO NOT link to pricing guide")
    print("=" * 75)
    print(f"  Found: {len(candidates_p)} posts")
    print(f"  (Showing first 15)")
    for s in candidates_p[:15]:
        print(f"  - {s}")


if __name__ == "__main__":
    main()
