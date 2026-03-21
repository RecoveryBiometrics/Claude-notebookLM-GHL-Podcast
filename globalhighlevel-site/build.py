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

SITE_URL     = "https://globalhighlevel.com"
SITE_NAME    = "Global High Level"
SITE_TAGLINE = "GoHighLevel Tutorials, Guides & Strategies for Agencies Worldwide"
AFFILIATE    = "https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12&utm_source=globalhighlevel&utm_medium=site&utm_campaign=nav"

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
.nav-dropdown{{position:relative}}
.nav-dropdown-menu{{display:none;position:absolute;top:calc(100% + 8px);left:-12px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px 0;min-width:220px;z-index:300;box-shadow:0 8px 24px rgba(0,0,0,.5)}}
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
  .nav-links .nav-link{{display:none}}
  .post-title{{font-size:1.8rem}}
  .hp-lead-title{{font-size:1.8rem}}
  .cta-end{{padding:24px 20px}}
  .related-grid{{grid-template-columns:1fr}}
  .cat-header{{padding:90px 20px 36px}}
  .footer-top{{grid-template-columns:1fr;gap:32px}}
  .footer-bottom{{flex-direction:column}}
  .share-row{{flex-wrap:wrap}}
}}
"""

# ── Base template ─────────────────────────────────────────────────────────────

def base_html(title: str, description: str, canonical: str, body: str, og_image: str = "") -> str:
    og_img = og_image or "https://storage.googleapis.com/msgsndr/VL5PlkLBYG4mKk3N6PGw/media/65c56a906c059c625980d9ac.jpeg"
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
      <a href="https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV" class="nav-link" target="_blank" rel="noopener">Podcast</a>
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
<p class="cta-byline">Follow along &mdash; <a href="{AFFILIATE}&utm_campaign={slug}" target="_blank" rel="nofollow noopener">get 30 days free &rarr;</a></p>"""

    # ── CTA #2 — Mid-article inline ───────────────────────────────────────────
    cta_mid = f"""
<p class="cta-inline">This is built into GoHighLevel.
<a href="{AFFILIATE}&utm_campaign={slug}" target="_blank" rel="nofollow noopener">Try it free for 30 days &rarr;</a></p>"""
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
          <a href="{AFFILIATE}&utm_campaign=sidebar" class="btn-amber" style="display:block;text-align:center;font-size:.8rem" target="_blank" rel="nofollow noopener">Start Free Trial</a>
          <div class="s-fine">No credit card required</div>
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

    # Homepage (paginated)
    print("\nBuilding homepage...")
    per_page = 18
    total_pages = max(1, -(-len(merged) // per_page))
    for page in range(1, total_pages + 1):
        build_index(merged, page=page, per_page=per_page)

    # Category pages
    print("\nBuilding category pages...")
    build_category_pages(merged)

    # Sitemap
    print("\nBuilding sitemap...")
    build_sitemap(merged)

    # llms.txt (AI discoverability)
    build_llms_txt(merged)

    # 404
    build_404()

    print(f"\n✅ Build complete — {len(merged)} posts, {total_pages} index pages\n")


if __name__ == "__main__":
    main()
