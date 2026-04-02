"""
build.py — Static site generator for globalhighlevel.com

Reads:
  - posts/*.json         (blog post HTML + metadata, saved by 5-blog.py)
  - ../ghl-podcast-pipeline/data/published.json  (episode metadata)

Generates:
  - public/index.html                      homepage
  - public/blog/{slug}/index.html          individual posts
  - public/category/{slug}/index.html      category pages
  - public/sitemap.xml                     sitemap
  - public/404.html                        404 page
"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR       = Path(__file__).parent
POSTS_DIR      = BASE_DIR / "posts"
PUBLIC_DIR     = BASE_DIR / "public"
PUBLISHED_JSON = BASE_DIR / ".." / "ghl-podcast-pipeline" / "data" / "published.json"
CATEGORIES_JSON = BASE_DIR / "categories.json"

SITE_URL     = os.getenv("SITE_URL", "https://globalhighlevel.com")
SITE_NAME    = os.getenv("SITE_NAME", "Global High Level")
SITE_TAGLINE = os.getenv("SITE_TAGLINE", "GoHighLevel Tutorials, Guides & Strategies for Agencies Worldwide")
AFFILIATE    = os.getenv("GHL_AFFILIATE_LINK", "https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12&utm_source=globalhighlevel&utm_medium=website")

GA_ID        = "G-HYT0YKNGX2"
ACCENT       = "#f59e0b"   # amber
ACCENT_DARK  = "#d97706"

# Module-level categories — loaded in main()
CATEGORIES = []

# ── Helpers ───────────────────────────────────────────────────────────────────

# Categories that bleed through from CMS and mean nothing to readers
_BAD_CATS = {"home", "uncategorized", "blog", "general", ""}

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "", text.lower().replace(" ", "-"))
    return re.sub(r"-{2,}", "-", slug).strip("-")

def fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso[:19]).strftime("%B %d, %Y")
    except Exception:
        return ""

def truncate(text: str, n: int = 160) -> str:
    return text[:n].rsplit(" ", 1)[0] + "…" if len(text) > n else text

def display_cat(cat: str) -> str:
    """Return category label for display, or empty string if it's a CMS artifact."""
    if not cat or cat.strip().lower() in _BAD_CATS:
        return ""
    return cat.strip()

def read_time(html: str) -> str:
    """Estimate read time from HTML content word count."""
    words = len(re.sub(r"<[^>]+>", " ", html).split())
    mins = max(1, round(words / 200))
    return f"{mins} min read"

def extract_toc(html: str) -> list:
    """Extract (anchor_id, label) from H2 tags for table of contents."""
    items = []
    for m in re.finditer(r'<h2[^>]*id=["\']([^"\']+)["\'][^>]*>(.*?)</h2>', html, re.DOTALL):
        anchor = m.group(1)
        label  = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if label:
            items.append((anchor, label))
    if not items:
        for m in re.finditer(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL):
            label  = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            anchor = slugify(label)
            if label:
                items.append((anchor, label))
    return items[:8]

def inject_inline_ctas(html: str, cta_mid: str) -> str:
    """Inject one inline CTA at roughly the 50% H2 boundary."""
    h2_positions = [m.start() for m in re.finditer(r'<h2', html)]
    n = len(h2_positions)
    if n < 2:
        return html
    mid = h2_positions[n // 2]
    return html[:mid] + cta_mid + html[mid:]

def get_related(post: dict, all_posts: list, n: int = 3) -> list:
    """Return n related posts — same category first, then most recent."""
    slug = post.get("slug", "")
    cat  = post.get("category", "")
    same = [p for p in all_posts if p.get("slug") != slug and p.get("category") == cat]
    other = [p for p in all_posts if p.get("slug") != slug and p.get("category") != cat]
    return (same + other)[:n]


def _build_link_index(all_posts: list) -> list[tuple[str, str, str, list[str]]]:
    """Build an index of (slug, title, category, keywords) for internal linking.
    Keywords are extracted from the title — split into meaningful phrases."""
    index = []
    stop = {"in", "the", "a", "an", "to", "for", "of", "and", "or", "how",
            "is", "it", "on", "at", "by", "with", "your", "you", "this",
            "that", "from", "its", "are", "be", "do", "was", "has", "can",
            "my", "our", "all", "no", "not", "what", "why", "when", "use",
            "set", "up", "get", "go", "new", "vs", "best", "top", "way"}
    for p in all_posts:
        title = p.get("title", p.get("seoTitle", ""))
        slug = p.get("slug", "")
        cat = p.get("category", "")
        if not title or not slug:
            continue
        # Extract 2-4 word phrases from title as linkable keywords
        words = re.sub(r"[^a-z0-9\s]", " ", title.lower()).split()
        meaningful = [w for w in words if w not in stop and len(w) > 2]
        phrases = []
        # Single important words (4+ chars)
        for w in meaningful:
            if len(w) >= 5:
                phrases.append(w)
        # Bigrams from meaningful words
        for i in range(len(meaningful) - 1):
            phrases.append(f"{meaningful[i]} {meaningful[i+1]}")
        index.append((slug, title, cat, phrases))
    return index


def inject_internal_links(html: str, post: dict, all_posts: list, max_links: int = 5) -> str:
    """Inject contextual internal links into post body.

    Scans paragraphs for keyword matches against other posts.
    Links are added as natural in-text hyperlinks, max one link per paragraph,
    max max_links total per post. Same-category posts preferred."""
    if not all_posts:
        return html

    slug = post.get("slug", "")
    cat = post.get("category", "")
    link_index = _build_link_index(all_posts)

    # Score candidates: same category gets a boost
    candidates = []
    for s, title, c, phrases in link_index:
        if s == slug:
            continue
        score = 2 if c == cat else 1
        candidates.append((s, title, c, phrases, score))

    # Shuffle within score tiers so we don't always link the same posts
    import random
    rng = random.Random(slug)  # deterministic per post
    rng.shuffle(candidates)
    candidates.sort(key=lambda x: x[4], reverse=True)

    # Find paragraphs and inject links
    linked_slugs = set()
    links_added = 0
    parts = re.split(r'(<p[^>]*>.*?</p>)', html, flags=re.DOTALL)

    for i, part in enumerate(parts):
        if links_added >= max_links:
            break
        if not part.startswith('<p'):
            continue
        # Skip short paragraphs and paragraphs that already have links
        text_only = re.sub(r'<[^>]+>', '', part)
        if len(text_only) < 80 or '<a ' in part:
            continue

        text_lower = text_only.lower()
        for c_slug, c_title, c_cat, c_phrases, c_score in candidates:
            if c_slug in linked_slugs:
                continue
            # Find the best matching phrase in this paragraph
            best_match = None
            best_len = 0
            for phrase in c_phrases:
                if phrase in text_lower and len(phrase) > best_len:
                    # Find the actual-case version in the text
                    idx = text_lower.find(phrase)
                    if idx >= 0:
                        best_match = phrase
                        best_len = len(phrase)

            if best_match and best_len >= 5:
                # Find the match position in the original HTML paragraph
                idx = part.lower().find(best_match)
                if idx < 0:
                    continue
                # Make sure we're not inside an HTML tag
                before = part[:idx]
                if before.count('<') > before.count('>'):
                    continue
                original_text = part[idx:idx + len(best_match)]
                link = f'<a href="/blog/{c_slug}/">{original_text}</a>'
                parts[i] = part[:idx] + link + part[idx + len(best_match):]
                linked_slugs.add(c_slug)
                links_added += 1
                break  # one link per paragraph

    return "".join(parts)

def load_categories() -> list[dict]:
    """Load category definitions from categories.json."""
    if CATEGORIES_JSON.exists():
        return json.loads(CATEGORIES_JSON.read_text())
    return []

def write(path: Path, html: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print(f"  ✓ {path.relative_to(PUBLIC_DIR)}")

def sanitize_content(html: str) -> str:
    """Strip problematic inline elements from blog HTML before rendering.

    Removes:
    - In-content TOC blocks (divs with lists of #section-N anchor links)
    - In-content CTA boxes (blue-themed centered divs with affiliate links)
    """
    # Remove in-content TOC blocks: divs with light background containing
    # a heading/label + a list of #section-N anchor links
    html = re.sub(
        r'<div[^>]*style="[^"]*background:#f0f4ff[^"]*"[^>]*>.*?</div>',
        '',
        html,
        flags=re.DOTALL
    )

    # Remove in-content CTA boxes: solid blue background divs
    html = re.sub(
        r'<div[^>]*style="[^"]*background:#1a73e8[^"]*"[^>]*>.*?</div>',
        '',
        html,
        flags=re.DOTALL
    )

    # Remove bottom CTA boxes: light border/background with centered trial links
    html = re.sub(
        r'<div[^>]*style="[^"]*background:#f0f4ff[^"]*text-align:center[^"]*"[^>]*>.*?</div>',
        '',
        html,
        flags=re.DOTALL
    )
    html = re.sub(
        r'<div[^>]*style="[^"]*text-align:center[^"]*background:#f0f4ff[^"]*"[^>]*>.*?</div>',
        '',
        html,
        flags=re.DOTALL
    )

    return html

# ── CSS — TechCrunch-style editorial layout ──────────────────────────────────

CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,700;0,9..40,800;1,9..40,400&display=swap');

:root{{
  --bg:#07080a;
  --bg2:#0c0e14;
  --surface:#111520;
  --amber:#f59e0b;
  --amber-light:#fbbf24;
  --amber-dim:rgba(245,158,11,0.12);
  --amber-border:rgba(245,158,11,0.22);
  --text:#eef2ff;
  --text2:#a0aec8;
  --text3:#6b7ea8;
  --border:rgba(255,255,255,0.06);
  --max:1120px;
  --content:665px;
  --sans:'DM Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{font-family:var(--sans);font-size:16px;line-height:1.7;color:var(--text);background:var(--bg);overflow-x:hidden;-webkit-font-smoothing:antialiased}}
a{{color:var(--amber);text-decoration:none}}
a:hover{{text-decoration:underline}}
img{{max-width:100%;height:auto}}

/* ANIMATIONS */
@keyframes fadeUp{{from{{opacity:0;transform:translateY(20px)}}to{{opacity:1;transform:translateY(0)}}}}
.fade-1{{animation:fadeUp .6s ease both}}
.fade-2{{animation:fadeUp .6s .15s ease both}}
.fade-3{{animation:fadeUp .6s .3s ease both}}

/* ── NAV — fixed, backdrop blur, animated underlines ──────────────────────── */
nav{{position:fixed;top:0;inset-x:0;z-index:200;background:rgba(7,8,10,0.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid var(--border)}}
.nav-inner{{max-width:var(--max);margin:0 auto;padding:0 24px;height:56px;display:flex;align-items:center;justify-content:space-between}}
.logo{{font-family:var(--sans);font-size:1.15rem;font-weight:800;letter-spacing:-.3px;display:flex;align-items:center;gap:0;color:var(--text)}}
.logo-amber{{color:var(--amber)}}
.nav-links{{display:flex;align-items:center;gap:24px}}
.nav-link{{font-size:.82rem;font-weight:500;color:var(--text2);letter-spacing:.1px;transition:color .15s;position:relative;padding:4px 0}}
.nav-link::after{{content:'';position:absolute;bottom:0;left:0;width:0;height:2px;background:var(--amber);transition:width .2s ease-in-out}}
.nav-link:hover{{color:var(--text);text-decoration:none}}
.nav-link:hover::after{{width:100%}}
.nav-cta{{font-size:.8rem;font-weight:700;color:#000;background:var(--amber);padding:7px 16px;border-radius:100px;transition:background .15s}}
.nav-cta:hover{{background:var(--amber-light);text-decoration:none}}

/* ── HAMBURGER MENU ──────────────────────────────────────────────────────── */
.hamburger{{display:none;flex-direction:column;gap:5px;cursor:pointer;padding:8px;margin-left:auto;z-index:301}}
.hamburger span{{display:block;width:22px;height:2px;background:var(--text);border-radius:2px;transition:all .3s ease}}
.mobile-menu{{display:none;position:fixed;top:56px;inset-x:0;background:var(--bg);border-bottom:1px solid var(--border);padding:16px 24px 24px;z-index:199;flex-direction:column;gap:0}}
.mobile-menu a{{display:block;padding:12px 0;font-size:.95rem;font-weight:500;color:var(--text2);border-bottom:1px solid var(--border);transition:color .15s}}
.mobile-menu a:last-child{{border-bottom:none}}
.mobile-menu a:hover{{color:var(--text);text-decoration:none}}
.mobile-menu .nav-cta{{display:block;text-align:center;margin-top:16px;padding:12px;border-radius:8px;border-bottom:none;color:#000}}
#mobile-toggle{{display:none}}
#mobile-toggle:checked ~ .mobile-menu{{display:flex}}
#mobile-toggle:checked ~ .hamburger span:nth-child(1){{transform:rotate(45deg) translate(5px,5px)}}
#mobile-toggle:checked ~ .hamburger span:nth-child(2){{opacity:0}}
#mobile-toggle:checked ~ .hamburger span:nth-child(3){{transform:rotate(-45deg) translate(5px,-5px)}}

.nav-dropdown{{position:relative}}
.nav-dropdown-menu{{display:none;position:absolute;top:100%;left:-12px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px 0;min-width:220px;z-index:300;box-shadow:0 8px 24px rgba(0,0,0,.5);padding-top:16px}}
.nav-dropdown-menu::before{{content:'';position:absolute;top:-8px;left:0;right:0;height:16px}}
.nav-dropdown:hover .nav-dropdown-menu{{display:block}}
.nav-dropdown-menu a{{display:block;padding:8px 20px;font-size:.82rem;color:var(--text2);transition:color .15s,background .15s}}
.nav-dropdown-menu a:hover{{color:var(--text);background:rgba(255,255,255,.05);text-decoration:none}}

/* ── CONTAINER ────────────────────────────────────────────────────────────── */
.container{{max-width:var(--max);margin:0 auto;padding:0 24px}}

/* ── SECTION LABELS ───────────────────────────────────────────────────────── */
.section-label{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--amber);margin-bottom:16px;padding-bottom:10px;border-bottom:2px solid var(--amber);display:inline-block}}

/* ── HOMEPAGE — Featured + stack ──────────────────────────────────────────── */
.hp-featured{{display:grid;grid-template-columns:1.5fr 1fr;gap:32px;padding:88px 0 48px;border-bottom:1px solid var(--border)}}
.hp-lead{{display:flex;flex-direction:column;justify-content:center}}
.hp-lead-cat{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--amber);margin-bottom:12px}}
.hp-lead-title{{font-family:var(--sans);font-size:clamp(2rem,4vw,3.5rem);font-weight:800;line-height:1.15;color:var(--text);margin-bottom:14px;letter-spacing:-.5px}}
.hp-lead-title a{{color:var(--text);transition:color .2s}}
.hp-lead-title a:hover{{color:var(--amber);text-decoration:none}}
.hp-lead-desc{{font-size:1rem;color:var(--text2);line-height:1.65;margin-bottom:16px}}
.hp-lead-meta{{font-size:13px;color:var(--text3);letter-spacing:.2px}}
.hp-stack{{display:flex;flex-direction:column;gap:0}}
.hp-stack-item{{padding:20px 0;border-bottom:1px solid var(--border)}}
.hp-stack-item:first-child{{padding-top:0}}
.hp-stack-item:last-child{{border-bottom:none}}
.hp-stack-cat{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--amber);margin-bottom:6px}}
.hp-stack-title{{font-family:var(--sans);font-size:1rem;font-weight:700;line-height:1.35;margin-bottom:6px}}
.hp-stack-title a{{color:var(--text);transition:color .15s}}
.hp-stack-title a:hover{{color:var(--amber);text-decoration:none}}
.hp-stack-meta{{font-size:12px;color:var(--text3)}}

/* ── HOMEPAGE — Main grid + sidebar ───────────────────────────────────────── */
.hp-body{{display:grid;grid-template-columns:1fr 320px;gap:48px;padding:48px 0 80px}}
.hp-articles{{display:flex;flex-direction:column;gap:0}}

/* ── FLAT EDITORIAL CARDS (article list items) ────────────────────────────── */
.card{{padding:24px 0;border-bottom:1px solid var(--border);display:flex;flex-direction:column}}
.card-cat{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--amber);margin-bottom:8px;text-decoration:none;display:inline-block}}
a.card-cat:hover{{color:var(--amber-light);text-decoration:none}}
.card-title{{font-family:var(--sans);font-size:1.1rem;font-weight:700;line-height:1.35;margin-bottom:8px}}
.card-title a{{color:var(--text);transition:color .15s}}
.card-title a:hover{{color:var(--amber);text-decoration:none}}
.card-excerpt{{font-size:.9rem;color:var(--text2);line-height:1.55;margin-bottom:12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-meta{{font-size:12px;color:var(--text3);display:flex;align-items:center;gap:6px;flex-wrap:wrap}}
.meta-sep{{color:var(--text3)}}
.podcast-badge{{display:inline-flex;align-items:center;gap:4px;background:var(--amber-dim);color:var(--amber);font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;margin-left:auto}}

/* ── HOMEPAGE SIDEBAR ─────────────────────────────────────────────────────── */
.hp-sidebar{{position:sticky;top:72px;align-self:start}}
.sidebar-section{{margin-bottom:36px}}
.sidebar-section .section-label{{font-size:11px;margin-bottom:12px;padding-bottom:8px}}
.sidebar-trending{{display:flex;flex-direction:column;gap:0}}
.trending-item{{padding:12px 0;border-bottom:1px solid var(--border);display:flex;gap:10px;align-items:flex-start}}
.trending-item:last-child{{border-bottom:none}}
.trending-num{{font-family:var(--sans);font-size:1.3rem;font-weight:800;color:rgba(245,158,11,.3);line-height:1;min-width:24px}}
.trending-title{{font-size:.85rem;font-weight:600;line-height:1.35}}
.trending-title a{{color:var(--text2);transition:color .15s}}
.trending-title a:hover{{color:var(--text);text-decoration:none}}
.sidebar-podcast{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:24px}}
.sidebar-podcast p{{font-size:.85rem;color:var(--text2);margin-bottom:12px;line-height:1.5}}
.btn-spotify{{display:inline-flex;align-items:center;gap:6px;background:#1DB954;color:#000;font-size:.8rem;font-weight:700;padding:8px 16px;border-radius:6px;transition:opacity .15s}}
.btn-spotify:hover{{opacity:.88;text-decoration:none}}
.sidebar-cta{{background:var(--surface);border:1px solid var(--amber-border);border-radius:8px;padding:20px;text-align:center}}
.sidebar-cta .s-headline{{font-size:.9rem;font-weight:700;color:var(--text);margin-bottom:6px}}
.sidebar-cta .s-sub{{font-size:.8rem;color:var(--text2);margin-bottom:14px;line-height:1.5}}
.sidebar-cta .s-fine{{font-size:.7rem;color:var(--text3);margin-top:10px}}
.sidebar-cat-link{{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:.85rem;color:var(--text2);transition:color .15s}}
.sidebar-cat-link:last-child{{border-bottom:none}}
.sidebar-cat-link:hover{{color:var(--text);text-decoration:none}}
.sidebar-cat-count{{font-size:.75rem;color:var(--text3);background:rgba(255,255,255,.04);padding:2px 8px;border-radius:12px}}

/* ── Cards grid (for category pages) ──────────────────────────────────────── */
.cards-grid{{display:flex;flex-direction:column;gap:0}}

/* ── Reading progress bar ─────────────────────────────────────────────────── */
#reading-progress{{position:fixed;top:0;left:0;height:3px;width:0;background:var(--amber);z-index:9999;transition:width .1s linear}}

/* ── POST PAGE — single-column centered ───────────────────────────────────── */
.post-container{{max-width:var(--content);margin:0 auto;padding:100px 24px 48px}}

/* Breadcrumb */
.post-breadcrumb{{font-size:.8rem;color:var(--text3);margin-bottom:24px}}
.post-breadcrumb a{{color:var(--text2);transition:color .15s}}
.post-breadcrumb a:hover{{color:var(--text);text-decoration:none}}
.post-breadcrumb .bc-sep{{margin:0 8px;color:var(--text3);opacity:.5}}

/* Post header */
.post-eyebrow{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--amber);margin-bottom:12px}}
.post-title{{font-family:var(--sans);font-size:clamp(2rem,4vw,3.5rem);font-weight:800;line-height:1.15;color:var(--text);letter-spacing:-.5px;margin-bottom:20px}}
.post-byline{{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--text3);padding-bottom:16px;border-bottom:1px solid var(--border);margin-bottom:8px;flex-wrap:wrap}}
.post-byline .sep{{color:var(--text3);opacity:.4}}

/* Share row */
.share-row{{display:flex;align-items:center;gap:12px;padding:12px 0 28px;border-bottom:1px solid var(--border);margin-bottom:32px;font-size:13px;color:var(--text3)}}
.share-btn{{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border:1px solid var(--border);border-radius:6px;font-size:12px;font-weight:600;color:var(--text2);background:transparent;cursor:pointer;transition:border-color .15s,color .15s}}
.share-btn:hover{{border-color:var(--amber);color:var(--text);text-decoration:none}}

/* CTA — below byline (compact one-liner) */
.cta-byline{{font-size:.9rem;color:var(--text2);margin:0 0 32px;padding:12px 0}}
.cta-byline a{{color:var(--amber);font-weight:600}}
.cta-byline a:hover{{color:var(--amber-light)}}

/* CTA — mid-article inline */
.cta-inline{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px 18px;margin:28px 0;font-size:.9rem;color:var(--text2);display:block}}
.cta-inline a{{color:var(--amber);font-weight:600;text-decoration:none}}
.cta-inline a:hover{{color:var(--amber-light)}}

/* CTA — end of article box */
.cta-end{{background:var(--surface);border:1px solid var(--amber-border);border-radius:10px;padding:32px;text-align:center;margin:48px 0}}
.cta-end h3{{font-family:var(--sans);font-size:1.25rem;font-weight:800;color:var(--text);margin-bottom:10px}}
.cta-end p{{font-size:.9rem;color:var(--text2);margin:0 0 20px;max-width:440px;margin-left:auto;margin-right:auto}}
.cta-end .fine{{font-size:.75rem;color:var(--text3);margin-top:12px}}
.btn-amber{{display:inline-flex;align-items:center;gap:8px;background:var(--amber);color:#000;font-size:.85rem;font-weight:700;padding:11px 22px;border-radius:6px;transition:all .2s;text-decoration:none}}
.btn-amber:hover{{background:var(--amber-light);transform:translateY(-1px);text-decoration:none}}

/* Post body typography */
.post-body{{font-size:19px;line-height:1.75;color:#e5e7eb}}
.post-body h2{{font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin:48px 0 14px}}
.post-body h3{{font-size:1.15rem;font-weight:700;color:#f3f4f6;margin:32px 0 10px}}
.post-body p{{margin-bottom:20px}}
.post-body ul,.post-body ol{{margin:0 0 20px 24px}}
.post-body li{{margin-bottom:8px}}
.post-body strong{{color:#fff}}
.post-body a{{color:var(--amber);text-decoration:underline;text-underline-offset:3px}}
.post-body a:hover{{color:var(--amber-light)}}

/* ── LIGHT-MODE INLINE STYLE OVERRIDES ────────────────────────────────────── */
.post-body a[style*="color:#1a73e8"],
.post-body a[style*="color: #1a73e8"]{{
  color:var(--amber)!important;
}}
.post-body a[style*="color:#1a73e8"]:hover,
.post-body a[style*="color: #1a73e8"]:hover{{
  color:var(--amber-light)!important;
}}
.post-body div[style*="background:#f0f4ff"],
.post-body div[style*="background: #f0f4ff"]{{
  background:var(--surface)!important;
  border-color:var(--amber-border)!important;
}}
.post-body div[style*="background:#f8f9fa"],
.post-body div[style*="background: #f8f9fa"]{{
  background:var(--surface)!important;
  border-color:var(--border)!important;
}}
.post-body div[style*="background:#fff8e1"],
.post-body div[style*="background: #fff8e1"]{{
  background:rgba(245,158,11,.06)!important;
  border-color:var(--amber-border)!important;
}}
.post-body div[style*="background:#fff"],
.post-body div[style*="background: #fff"],
.post-body div[style*="background:#ffffff"],
.post-body div[style*="background: #ffffff"]{{
  background:var(--surface)!important;
}}
.post-body div[style*="background:#1a73e8"],
.post-body div[style*="background: #1a73e8"]{{
  background:var(--surface)!important;
  border:1px solid var(--amber-border)!important;
}}
.post-body div[style*="background:#1a73e8"] *,
.post-body div[style*="background: #1a73e8"] *{{
  color:var(--text)!important;
}}
.post-body div[style*="background:#1a73e8"] a,
.post-body div[style*="background: #1a73e8"] a{{
  background:var(--amber)!important;
  color:#000!important;
  border-radius:6px;
  padding:12px 24px;
}}
.post-body a[style*="background:#ffffff"],
.post-body a[style*="background: #ffffff"],
.post-body a[style*="background:#fff"],
.post-body a[style*="background: #fff"]{{
  background:var(--amber)!important;
  color:#000!important;
}}
.post-body div[style*="border-left:4px solid #1a73e8"],
.post-body div[style*="border-left: 4px solid #1a73e8"]{{
  border-left-color:var(--amber)!important;
}}
.post-body div[style*="border:2px solid #1a73e8"],
.post-body div[style*="border: 2px solid #1a73e8"]{{
  border-color:var(--amber-border)!important;
}}
.post-body div[style*="border-left:4px solid #ffc107"]{{
  border-left-color:var(--amber)!important;
}}
.post-body div[style*="background:#f8f9fa"] h3,
.post-body div[style*="background: #f8f9fa"] h3{{
  color:var(--amber)!important;
  margin-top:0;
}}
.post-body div[style*="background:#f8f9fa"] h3[style*="color:#1a73e8"],
.post-body div[style*="background: #f8f9fa"] h3[style*="color:#1a73e8"]{{
  color:var(--amber)!important;
}}
.post-body div[style*="background:#f8f9fa"] p,
.post-body div[style*="background: #f8f9fa"] p{{
  color:var(--text2)!important;
}}
.post-body div[style*="background:#f8f9fa"] strong,
.post-body div[style*="background: #f8f9fa"] strong{{
  color:var(--text)!important;
}}
.post-body h2[style*="color:#1a73e8"],
.post-body h3[style*="color:#1a73e8"],
.post-body h4[style*="color:#1a73e8"]{{
  color:var(--amber)!important;
}}
.post-body p[style*="color:#1a73e8"],
.post-body span[style*="color:#1a73e8"],
.post-body p[style*="color:#333"],
.post-body span[style*="color:#333"],
.post-body p[style*="color:#000"],
.post-body span[style*="color:#000"]{{
  color:var(--text2)!important;
}}
.post-body a[style*="background:#1a73e8"],
.post-body a[style*="background: #1a73e8"]{{
  background:var(--amber)!important;
  color:#000!important;
}}
.post-body p[style*="background:#f0fdf4"],
.post-body p[style*="background: #f0fdf4"]{{
  background:var(--surface)!important;
  border-color:var(--amber-border)!important;
  color:var(--text)!important;
}}
.post-body p[style*="background:#f0fdf4"] a,
.post-body p[style*="background: #f0fdf4"] a{{
  color:var(--amber)!important;
}}
.post-body div[style*="border-radius"]{{
  color:var(--text2);
}}

/* TOC */
.toc{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px 24px;margin:0 0 32px}}
.toc-label{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text3);margin-bottom:12px}}
.toc ol{{margin:0;padding-left:18px}}
.toc li{{font-size:.9rem;line-height:1.9}}
.toc a{{color:var(--text2);text-decoration:none}}
.toc a:hover{{color:var(--amber);text-decoration:none}}

/* Podcast embed */
.podcast-embed{{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--amber);border-radius:8px;padding:20px;margin:36px 0}}
.podcast-embed p{{font-size:.8rem;font-weight:600;color:var(--text2);margin-bottom:12px}}
.podcast-embed iframe{{border-radius:6px}}
.podcast-link{{display:inline-flex;align-items:center;gap:8px;color:var(--amber);font-size:.875rem;font-weight:600;text-decoration:none;margin-top:8px}}
.podcast-link:hover{{color:var(--amber-light);text-decoration:none}}

/* Author box */
.author-box{{display:flex;gap:16px;align-items:flex-start;padding:24px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin:40px 0}}
.author-box .author-name{{font-weight:700;color:var(--text);font-size:.95rem;margin-bottom:4px}}
.author-box .author-bio{{font-size:.825rem;color:var(--text2);line-height:1.6}}

/* Related posts */
.related-posts{{margin:48px 0 0}}
.related-label{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text3);margin-bottom:18px}}
.related-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.related-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;text-decoration:none;display:block;transition:border-color .2s}}
.related-card:hover{{border-color:var(--amber);text-decoration:none}}
.related-card .r-tag{{font-size:11px;font-weight:700;color:var(--amber);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}}
.related-card .r-title{{font-size:.85rem;font-weight:600;color:#e5e7eb;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}

/* Pagination */
.pagination{{display:flex;gap:8px;justify-content:center;margin-top:48px;flex-wrap:wrap}}
.page-btn{{padding:8px 16px;border:1px solid var(--border);border-radius:6px;font-size:.875rem;color:var(--text2);background:var(--surface)}}
.page-btn.active{{background:var(--amber);color:#07080a;border-color:var(--amber);font-weight:700}}
.page-btn:hover{{border-color:var(--amber);color:var(--text);text-decoration:none}}

/* Category header */
.cat-header{{background:var(--bg2);border-bottom:1px solid var(--border);padding:100px 24px 40px}}
.cat-header h1{{font-family:var(--sans);font-size:1.8rem;font-weight:800;margin-bottom:8px;color:var(--text)}}
.cat-header p{{color:var(--text2);font-size:.9rem}}

/* Footer */
footer{{border-top:1px solid var(--border);padding:56px 24px 36px;margin-top:80px}}
.footer-inner{{max-width:var(--max);margin:0 auto}}
.footer-top{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:48px;margin-bottom:48px}}
.footer-logo{{font-family:var(--sans);font-size:1.1rem;font-weight:800;margin-bottom:12px;color:var(--text)}}
.footer-logo span{{color:var(--amber)}}
.footer-desc{{font-size:.82rem;color:var(--text3);line-height:1.7;margin-bottom:14px}}
.footer-disclaimer{{font-size:.74rem;color:var(--text3);line-height:1.6;opacity:.7}}
.footer-col h4{{font-size:.76rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--text2);margin-bottom:16px}}
.footer-col a{{display:block;font-size:.85rem;color:var(--text2);margin-bottom:10px;transition:color .15s}}
.footer-col a:hover{{color:var(--text);text-decoration:none}}
.footer-bottom{{border-top:1px solid var(--border);padding-top:24px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-size:.76rem;color:var(--text3)}}

/* ── RESPONSIVE ───────────────────────────────────────────────────────────── */
@media(max-width:1024px){{
  .hp-featured{{grid-template-columns:1fr}}
  .hp-body{{grid-template-columns:1fr}}
  .hp-sidebar{{position:static;display:grid;grid-template-columns:1fr 1fr;gap:24px}}
  .related-grid{{grid-template-columns:repeat(2,1fr)}}
}}
@media(max-width:640px){{
  .hp-sidebar{{grid-template-columns:1fr}}
  .nav-links{{display:none}}
  .hamburger{{display:flex}}
  .post-title{{font-size:1.8rem}}
  .hp-lead-title{{font-size:1.8rem}}
  .cta-end{{padding:24px 20px}}
  .related-grid{{grid-template-columns:1fr}}
  .cat-header{{padding:90px 20px 36px}}
  .footer-top{{grid-template-columns:1fr;gap:32px}}
  .footer-bottom{{flex-direction:column}}
  .share-row{{flex-wrap:wrap}}
  .trial-grid{{grid-template-columns:1fr!important}}
  .coupon-compare{{grid-template-columns:1fr!important}}
  .coupon-features{{grid-template-columns:1fr!important}}
  .services-grid{{grid-template-columns:1fr!important}}
  .services-steps{{grid-template-columns:1fr!important}}
  .services-pricing{{grid-template-columns:1fr!important}}
  .form-row{{grid-template-columns:1fr!important}}
}}
"""

# ── Base template ─────────────────────────────────────────────────────────────

def _ga_snippet() -> str:
    """Return GA4 + CTA click tracking script, or empty string if no GA_ID."""
    if not GA_ID:
        return ""
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>\n'
        f"<script>\n"
        f"window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}\n"
        f'gtag("js",new Date());gtag("config","{GA_ID}");\n'
        f'document.addEventListener("click",function(e){{\n'
        f'  var a=e.target.closest(\'a[href*="gohighlevel.com"],a[href*="/trial/"],a.nav-cta,a.btn-amber\');\n'
        f'  if(a)gtag("event","cta_click",{{\n'
        f"    link_url:a.href,\n"
        f"    link_text:a.textContent.trim().slice(0,50),\n"
        f"    page_path:location.pathname\n"
        f"  }});\n"
        f"}});\n"
        f"</script>"
    )


def base_html(title: str, description: str, canonical: str, body: str, og_image: str = "") -> str:
    og_img = og_image or os.getenv("OG_IMAGE_URL", "")
    cats = CATEGORIES

    # Nav dropdown links
    dropdown_links = ""
    for c in cats:
        dropdown_links += f'    <a href="/category/{c["slug"]}/">{c["name"]}</a>\n'

    # Footer category links (top 4)
    footer_cat_links = ""
    for c in cats[:4]:
        footer_cat_links += f'        <a href="/category/{c["slug"]}/">{c["name"]}</a>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_img}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"WebSite","name":"{SITE_NAME}","url":"{SITE_URL}"}}
</script>
<style>{CSS}</style>
{_ga_snippet()}
</head>
<body>
<nav>
  <div class="nav-inner">
    <a href="/" class="logo">Global<span class="logo-amber">HighLevel</span></a>
    <div class="nav-links">
      <a href="/" class="nav-link">Home</a>
      <div class="nav-dropdown">
        <a class="nav-link">Topics <span style="font-size:10px">&#9662;</span></a>
        <div class="nav-dropdown-menu">
{dropdown_links}        </div>
      </div>
      <a href="/services/" class="nav-link">Services</a>
      <a href="https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV" class="nav-link" target="_blank" rel="noopener">Podcast</a>
      <a href="{AFFILIATE}" class="nav-cta" target="_blank" rel="nofollow noopener">Free 30-Day Trial</a>
    </div>
    <input type="checkbox" id="mobile-toggle">
    <label for="mobile-toggle" class="hamburger" aria-label="Menu">
      <span></span><span></span><span></span>
    </label>
    <div class="mobile-menu">
      <a href="/">Home</a>
      <a href="/services/">Services</a>
{dropdown_links}      <a href="https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV" target="_blank" rel="noopener">Podcast</a>
      <a href="{AFFILIATE}" class="nav-cta" target="_blank" rel="nofollow noopener">Free 30-Day Trial</a>
    </div>
  </div>
</nav>
{body}
<footer>
  <div class="footer-inner">
    <div class="footer-top">
      <div>
        <div class="footer-logo">Global<span>HighLevel</span></div>
        <p class="footer-desc">Free GoHighLevel tutorials, guides, and strategies for digital marketing agencies and businesses worldwide.</p>
        <p class="footer-disclaimer">Affiliate disclosure: Some links on this site are affiliate links. If you sign up through our link, we may earn a commission at no extra cost to you. Not affiliated with GoHighLevel LLC.</p>
      </div>
      <div class="footer-col">
        <h4>Topics</h4>
{footer_cat_links}      </div>
      <div class="footer-col">
        <h4>Resources</h4>
        <a href="https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV" target="_blank" rel="noopener">Podcast</a>
        <a href="https://help.gohighlevel.com" target="_blank" rel="noopener">GHL Help Center</a>
        <a href="{AFFILIATE}" target="_blank" rel="nofollow noopener">Free 30-Day Trial</a>
      </div>
    </div>
    <div class="footer-bottom">
      <span>&copy; {datetime.now().year} GlobalHighLevel.com</span>
      <span>Not affiliated with GoHighLevel LLC</span>
    </div>
  </div>
</footer>
</body>
</html>"""

# ── Load data ─────────────────────────────────────────────────────────────────

def load_posts() -> list[dict]:
    """Load all post JSON files from posts/ directory."""
    posts = []
    if not POSTS_DIR.exists():
        return posts
    for f in sorted(POSTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if data.get("slug") and data.get("html_content"):
                posts.append(data)
        except Exception:
            pass
    return posts

def load_published() -> list[dict]:
    """Load published.json for episode metadata."""
    if not PUBLISHED_JSON.exists():
        return []
    try:
        return json.loads(PUBLISHED_JSON.read_text())
    except Exception:
        return []

def merge_data(posts: list[dict], published: list[dict]) -> list[dict]:
    """Merge blog post data with episode metadata."""
    ep_by_id = {str(p.get("articleId", p.get("id", ""))): p for p in published}
    merged = []
    for post in posts:
        article_id = str(post.get("articleId", ""))
        ep = ep_by_id.get(article_id, {})
        merged.append({**ep, **post})
    # Sort newest first
    merged.sort(key=lambda x: x.get("publishedAt", x.get("uploadedAt", "")), reverse=True)
    return merged

# ── Page generators ───────────────────────────────────────────────────────────

def build_post_page(post: dict, all_posts: list = None):
    slug        = post["slug"]
    title       = post.get("title", post.get("seoTitle", ""))
    description = post.get("description", post.get("seoDescription", post.get("meta_description", "")))
    category    = display_cat(post.get("category", "")) or "GoHighLevel Tutorials"
    cat_slug    = slugify(category)
    date_str    = fmt_date(post.get("publishedAt", post.get("uploadedAt", "")))
    html_content = post.get("html_content", "")
    episode_id  = post.get("transistorEpisodeId", "")
    rtime       = read_time(html_content)
    canonical   = f"{SITE_URL}/blog/{slug}/"

    # ── Sanitize content: strip in-content TOC and CTA boxes ──────────────────
    html_content = sanitize_content(html_content)

    # ── Internal links: cross-link to related posts for SEO ──────────────────
    if all_posts:
        html_content = inject_internal_links(html_content, post, all_posts)

    # ── Podcast section ───────────────────────────────────────────────────────
    if episode_id:
        podcast_html = f"""
<div class="podcast-embed">
  <p>Listen to this episode</p>
  <iframe width="100%" height="180" frameborder="no" scrolling="no" seamless
    src="https://share.transistor.fm/e/{episode_id}" loading="lazy"></iframe>
  <a class="podcast-link" href="https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV" target="_blank" rel="noopener">
    Follow the podcast on Spotify
  </a>
</div>"""
    else:
        podcast_html = f"""
<div class="podcast-embed">
  <p>This tutorial also has a podcast episode</p>
  <a class="podcast-link" href="https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV" target="_blank" rel="noopener">
    Listen on Spotify — "Go High Level" podcast
  </a>
</div>"""

    # ── Table of contents ──────────────────────────────────────────────────────
    toc_items = extract_toc(html_content)
    if toc_items:
        toc_rows = "".join(f'<li><a href="#{a}">{label}</a></li>' for a, label in toc_items)
        toc_html = f"""
<div class="toc">
  <div class="toc-label">In This Guide</div>
  <ol>{toc_rows}</ol>
</div>"""
    else:
        toc_html = ""

    # ── CTA #1 — Below byline (compact one-liner) ─────────────────────────────
    cta1 = f"""
<p class="cta-byline">Follow along &mdash; <a href="/trial/">get 30 days free &rarr;</a></p>"""

    # ── CTA #2 — Mid-article inline ───────────────────────────────────────────
    cta_mid = f"""
<p class="cta-inline">This is built into GoHighLevel.
<a href="/trial/">Try it free for 30 days &rarr;</a></p>"""
    body_with_ctas = inject_inline_ctas(html_content, cta_mid)

    # ── CTA #3 — End of article box ───────────────────────────────────────────
    cta3 = f"""
<div class="cta-end">
  <h3>Ready to try this?</h3>
  <p>30 days free, no credit card required. Set up everything in this guide inside your trial.</p>
  <a href="{AFFILIATE}&utm_campaign={slug}" class="btn-amber" target="_blank" rel="nofollow noopener">Start Free 30-Day Trial</a>
  <div class="fine">Cancel anytime &mdash; $0 for the first 30 days</div>
</div>"""

    # ── Share buttons ─────────────────────────────────────────────────────────
    encoded_url = canonical.replace(":", "%3A").replace("/", "%2F")
    encoded_title = title.replace(" ", "%20").replace("&", "%26")
    share_html = f"""
<div class="share-row">
  <span>Share</span>
  <a href="https://twitter.com/intent/tweet?url={encoded_url}&text={encoded_title}" target="_blank" rel="noopener" class="share-btn">X</a>
  <a href="https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}" target="_blank" rel="noopener" class="share-btn">LinkedIn</a>
  <button class="share-btn" onclick="navigator.clipboard.writeText('{canonical}');this.textContent='Copied!'">Copy Link</button>
</div>"""

    # ── Author box ─────────────────────────────────────────────────────────────
    author_html = f"""
<div class="author-box">
  <div>
    <div class="author-name">William Welch</div>
    <div class="author-bio">GoHighLevel user and affiliate. Runs GlobalHighLevel.com — free tutorials, guides, and strategies for agencies and businesses using GHL worldwide.</div>
  </div>
</div>"""

    # ── Related posts ──────────────────────────────────────────────────────────
    related_html = ""
    if all_posts:
        related = get_related(post, all_posts)
        if related:
            cards = ""
            for r in related:
                r_slug  = r.get("slug", "")
                r_title = r.get("title", r.get("seoTitle", ""))
                r_cat   = display_cat(r.get("category", "")) or "GoHighLevel"
                cards += f"""
<a href="/blog/{r_slug}/" class="related-card">
  <div class="r-tag">{r_cat}</div>
  <div class="r-title">{r_title}</div>
</a>"""
            related_html = f"""
<div class="related-posts">
  <div class="related-label">Keep Reading</div>
  <div class="related-grid">{cards}</div>
</div>"""

    # ── Schema ─────────────────────────────────────────────────────────────────
    article_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "datePublished": post.get("publishedAt", post.get("uploadedAt", "")),
        "author": {"@type": "Person", "name": "William Welch"},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE_URL},
        "url": canonical
    })

    # ── Progress bar JS ────────────────────────────────────────────────────────
    progress_js = """
<script>
(function(){
  var bar=document.getElementById('reading-progress');
  if(!bar)return;
  window.addEventListener('scroll',function(){
    var body=document.querySelector('.post-body');
    if(!body)return;
    var top=body.getBoundingClientRect().top+window.scrollY;
    var h=body.offsetHeight-window.innerHeight;
    var pct=h>0?Math.min(100,Math.max(0,(window.scrollY-top+window.innerHeight*0.1)/h*100)):100;
    bar.style.width=pct+'%';
  },{passive:true});
})();
</script>"""

    body = f"""
<div id="reading-progress"></div>
<div class="post-container">
  <div class="post-breadcrumb fade-1">
    <a href="/">Home</a><span class="bc-sep">&rsaquo;</span><a href="/category/{cat_slug}/">{category}</a><span class="bc-sep">&rsaquo;</span><span>{truncate(title, 50)}</span>
  </div>
  <div class="post-eyebrow fade-1"><a href="/category/{cat_slug}/" style="color:var(--amber);text-decoration:none">{category}</a></div>
  <h1 class="post-title fade-2">{title}</h1>
  <div class="post-byline fade-3">
    <span>By William Welch</span>
    {"<span class='sep'>&middot;</span><span>" + date_str + "</span>" if date_str else ""}
    <span class="sep">&middot;</span><span>{rtime}</span>
  </div>
  {share_html}
  {cta1}
  {toc_html}
  {podcast_html}
  <div class="post-body">{body_with_ctas}</div>
  {cta3}
  {author_html}
  {related_html}
</div>
<script type="application/ld+json">{article_schema}</script>
{progress_js}"""

    html = base_html(
        title=f"{title} | {SITE_NAME}",
        description=truncate(description, 160),
        canonical=canonical,
        body=body
    )
    write(PUBLIC_DIR / "blog" / slug / "index.html", html)


def build_index(posts: list[dict], page: int = 1, per_page: int = 18):
    total_pages = max(1, -(-len(posts) // per_page))
    start = (page - 1) * per_page
    page_posts = posts[start:start + per_page]

    # ── Build card HTML for all page posts ────────────────────────────────────
    def make_card(p):
        slug     = p.get("slug", "")
        title    = p.get("title", p.get("seoTitle", "Untitled"))
        desc     = truncate(p.get("description", p.get("seoDescription", p.get("meta_description", ""))), 130)
        cat      = display_cat(p.get("category", ""))
        date_str = fmt_date(p.get("publishedAt", p.get("uploadedAt", "")))
        ep_id    = p.get("transistorEpisodeId", "")
        rtime    = read_time(p.get("html_content", desc))
        cat_html = f'<a href="/category/{slugify(cat)}/" class="card-cat">{cat}</a>' if cat else ""
        podcast  = '<span class="podcast-badge">Podcast</span>' if ep_id else ""
        return f"""
<article class="card">
  {cat_html}
  <h2 class="card-title"><a href="/blog/{slug}/">{title}</a></h2>
  <p class="card-excerpt">{desc}</p>
  <div class="card-meta">
    <span>{date_str}</span>
    {"<span class='meta-sep'>&middot;</span><span>" + rtime + "</span>" if date_str else ""}
    {podcast}
  </div>
</article>"""

    # Pagination
    pages_html = ""
    if total_pages > 1:
        for i in range(1, total_pages + 1):
            href = "/" if i == 1 else f"/page/{i}/"
            active = "active" if i == page else ""
            pages_html += f'<a href="{href}" class="page-btn {active}">{i}</a>'
        pages_html = f'<div class="pagination">{pages_html}</div>'

    canonical = SITE_URL + ("/" if page == 1 else f"/page/{page}/")

    # ── PAGE 1: Editorial homepage ────────────────────────────────────────────
    if page == 1 and len(page_posts) > 0:
        lead = page_posts[0]
        stack_posts = page_posts[1:4]
        rest_posts = page_posts[4:]
        # Trending = top 5 posts for sidebar
        trending = posts[:5]

        # Featured section: lead + stack
        lead_slug = lead.get("slug", "")
        lead_title = lead.get("title", lead.get("seoTitle", ""))
        lead_desc = truncate(lead.get("description", lead.get("seoDescription", lead.get("meta_description", ""))), 200)
        lead_cat = display_cat(lead.get("category", ""))
        lead_date = fmt_date(lead.get("publishedAt", lead.get("uploadedAt", "")))
        lead_rtime = read_time(lead.get("html_content", lead_desc))
        lead_cat_html = f'<a href="/category/{slugify(lead_cat)}/" class="hp-lead-cat" style="text-decoration:none;display:inline-block">{lead_cat}</a>' if lead_cat else ""

        stack_html = ""
        for sp in stack_posts:
            sp_slug = sp.get("slug", "")
            sp_title = sp.get("title", sp.get("seoTitle", ""))
            sp_cat = display_cat(sp.get("category", ""))
            sp_date = fmt_date(sp.get("publishedAt", sp.get("uploadedAt", "")))
            sp_cat_html = f'<a href="/category/{slugify(sp_cat)}/" class="hp-stack-cat" style="text-decoration:none;display:inline-block">{sp_cat}</a>' if sp_cat else ""
            stack_html += f"""
<div class="hp-stack-item">
  {sp_cat_html}
  <div class="hp-stack-title"><a href="/blog/{sp_slug}/">{sp_title}</a></div>
  <div class="hp-stack-meta">{sp_date}</div>
</div>"""

        # Article list (rest of posts)
        articles_html = ""
        for p in rest_posts:
            articles_html += make_card(p)

        # Trending sidebar
        trending_html = ""
        for i, tp in enumerate(trending, 1):
            tp_slug = tp.get("slug", "")
            tp_title = tp.get("title", tp.get("seoTitle", ""))
            trending_html += f"""
<div class="trending-item">
  <span class="trending-num">{i:02d}</span>
  <div class="trending-title"><a href="/blog/{tp_slug}/">{tp_title}</a></div>
</div>"""

        # Topics sidebar
        topics_html = ""
        for c in CATEGORIES:
            c_count = len([p for p in posts if slugify(p.get("category", "")) == c["slug"]])
            topics_html += f"""
<a href="/category/{c['slug']}/" class="sidebar-cat-link">
  <span>{c['name']}</span>
  <span class="sidebar-cat-count">{c_count}</span>
</a>"""

        body = f"""
<div class="container" style="padding-top:56px">
  <div class="hp-hero fade-1" style="text-align:center;padding:48px 0 40px">
    <h1 style="font-family:var(--sans);font-size:clamp(1.8rem,4vw,2.8rem);font-weight:800;color:var(--text);line-height:1.15;letter-spacing:-.5px;margin:0 0 12px">GoHighLevel Tutorials, Tips &amp; 30-Day Free Trial</h1>
    <p style="font-size:1.1rem;color:var(--muted);max-width:640px;margin:0 auto 20px;line-height:1.6">Learn how to automate your agency with GoHighLevel. Free tutorials, podcast episodes &amp; step-by-step guides — updated daily.</p>
    <a href="{AFFILIATE}&utm_campaign=hero" class="btn-amber" style="font-size:.9rem;padding:12px 28px" target="_blank" rel="nofollow noopener">Start Your 30-Day Free Trial</a>
  </div>
  <div class="hp-featured fade-1">
    <div class="hp-lead">
      {lead_cat_html}
      <h2 class="hp-lead-title"><a href="/blog/{lead_slug}/">{lead_title}</a></h2>
      <p class="hp-lead-desc">{lead_desc}</p>
      <div class="hp-lead-meta">{lead_date} &middot; {lead_rtime}</div>
    </div>
    <div class="hp-stack">{stack_html}</div>
  </div>
  <div class="hp-body">
    <div class="hp-articles">
      <div class="section-label">Latest</div>
      {articles_html}
      {pages_html}
    </div>
    <aside class="hp-sidebar">
      <div class="sidebar-section">
        <div class="section-label">Trending</div>
        <div class="sidebar-trending">{trending_html}</div>
      </div>
      <div class="sidebar-section">
        <div class="section-label">Topics</div>
        <div class="sidebar-trending">{topics_html}</div>
      </div>
      <div class="sidebar-section">
        <div class="sidebar-podcast">
          <div class="section-label" style="border-bottom-color:#1DB954">Podcast</div>
          <p>"Go High Level" on Spotify — 380 followers, new episodes daily.</p>
          <a href="https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV" class="btn-spotify" target="_blank" rel="noopener">Listen on Spotify</a>
        </div>
      </div>
      <div class="sidebar-section">
        <div class="sidebar-cta">
          <div class="s-headline">Try GoHighLevel Free</div>
          <div class="s-sub">30 days full access — double the standard 14-day trial.</div>
          <a href="/trial/" class="btn-amber" style="display:block;text-align:center;font-size:.8rem">Start Free Trial</a>
          <div class="s-fine">Cancel anytime &mdash; $0 for 30 days</div>
        </div>
      </div>
    </aside>
  </div>
</div>"""
    else:
        # Non-first pages or empty: simple list
        cards_html = ""
        for p in page_posts:
            cards_html += make_card(p)

        body = f"""
<div class="container" style="padding-top:100px">
  <div class="section-label">{"Tutorials" if page == 1 else f"Page {page}"}</div>
  <div class="cards-grid">{cards_html}</div>
  {pages_html}
</div>"""

    html = base_html(
        title=f"{SITE_NAME} — {SITE_TAGLINE}" if page == 1 else f"Page {page} | {SITE_NAME}",
        description="Free GoHighLevel tutorials, guides, and strategies for digital marketing agencies worldwide. Learn GHL step by step.",
        canonical=canonical,
        body=body
    )
    if page == 1:
        write(PUBLIC_DIR / "index.html", html)
    else:
        write(PUBLIC_DIR / "page" / str(page) / "index.html", html)


def build_category_pages(posts: list[dict]):
    by_cat: dict[str, list] = {}
    for p in posts:
        raw_cat = p.get("category", "")
        cat = raw_cat if display_cat(raw_cat) else "GoHighLevel Tutorials"
        by_cat.setdefault(cat, []).append(p)

    for cat, cat_posts in by_cat.items():
        cat_slug = slugify(cat)
        cards_html = ""
        for p in cat_posts:
            slug     = p.get("slug", "")
            title    = p.get("title", p.get("seoTitle", "Untitled"))
            desc     = truncate(p.get("description", p.get("seoDescription", p.get("meta_description", ""))), 130)
            date_str = fmt_date(p.get("publishedAt", p.get("uploadedAt", "")))
            ep_id    = p.get("transistorEpisodeId", "")
            rtime    = read_time(p.get("html_content", desc))
            cat_label = display_cat(cat)
            cat_html  = f'<a href="/category/{slugify(cat_label)}/" class="card-cat">{cat_label}</a>' if cat_label else ""
            podcast   = '<span class="podcast-badge">Podcast</span>' if ep_id else ""
            cards_html += f"""
<article class="card">
  {cat_html}
  <h2 class="card-title"><a href="/blog/{slug}/">{title}</a></h2>
  <p class="card-excerpt">{desc}</p>
  <div class="card-meta">
    <span>{date_str}</span>
    {"<span class='meta-sep'>&middot;</span><span>" + rtime + "</span>" if date_str else ""}
    {podcast}
  </div>
</article>"""

        cat_config = next((c for c in CATEGORIES if c["slug"] == cat_slug), None)
        cat_desc = cat_config["description"] if cat_config else f"Free GoHighLevel {cat.lower()} guides and tutorials."

        body = f"""
<div class="cat-header">
  <div class="container">
    <div class="section-label fade-1" style="border-bottom:none;padding-bottom:0;margin-bottom:8px">Category</div>
    <h1 class="fade-2">{cat}</h1>
    <p class="fade-3">{cat_desc}</p>
    <p class="fade-3" style="font-size:.8rem;color:var(--text3);margin-top:6px">{len(cat_posts)} guides</p>
  </div>
</div>
<div class="container">
  <div class="cards-grid" style="padding:32px 0 80px">{cards_html}</div>
</div>"""

        canonical = f"{SITE_URL}/category/{cat_slug}/"
        html = base_html(
            title=f"{cat} | {SITE_NAME}",
            description=f"Free GoHighLevel {cat.lower()} guides and tutorials. Step-by-step help for agencies and businesses.",
            canonical=canonical,
            body=body
        )
        write(PUBLIC_DIR / "category" / cat_slug / "index.html", html)


def build_sitemap(posts: list[dict]):
    urls = [f"  <url><loc>{SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    urls.append(f"  <url><loc>{SITE_URL}/trial/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>")
    urls.append(f"  <url><loc>{SITE_URL}/coupon/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>")
    urls.append(f"  <url><loc>{SITE_URL}/services/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>")
    for c in CATEGORIES:
        urls.append(f'  <url><loc>{SITE_URL}/category/{c["slug"]}/</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>')
    for p in posts:
        slug = p.get("slug", "")
        date = p.get("publishedAt", p.get("uploadedAt", ""))[:10]
        urls.append(f'  <url><loc>{SITE_URL}/blog/{slug}/</loc><lastmod>{date}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>')

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls)
    xml += "\n</urlset>"
    write(PUBLIC_DIR / "sitemap.xml", xml)


def build_llms_txt(posts: list[dict]):
    """
    Generate llms.txt — tells AI models (ChatGPT, Claude, Perplexity, Gemini)
    what this site is about and lists all available content.
    Standard: https://llmstxt.org
    """
    post_lines = ""
    for p in posts[:200]:  # cap at 200 most recent
        title = p.get("title", p.get("seoTitle", ""))
        slug  = p.get("slug", "")
        desc  = truncate(p.get("description", p.get("seoDescription", p.get("meta_description", ""))), 120)
        if title and slug:
            post_lines += f"- [{title}]({SITE_URL}/blog/{slug}/): {desc}\n"

    content = f"""# GlobalHighLevel.com

> Free GoHighLevel tutorials, guides, and strategies for digital marketing agencies and businesses worldwide.

GlobalHighLevel.com is a free resource covering GoHighLevel (GHL) — an all-in-one CRM, marketing automation, and funnel platform used by digital marketing agencies globally. Every tutorial on this site also has a corresponding podcast episode on Spotify ("Go High Level", {SITE_URL}).

## About

- **Author:** William Welch — GoHighLevel user and affiliate
- **Audience:** Digital marketing agency owners, freelancers, business owners
- **Content:** 80+ step-by-step tutorials covering every major GoHighLevel feature
- **Podcast:** "Go High Level" on Spotify — https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV
- **Free Trial:** 30-day GoHighLevel free trial (double the standard 14 days) — https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12

## Content

All tutorials are free. Topics include GoHighLevel automations, AI conversation bots, funnel building, pipeline management, SMS/email marketing, reputation management, calendar booking, white-label SaaS setup, and sub-account management.

## Tutorials

{post_lines if post_lines else "- New tutorials published daily. See full list at " + SITE_URL}

## Optional

- Sitemap: {SITE_URL}/sitemap.xml
- Podcast: https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV
"""
    write(PUBLIC_DIR / "llms.txt", content)


def build_trial_page():
    """Build SEO-optimized /trial/ landing page targeting free trial keywords."""
    canonical = f"{SITE_URL}/trial/"
    title = "GoHighLevel Free Trial — 30 Days Free (2026)"
    description = "Get a 30-day GoHighLevel free trial instead of the standard 14 days. Full access to CRM, funnels, automations, AI tools and more. Cancel anytime."

    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "How long is the GoHighLevel free trial?",
                "acceptedAnswer": {"@type": "Answer", "text": "The standard GoHighLevel free trial is 14 days. Through GlobalHighLevel.com, you get an extended 30-day free trial — double the time to explore every feature."}
            },
            {
                "@type": "Question",
                "name": "Do I need a credit card for the GoHighLevel free trial?",
                "acceptedAnswer": {"@type": "Answer", "text": "No. The 30-day GoHighLevel free trial does not require a credit card. You can cancel anytime during the trial with no charge."}
            },
            {
                "@type": "Question",
                "name": "What do I get with the GoHighLevel free trial?",
                "acceptedAnswer": {"@type": "Answer", "text": "Full access to GoHighLevel's CRM, funnel builder, email & SMS marketing, workflow automations, AI conversation bots, calendar booking, reputation management, and more. Nothing is locked during the trial."}
            },
            {
                "@type": "Question",
                "name": "How much does GoHighLevel cost after the free trial?",
                "acceptedAnswer": {"@type": "Answer", "text": "GoHighLevel starts at $97/month after the trial ends. You can cancel anytime during your 30-day free trial if it's not the right fit."}
            },
            {
                "@type": "Question",
                "name": "Is this GoHighLevel free trial legitimate?",
                "acceptedAnswer": {"@type": "Answer", "text": "Yes. This is an official GoHighLevel extended trial offered through their affiliate program. You sign up directly on GoHighLevel's website with full access to all features."}
            },
            {
                "@type": "Question",
                "name": "GoHighLevel 14-day trial vs 30-day trial — what's the difference?",
                "acceptedAnswer": {"@type": "Answer", "text": "The features are identical. The only difference is time. The standard trial from gohighlevel.com gives you 14 days. Through this page, you get 30 days — enough time to set up funnels, migrate contacts, and see real results before deciding."}
            }
        ]
    })

    offer_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Offer",
        "name": "GoHighLevel 30-Day Free Trial",
        "description": "Extended 30-day free trial for GoHighLevel — CRM, funnels, automations, and AI tools for agencies.",
        "price": "0",
        "priceCurrency": "USD",
        "availability": "https://schema.org/InStock",
        "url": canonical,
        "seller": {"@type": "Organization", "name": "GoHighLevel"}
    })

    body = f"""
<div class="post-container" style="max-width:740px;padding-top:100px">

  <div class="fade-1" style="text-align:center;margin-bottom:48px">
    <p style="font-size:.82rem;color:var(--text3);margin-bottom:24px">Already know you want in? <a href="{AFFILIATE}&utm_campaign=trial-page-skip" target="_blank" rel="nofollow noopener" style="color:var(--amber)">Go straight to GoHighLevel &rarr;</a></p>
    <p style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--amber);margin-bottom:16px">Extended Offer</p>
    <h1 style="font-family:var(--sans);font-size:clamp(2rem,4vw,3.2rem);font-weight:800;line-height:1.15;color:var(--text);letter-spacing:-.5px;margin-bottom:20px">GoHighLevel Free Trial — 30 Days Free</h1>
    <p style="font-size:1.15rem;color:var(--text2);line-height:1.7;max-width:580px;margin:0 auto 28px">Get a <strong style="color:var(--text)">30-day GHL free trial</strong> instead of the standard 14 days. Full access to every GoHighLevel feature — CRM, funnels, automations, AI tools, and more.</p>
    <a href="{AFFILIATE}&utm_campaign=trial-page-hero" class="btn-amber" style="font-size:1rem;padding:14px 36px" target="_blank" rel="nofollow noopener">Start Your 30-Day Free Trial &rarr;</a>
    <p style="font-size:.8rem;color:var(--text3);margin-top:12px">Cancel anytime &middot; $0 for 30 days</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px" class="fade-2">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">Why Get a 30-Day GHL Free Trial Instead of 14?</h2>
    <p style="font-size:1.05rem;color:var(--text2);line-height:1.75;margin-bottom:20px">The standard GoHighLevel free trial is 14 days. That's often not enough time to set up your funnels, migrate contacts, build automations, and actually see results.</p>
    <p style="font-size:1.05rem;color:var(--text2);line-height:1.75;margin-bottom:20px">Through this page, you get an <strong style="color:var(--text)">extended 30-day GoHighLevel free trial</strong> — double the time to explore every feature, follow our step-by-step tutorials, and decide if GHL is the right platform for your agency or business.</p>
    <p style="font-size:1.05rem;color:var(--text2);line-height:1.75">Cancel anytime during the trial — $0 for the first 30 days.</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px" class="fade-2">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">What's Included in Your GHL Free Trial</h2>
    <div class="trial-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:6px">CRM &amp; Pipeline Management</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">Contacts, deals, tags, smart lists, and custom pipelines to manage every lead.</p>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:6px">Funnel &amp; Website Builder</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">Drag-and-drop pages, forms, surveys, and full websites — no code needed.</p>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:6px">Email &amp; SMS Marketing</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">Bulk campaigns, drip sequences, and two-way conversations in one inbox.</p>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:6px">Workflow Automations</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">If/else logic, triggers, wait steps, webhooks — automate your entire client journey.</p>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:6px">AI Conversation Bots</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">Agent Studio, brand voice AI, and automated chat/SMS bots that book appointments.</p>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:6px">Calendar &amp; Booking</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">Booking widgets, round-robin scheduling, Google/Outlook sync, and reminders.</p>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:6px">Reputation Management</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">Automated review requests, Google review widget, and review response tools.</p>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:6px">White-Label SaaS Mode</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">Rebrand GHL as your own platform and resell to clients at your own price.</p>
      </div>
    </div>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">GoHighLevel Free Trial — Frequently Asked Questions</h2>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">How long is the GoHighLevel free trial?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">The standard GoHighLevel free trial is 14 days. Through GlobalHighLevel.com, you get an extended <strong style="color:var(--text)">30-day free trial</strong> — double the time to explore every feature.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">Do I need a credit card for the GoHighLevel free trial?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">No. The 30-day GoHighLevel free trial does not require a credit card. You can cancel anytime during the trial with no charge.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">What do I get with the GoHighLevel free trial?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">Full access to GoHighLevel's CRM, funnel builder, email &amp; SMS marketing, workflow automations, AI conversation bots, calendar booking, reputation management, and more. Nothing is locked during the trial.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">How much does GoHighLevel cost after the free trial?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">GoHighLevel starts at <strong style="color:var(--text)">$97/month</strong> after the trial ends. You can cancel anytime during your 30-day free trial if it's not the right fit.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">Is this GoHighLevel free trial legitimate?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">Yes. This is an official GoHighLevel extended trial offered through their affiliate program. You sign up directly on GoHighLevel's website with full access to all features.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">GoHighLevel 14-day trial vs 30-day trial — what's the difference?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">The features are identical. The only difference is time. The standard trial from gohighlevel.com gives you 14 days. Through this page, you get 30 days — enough time to set up funnels, migrate contacts, and see real results before deciding.</p>
    </div>
  </div>

  <div class="cta-end" style="margin-bottom:48px">
    <h3>Start Your GoHighLevel Free Trial</h3>
    <p>30 days full access. Cancel anytime. Set up your funnels, automations, and AI bots — and follow along with our <a href="/" style="color:var(--amber)">free tutorials</a>.</p>
    <a href="{AFFILIATE}&utm_campaign=trial-page-bottom" class="btn-amber" target="_blank" rel="nofollow noopener">Start Free 30-Day Trial &rarr;</a>
    <div class="fine">$0 for the first 30 days &middot; then $97/mo &middot; cancel anytime</div>
  </div>

  <div style="text-align:center;margin-bottom:32px">
    <p style="font-size:.85rem;color:var(--text2)">Looking for a discount? <a href="/coupon/" style="color:var(--amber)">See our GoHighLevel coupon code page</a> or <a href="/" style="color:var(--amber)">browse all GoHighLevel guides</a>.</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:32px">
    <p style="font-size:.8rem;color:var(--text3);line-height:1.7;text-align:center">Affiliate disclosure: If you sign up through the links on this page, GlobalHighLevel.com may earn a commission at no extra cost to you. We only recommend tools we use ourselves. Not affiliated with GoHighLevel LLC.</p>
  </div>

</div>
<script type="application/ld+json">{faq_schema}</script>
<script type="application/ld+json">{offer_schema}</script>"""

    html = base_html(
        title=f"{title} | {SITE_NAME}",
        description=description,
        canonical=canonical,
        body=body
    )
    write(PUBLIC_DIR / "trial" / "index.html", html)


def build_coupon_page():
    """Build SEO-optimized /coupon/ landing page targeting promo/discount keywords."""
    canonical = f"{SITE_URL}/coupon/"
    title = "GoHighLevel Coupon Code 2026 — 30 Days Free"
    description = "Looking for a GoHighLevel coupon code or promo code? Get a 30-day free trial instead of the standard 14 days. No discount code needed."

    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "Is there a GoHighLevel coupon code?",
                "acceptedAnswer": {"@type": "Answer", "text": "GoHighLevel doesn't offer traditional coupon codes or promo codes. Instead, you can get an extended 30-day free trial through affiliate partners like GlobalHighLevel.com — double the standard 14-day trial. No code needed."}
            },
            {
                "@type": "Question",
                "name": "How do I get a GoHighLevel discount?",
                "acceptedAnswer": {"@type": "Answer", "text": "The best GoHighLevel discount is the extended 30-day free trial. That's 16 extra free days compared to signing up directly. After the trial, plans start at $97/month. There are no publicly available coupon codes or promo codes."}
            },
            {
                "@type": "Question",
                "name": "Does GoHighLevel have a promo code for 2026?",
                "acceptedAnswer": {"@type": "Answer", "text": "There is no GoHighLevel promo code for 2026. GoHighLevel runs its discounts through extended trial offers via affiliate partners. Through this page, you get 30 days free instead of 14 — the best deal currently available."}
            },
            {
                "@type": "Question",
                "name": "Can I get GoHighLevel cheaper than $97/month?",
                "acceptedAnswer": {"@type": "Answer", "text": "GoHighLevel starts at $97/month and there are no publicly available coupon codes to reduce that. The best way to save is by starting with the extended 30-day free trial to make sure it's the right fit before paying anything."}
            },
            {
                "@type": "Question",
                "name": "What is the best GoHighLevel deal right now?",
                "acceptedAnswer": {"@type": "Answer", "text": "The best deal is the extended 30-day free trial — double the standard 14 days. Full access to every feature, no credit card required, cancel anytime. This is better than any coupon code because you pay $0 for a full month."}
            }
        ]
    })

    body = f"""
<div class="post-container" style="max-width:740px;padding-top:100px">

  <div class="fade-1" style="text-align:center;margin-bottom:48px">
    <p style="font-size:.82rem;color:var(--text3);margin-bottom:24px">Already know you want in? <a href="{AFFILIATE}&utm_campaign=coupon-page-skip" target="_blank" rel="nofollow noopener" style="color:var(--amber)">Go straight to GoHighLevel &rarr;</a></p>
    <p style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--amber);margin-bottom:16px">Better Than a Coupon</p>
    <h1 style="font-family:var(--sans);font-size:clamp(2rem,4vw,3.2rem);font-weight:800;line-height:1.15;color:var(--text);letter-spacing:-.5px;margin-bottom:20px">GoHighLevel Coupon Code 2026</h1>
    <p style="font-size:1.15rem;color:var(--text2);line-height:1.7;max-width:580px;margin:0 auto 12px">There's no GoHighLevel coupon code or promo code. But there's something better:</p>
    <p style="font-size:1.3rem;font-weight:800;color:var(--text);margin-bottom:28px">30 days free instead of 14 &mdash; no code needed.</p>
    <a href="{AFFILIATE}&utm_campaign=coupon-page-hero" class="btn-amber" style="font-size:1rem;padding:14px 36px" target="_blank" rel="nofollow noopener">Start Your 30-Day Free Trial &rarr;</a>
    <p style="font-size:.8rem;color:var(--text3);margin-top:12px">No credit card required &middot; No coupon code needed &middot; Cancel anytime</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px" class="fade-2">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">Why There's No GoHighLevel Coupon Code</h2>
    <p style="font-size:1.05rem;color:var(--text2);line-height:1.75;margin-bottom:20px">GoHighLevel doesn't typically offer coupon codes, promo codes, or discount codes. Instead, they run promotions through extended trial offers.</p>
    <p style="font-size:1.05rem;color:var(--text2);line-height:1.75;margin-bottom:20px">Instead, GoHighLevel offers <strong style="color:var(--text)">extended free trials</strong> through affiliate partners. The standard trial on gohighlevel.com is 14 days. Through this page, you get <strong style="color:var(--text)">30 days free</strong> — that's 16 extra days at no cost.</p>
    <p style="font-size:1.05rem;color:var(--text2);line-height:1.75">No code to enter. No checkout trick. Just click the link and your 30-day trial starts automatically.</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px" class="fade-2">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">30-Day Free Trial vs Coupon Code — The Math</h2>
    <div class="coupon-compare" style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:24px;text-align:center">
        <div style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--text3);margin-bottom:12px">Typical Coupon Code</div>
        <div style="font-size:2rem;font-weight:800;color:var(--text3);margin-bottom:8px;text-decoration:line-through">10-20% off</div>
        <p style="font-size:.85rem;color:var(--text3);line-height:1.6;margin:0">Saves $10-19 on first month. Still pay $78-87 immediately. 14-day trial only.</p>
      </div>
      <div style="background:var(--surface);border:1px solid var(--amber-border);border-radius:8px;padding:24px;text-align:center">
        <div style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--amber);margin-bottom:12px">Extended Free Trial</div>
        <div style="font-size:2rem;font-weight:800;color:var(--amber);margin-bottom:8px">$0 for 30 days</div>
        <p style="font-size:.85rem;color:var(--text2);line-height:1.6;margin:0">Pay nothing for a full month. Full access to every feature. Cancel anytime.</p>
      </div>
    </div>
    <p style="font-size:.95rem;color:var(--text2);line-height:1.7;margin-top:20px;text-align:center">Even a 20% coupon code only saves ~$19. The extended trial gives you <strong style="color:var(--text)">16 extra free days</strong> — more time to build before you pay anything.</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">What You Get During the GHL Free Trial</h2>
    <div class="coupon-features" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div style="padding:14px 18px;border:1px solid var(--border);border-radius:6px">
        <span style="font-size:.85rem;color:var(--text)">CRM &amp; Pipeline Management</span>
      </div>
      <div style="padding:14px 18px;border:1px solid var(--border);border-radius:6px">
        <span style="font-size:.85rem;color:var(--text)">Funnel &amp; Website Builder</span>
      </div>
      <div style="padding:14px 18px;border:1px solid var(--border);border-radius:6px">
        <span style="font-size:.85rem;color:var(--text)">Email &amp; SMS Marketing</span>
      </div>
      <div style="padding:14px 18px;border:1px solid var(--border);border-radius:6px">
        <span style="font-size:.85rem;color:var(--text)">Workflow Automations</span>
      </div>
      <div style="padding:14px 18px;border:1px solid var(--border);border-radius:6px">
        <span style="font-size:.85rem;color:var(--text)">AI Conversation Bots</span>
      </div>
      <div style="padding:14px 18px;border:1px solid var(--border);border-radius:6px">
        <span style="font-size:.85rem;color:var(--text)">Calendar &amp; Booking</span>
      </div>
      <div style="padding:14px 18px;border:1px solid var(--border);border-radius:6px">
        <span style="font-size:.85rem;color:var(--text)">Reputation Management</span>
      </div>
      <div style="padding:14px 18px;border:1px solid var(--border);border-radius:6px">
        <span style="font-size:.85rem;color:var(--text)">White-Label SaaS Mode</span>
      </div>
    </div>
    <p style="font-size:.85rem;color:var(--text3);margin-top:14px;text-align:center">Explore all of these during your 30-day GHL free trial.</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">GoHighLevel Pricing After the Trial</h2>
    <div style="background:var(--surface);border:1px solid var(--amber-border);border-radius:8px;padding:28px;text-align:center">
      <p style="font-size:.85rem;color:var(--text2);margin-bottom:8px">GoHighLevel plans start at</p>
      <div style="font-size:2.5rem;font-weight:800;color:var(--text);margin-bottom:8px">$97<span style="font-size:1rem;color:var(--text3)">/month</span></div>
      <p style="font-size:.9rem;color:var(--text2);margin:0">But you pay <strong style="color:var(--amber)">$0 for the first 30 days</strong> with the extended trial. No coupon code or promo code will beat that.</p>
    </div>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">GoHighLevel Coupon Code FAQ</h2>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">Is there a GoHighLevel coupon code?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">GoHighLevel doesn't offer traditional coupon codes or promo codes. Instead, you can get an extended <strong style="color:var(--text)">30-day free trial</strong> through affiliate partners like GlobalHighLevel.com — double the standard 14-day trial. No code needed.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">How do I get a GoHighLevel discount?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">The best GoHighLevel discount is the extended 30-day free trial. That's 16 extra free days compared to signing up directly. After the trial, plans start at $97/month. There are no publicly available coupon codes or promo codes.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">Does GoHighLevel have a promo code for 2026?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">There is no GoHighLevel promo code for 2026. GoHighLevel runs its discounts through extended trial offers via affiliate partners. Through this page, you get 30 days free instead of 14 — the best deal currently available.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">Can I get GoHighLevel cheaper than $97/month?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">GoHighLevel starts at $97/month and there are no publicly available coupon codes to reduce that. The best way to save is by starting with the extended 30-day free trial to make sure it's the right fit before paying anything.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">What is the best GoHighLevel deal right now?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">The best deal is the extended 30-day free trial — double the standard 14 days. Full access to every feature, no credit card required, cancel anytime. This is better than any coupon code because you pay <strong style="color:var(--text)">$0 for a full month</strong>.</p>
    </div>
  </div>

  <div class="cta-end" style="margin-bottom:48px">
    <h3>Skip the Coupon Code &mdash; Get 30 Days Free</h3>
    <p>No promo code, no discount code, no checkout tricks. Just a full month of GoHighLevel at $0. Follow along with our <a href="/" style="color:var(--amber)">free tutorials</a> while you build.</p>
    <a href="{AFFILIATE}&utm_campaign=coupon-page-bottom" class="btn-amber" target="_blank" rel="nofollow noopener">Start Free 30-Day Trial &rarr;</a>
    <div class="fine">$0 for the first 30 days &middot; then $97/mo &middot; cancel anytime</div>
  </div>

  <div style="text-align:center;margin-bottom:32px">
    <p style="font-size:.85rem;color:var(--text2)">Looking for tutorials instead? <a href="/trial/" style="color:var(--amber)">Learn more about the free trial</a> or <a href="/" style="color:var(--amber)">browse all GoHighLevel guides</a>.</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:32px">
    <p style="font-size:.8rem;color:var(--text3);line-height:1.7;text-align:center">Affiliate disclosure: If you sign up through the links on this page, GlobalHighLevel.com may earn a commission at no extra cost to you. We only recommend tools we use ourselves. Not affiliated with GoHighLevel LLC.</p>
  </div>

</div>
<script type="application/ld+json">{faq_schema}</script>"""

    html = base_html(
        title=f"{title} | {SITE_NAME}",
        description=description,
        canonical=canonical,
        body=body
    )
    write(PUBLIC_DIR / "coupon" / "index.html", html)


def build_services_page():
    """Build /services/ page — a la carte AI automation services."""
    canonical = f"{SITE_URL}/services/"
    title = "GoHighLevel Automation Services — $497/mo"
    description = "AI automation systems built inside GoHighLevel. Content pipelines, lead follow-up, appointment setting, SEO engines, and more. A la carte, no contracts."

    WEBHOOK_URL = "https://services.leadconnectorhq.com/hooks/VL5PlkLBYG4mKk3N6PGw/webhook-trigger/98cc6f29-7cee-4b59-845f-8908cdbe9575"

    services = [
        {
            "name": "AI Content Pipeline",
            "desc": "Automated blog posts and podcast episodes generated from your existing content, published on autopilot.",
            "includes": "Source scraping, AI audio generation, transcription, SEO blog posts, podcast distribution",
        },
        {
            "name": "SEO Engine",
            "desc": "Google Search Console monitoring with auto-generated topics, landing pages, and content gap analysis.",
            "includes": "GSC integration, keyword tracking, auto-generated pages, 28-day optimization cycles",
        },
        {
            "name": "AI Lead Follow-Up",
            "desc": "Claude-powered SMS and email sequences that respond intelligently to inbound leads. Opt-in only.",
            "includes": "AI conversation flows, smart nurture sequences, re-engagement campaigns, CRM tagging",
        },
        {
            "name": "AI Appointment Setter",
            "desc": "Conversation bot that qualifies leads and books calls on your calendar — no human needed.",
            "includes": "GHL Agent Studio setup, calendar integration, qualification logic, handoff workflows",
        },
        {
            "name": "Direct Mail Campaigns",
            "desc": "AI-written postcards and letters with multi-touch sequences that drive inbound responses.",
            "includes": "6-touch campaign copywriting, QR tracking, CRM integration, follow-up automation",
        },
        {
            "name": "CRM Setup &amp; Workflow Automation",
            "desc": "Pipelines, triggers, and workflows configured to automate your entire client journey.",
            "includes": "Pipeline design, workflow automation, tagging logic, reporting dashboards",
        },
        {
            "name": "Multi-Location SEO Pages",
            "desc": "Hundreds of geo-targeted landing pages generated at scale for local service businesses.",
            "includes": "Dynamic page generation, local schema markup, city/county targeting, sitemap automation",
        },
        {
            "name": "Reputation Management",
            "desc": "Automated review requests after jobs, AI-written responses, and Google review monitoring.",
            "includes": "Review request workflows, AI response drafting, sentiment tracking, review widgets",
        },
    ]

    services_html = ""
    for s in services:
        services_html += f"""
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:24px;transition:border-color .2s">
        <div style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">{s['name']}</div>
        <p style="font-size:.9rem;color:var(--text2);line-height:1.65;margin-bottom:12px">{s['desc']}</p>
        <p style="font-size:.78rem;color:var(--text3);line-height:1.6;margin:0"><strong style="color:var(--text2)">Includes:</strong> {s['includes']}</p>
      </div>"""

    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "How much do GoHighLevel automation services cost?",
                "acceptedAnswer": {"@type": "Answer", "text": "Each automation system is $497/month plus API usage at 6x cost. Pick only the systems you need — no bundles, no contracts. API usage covers Claude, Gemini, and other AI services powering your automations."}
            },
            {
                "@type": "Question",
                "name": "Do you do unsolicited outbound SMS?",
                "acceptedAnswer": {"@type": "Answer", "text": "No. All SMS and email automation is opt-in only. We don't support cold outreach, skip-traced lists, or unsolicited messaging. This protects your numbers from being banned and keeps you compliant with TCPA and A2P 10DLC regulations. Read more at globalhighlevel.com/blog/unsolicited-sms-gohighlevel-compliance-risk/"}
            },
            {
                "@type": "Question",
                "name": "What AI tools do you use for GoHighLevel automation?",
                "acceptedAnswer": {"@type": "Answer", "text": "We use Claude (Anthropic) for intelligent conversations, copywriting, and decision-making. Gemini for transcription and content processing. NotebookLM for podcast generation. All integrated directly into your GoHighLevel account."}
            },
            {
                "@type": "Question",
                "name": "How long does setup take?",
                "acceptedAnswer": {"@type": "Answer", "text": "Most systems are live within 3-5 business days. Complex multi-system setups may take 1-2 weeks. We use AI to accelerate the build process so you are not waiting months for delivery."}
            },
            {
                "@type": "Question",
                "name": "Do I need a GoHighLevel account?",
                "acceptedAnswer": {"@type": "Answer", "text": "Yes. We build inside your GHL account so you own everything. Don't have one yet? Start a 30-day free trial at globalhighlevel.com/trial and we'll set up your first system during the trial period."}
            }
        ]
    })

    service_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Service",
        "name": "GoHighLevel AI Automation Services",
        "description": "Done-for-you AI automation systems built inside GoHighLevel. Content pipelines, lead follow-up, appointment setting, SEO engines, and more.",
        "provider": {"@type": "Organization", "name": "GlobalHighLevel", "url": SITE_URL},
        "url": canonical,
        "offers": {
            "@type": "Offer",
            "price": "497",
            "priceCurrency": "USD",
            "description": "Per automation system per month, plus API usage"
        }
    })

    body = f"""
<div class="post-container" style="max-width:780px;padding-top:100px">

  <div class="fade-1" style="text-align:center;margin-bottom:48px">
    <p style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--amber);margin-bottom:16px">AI Automation Services</p>
    <h1 style="font-family:var(--sans);font-size:clamp(2rem,4vw,3rem);font-weight:800;line-height:1.15;color:var(--text);letter-spacing:-.5px;margin-bottom:20px">GoHighLevel Automation Services — AI Systems That Run Your Business</h1>
    <p style="font-size:1.1rem;color:var(--text2);line-height:1.7;max-width:600px;margin:0 auto 16px">Pick the automations you need. We build them inside your GHL account. They run 24/7. You pay monthly.</p>
    <p style="font-size:1.3rem;font-weight:800;color:var(--text);margin-bottom:8px">$497/mo per system + API usage</p>
    <p style="font-size:.85rem;color:var(--text3)">API usage billed at 6x cost &middot; No contracts &middot; Cancel anytime</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px" class="fade-2">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:8px">GHL Automation Services — Pick What You Need</h2>
    <p style="font-size:.9rem;color:var(--text3);margin-bottom:24px">Each system is $497/mo. Pick one, pick all eight. No bundles, no upsells.</p>
    <div class="services-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
{services_html}
    </div>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">How It Works</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px" class="services-steps">
      <div style="text-align:center">
        <div style="font-size:2rem;font-weight:800;color:var(--amber);margin-bottom:8px">1</div>
        <div style="font-size:.9rem;font-weight:700;color:var(--text);margin-bottom:6px">You Pick</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">Choose the automations you need from the menu above.</p>
      </div>
      <div style="text-align:center">
        <div style="font-size:2rem;font-weight:800;color:var(--amber);margin-bottom:8px">2</div>
        <div style="font-size:.9rem;font-weight:700;color:var(--text);margin-bottom:6px">We Build</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">We set everything up inside your GoHighLevel account. Live in 3-5 days.</p>
      </div>
      <div style="text-align:center">
        <div style="font-size:2rem;font-weight:800;color:var(--amber);margin-bottom:8px">3</div>
        <div style="font-size:.9rem;font-weight:700;color:var(--text);margin-bottom:6px">It Runs</div>
        <p style="font-size:.82rem;color:var(--text2);line-height:1.6;margin:0">Your systems run 24/7. You pay monthly. Cancel anytime.</p>
      </div>
    </div>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">GoHighLevel Consulting &amp; Setup Pricing</h2>
    <div style="background:var(--surface);border:1px solid var(--amber-border);border-radius:8px;padding:32px;text-align:center;margin-bottom:20px">
      <div style="font-size:2.5rem;font-weight:800;color:var(--text)">$497<span style="font-size:1rem;color:var(--text3)">/mo per system</span></div>
      <p style="font-size:.95rem;color:var(--text2);margin:12px 0 0">+ API usage at 6x cost (typically $30-150/mo depending on volume)</p>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px" class="services-pricing">
      <div style="padding:16px;border:1px solid var(--border);border-radius:6px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:4px">1 system</div>
        <div style="font-size:.82rem;color:var(--text2)">$497/mo + API</div>
      </div>
      <div style="padding:16px;border:1px solid var(--border);border-radius:6px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:4px">3 systems</div>
        <div style="font-size:.82rem;color:var(--text2)">$1,491/mo + API</div>
      </div>
      <div style="padding:16px;border:1px solid var(--border);border-radius:6px">
        <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:4px">5 systems</div>
        <div style="font-size:.82rem;color:var(--text2)">$2,485/mo + API</div>
      </div>
      <div style="padding:16px;border:1px solid var(--border);border-radius:8px;border-color:var(--amber-border)">
        <div style="font-size:.85rem;font-weight:700;color:var(--amber);margin-bottom:4px">All 8 systems</div>
        <div style="font-size:.82rem;color:var(--text2)">$3,976/mo + API</div>
      </div>
    </div>
    <p style="font-size:.8rem;color:var(--text3);text-align:center;margin-top:14px">No setup fees &middot; No contracts &middot; Cancel any system anytime</p>
  </div>

  <div style="background:var(--surface);border:1px solid var(--amber-border);border-radius:8px;padding:24px;margin-bottom:48px">
    <div style="display:flex;align-items:flex-start;gap:12px">
      <div style="font-size:1.2rem;line-height:1">&#9888;</div>
      <div>
        <div style="font-size:.9rem;font-weight:700;color:var(--text);margin-bottom:6px">Opt-In Only — No Unsolicited SMS</div>
        <p style="font-size:.85rem;color:var(--text2);line-height:1.65;margin:0">All SMS and email automation we build is <strong style="color:var(--text)">opt-in only</strong>. We do not support cold outreach, skip-traced lists, or unsolicited messaging. This protects your phone numbers from being banned and keeps you compliant with TCPA and A2P 10DLC regulations. <a href="/blog/unsolicited-sms-gohighlevel-compliance-risk/" style="color:var(--amber)">Read why this matters &rarr;</a></p>
      </div>
    </div>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:24px">GoHighLevel Setup Service FAQ</h2>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">How much do GoHighLevel automation services cost?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">Each automation system is $497/month plus API usage at 6x cost. Pick only the systems you need — no bundles, no contracts. API usage covers Claude, Gemini, and other AI services powering your automations.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">Do you do unsolicited outbound SMS?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">No. All SMS and email automation is opt-in only. We don't support cold outreach, skip-traced lists, or unsolicited messaging. This protects your numbers from being banned and keeps you compliant with TCPA and A2P 10DLC regulations. <a href="/blog/unsolicited-sms-gohighlevel-compliance-risk/" style="color:var(--amber)">Read why this matters</a>.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">What AI tools do you use?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">We use Claude (Anthropic) for intelligent conversations, copywriting, and decision-making. Gemini for transcription and content processing. NotebookLM for podcast generation. All integrated directly into your GoHighLevel account.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">How long does setup take?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">Most systems are live within 3-5 business days. Complex multi-system setups may take 1-2 weeks. We use AI to accelerate the build process so you're not waiting months for delivery.</p>
    </div>

    <div style="margin-bottom:24px">
      <h3 style="font-size:1rem;font-weight:700;color:var(--text);margin-bottom:8px">Do I need a GoHighLevel account?</h3>
      <p style="font-size:.95rem;color:var(--text2);line-height:1.7">Yes. We build inside your GHL account so you own everything. Don't have one yet? <a href="/trial/" style="color:var(--amber)">Start a 30-day free trial</a> and we'll set up your first system during the trial period.</p>
    </div>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:48px;margin-bottom:48px" id="contact">
    <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:800;color:var(--text);margin-bottom:8px">Get Started</h2>
    <p style="font-size:.9rem;color:var(--text2);margin-bottom:24px">Tell us what you need. We'll get back to you within 24 hours.</p>
    <form id="services-form" style="display:flex;flex-direction:column;gap:16px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px" class="form-row">
        <div>
          <label style="font-size:.78rem;font-weight:600;color:var(--text2);display:block;margin-bottom:6px">First Name</label>
          <input type="text" name="firstName" required style="width:100%;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:.9rem;font-family:var(--sans)">
        </div>
        <div>
          <label style="font-size:.78rem;font-weight:600;color:var(--text2);display:block;margin-bottom:6px">Last Name</label>
          <input type="text" name="lastName" required style="width:100%;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:.9rem;font-family:var(--sans)">
        </div>
      </div>
      <div>
        <label style="font-size:.78rem;font-weight:600;color:var(--text2);display:block;margin-bottom:6px">Email</label>
        <input type="email" name="email" required style="width:100%;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:.9rem;font-family:var(--sans)">
      </div>
      <div>
        <label style="font-size:.78rem;font-weight:600;color:var(--text2);display:block;margin-bottom:6px">Phone</label>
        <input type="tel" name="phone" style="width:100%;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:.9rem;font-family:var(--sans)">
      </div>
      <div>
        <label style="font-size:.78rem;font-weight:600;color:var(--text2);display:block;margin-bottom:6px">Which systems are you interested in?</label>
        <textarea name="services" rows="3" placeholder="e.g. AI Content Pipeline, AI Lead Follow-Up, CRM Setup" style="width:100%;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:.9rem;font-family:var(--sans);resize:vertical"></textarea>
      </div>
      <div>
        <label style="font-size:.78rem;font-weight:600;color:var(--text2);display:block;margin-bottom:6px">Tell us about your business</label>
        <textarea name="message" rows="3" placeholder="What industry, how many leads/mo, what are you trying to automate?" style="width:100%;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:.9rem;font-family:var(--sans);resize:vertical"></textarea>
      </div>
      <button type="submit" class="btn-amber" style="width:100%;text-align:center;padding:14px;font-size:.95rem;border:none;cursor:pointer">Send Inquiry &rarr;</button>
      <div id="form-status" style="font-size:.85rem;text-align:center;display:none"></div>
    </form>
  </div>

  <div style="text-align:center;margin-bottom:32px">
    <p style="font-size:.85rem;color:var(--text2)">Not ready for services? <a href="/trial/" style="color:var(--amber)">Start a free 30-day GHL trial</a>, check our <a href="/coupon/" style="color:var(--amber)">coupon page</a>, or explore our <a href="/" style="color:var(--amber)">free tutorials</a>.</p>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:32px">
    <p style="font-size:.8rem;color:var(--text3);line-height:1.7;text-align:center">GlobalHighLevel.com is an independent automation consultancy. We are not affiliated with GoHighLevel LLC or Anthropic. GoHighLevel is a registered trademark of HighLevel Inc.</p>
  </div>

</div>
<script type="application/ld+json">{faq_schema}</script>
<script type="application/ld+json">{service_schema}</script>
<script>
(function(){{
  var form=document.getElementById('services-form');
  var status=document.getElementById('form-status');
  if(!form)return;
  form.addEventListener('submit',function(e){{
    e.preventDefault();
    var data={{}};
    new FormData(form).forEach(function(v,k){{data[k]=v}});
    status.style.display='block';
    status.style.color='var(--text2)';
    status.textContent='Sending...';
    fetch('{WEBHOOK_URL}',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify(data)
    }}).then(function(r){{
      if(r.ok){{
        status.style.color='var(--amber)';
        status.textContent='Sent! We\\'ll be in touch within 24 hours.';
        form.reset();
      }}else{{
        status.style.color='#ef4444';
        status.textContent='Something went wrong. Email us instead.';
      }}
    }}).catch(function(){{
      status.style.color='#ef4444';
      status.textContent='Something went wrong. Email us instead.';
    }});
  }});
}})();
</script>"""

    html = base_html(
        title=f"{title} | {SITE_NAME}",
        description=description,
        canonical=canonical,
        body=body
    )
    write(PUBLIC_DIR / "services" / "index.html", html)


def build_404():
    body = f"""
<div style="text-align:center;padding:160px 24px 100px">
  <h1 style="font-family:var(--sans);font-size:5rem;font-weight:800;color:var(--amber);margin-bottom:8px">404</h1>
  <h2 style="font-family:var(--sans);font-size:1.5rem;font-weight:700;margin-bottom:16px;color:var(--text)">Page Not Found</h2>
  <p style="color:var(--text3);margin-bottom:32px">The page you're looking for doesn't exist.</p>
  <a href="/" class="btn-amber">Go Home</a>
</div>"""
    html = base_html("404 — Page Not Found | Global High Level", "Page not found.", f"{SITE_URL}/404", body)
    write(PUBLIC_DIR / "404.html", html)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n🔨 Building globalhighlevel.com...\n")

    # Clean public dir, then copy robots.txt from source (not from public/ which is gitignored)
    ROBOTS_SRC = BASE_DIR / "robots.txt"
    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True)
    if ROBOTS_SRC.exists():
        shutil.copy(ROBOTS_SRC, PUBLIC_DIR / "robots.txt")
    REDIRECTS_SRC = BASE_DIR / "_redirects"
    if REDIRECTS_SRC.exists():
        shutil.copy(REDIRECTS_SRC, PUBLIC_DIR / "_redirects")

    global CATEGORIES
    CATEGORIES = load_categories()

    posts     = load_posts()
    published = load_published()
    merged    = merge_data(posts, published)

    print(f"  Posts found: {len(posts)}")
    print(f"  Episodes in published.json: {len(published)}")
    print(f"  Categories: {len(CATEGORIES)}")
    print(f"  Merged: {len(merged)}\n")

    # Individual post pages
    print("Building post pages...")
    for p in merged:
        build_post_page(p, all_posts=merged)

    # Homepage (paginated) — English only
    print("\nBuilding homepage...")
    NON_ENGLISH_CATEGORIES = {"gohighlevel india", "gohighlevel en español"}
    homepage_posts = [
        p for p in merged
        if p.get("category", "").lower() not in NON_ENGLISH_CATEGORIES
        and p.get("language", "en") == "en"
    ]
    print(f"  Homepage posts (English only): {len(homepage_posts)} of {len(merged)} total")
    per_page = 18
    total_pages = max(1, -(-len(homepage_posts) // per_page))
    for page in range(1, total_pages + 1):
        build_index(homepage_posts, page=page, per_page=per_page)

    # Category pages
    print("\nBuilding category pages...")
    build_category_pages(merged)

    # Sitemap
    print("\nBuilding sitemap...")
    build_sitemap(merged)

    # Landing pages
    print("\nBuilding trial page...")
    build_trial_page()
    print("Building coupon page...")
    build_coupon_page()
    print("Building services page...")
    build_services_page()

    # llms.txt (AI discoverability)
    build_llms_txt(merged)

    # 404
    build_404()

    print(f"\n✅ Build complete — {len(merged)} posts, {total_pages} index pages\n")


if __name__ == "__main__":
    main()
