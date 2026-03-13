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
HOMEPAGE_HERO  = BASE_DIR / "homepage_hero.html"

SITE_URL     = "https://globalhighlevel.com"
SITE_NAME    = "Global High Level"
SITE_TAGLINE = "GoHighLevel Tutorials, Guides & Strategies for Agencies Worldwide"
AFFILIATE    = "https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12&utm_source=globalhighlevel&utm_medium=site&utm_campaign=nav"

ACCENT       = "#f59e0b"   # amber
ACCENT_DARK  = "#d97706"

# ── Helpers ───────────────────────────────────────────────────────────────────

# Categories that bleed through from CMS and mean nothing to readers
_BAD_CATS = {"home", "uncategorized", "blog", "general", ""}

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", text.lower().replace(" ", "-"))

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

def inject_inline_ctas(html: str, cta2: str, cta3: str) -> str:
    """Inject two inline CTAs at roughly the 50% and 75% H2 boundaries."""
    h2_positions = [m.start() for m in re.finditer(r'<h2', html)]
    n = len(h2_positions)
    if n < 2:
        return html
    mid  = h2_positions[n // 2]
    late = h2_positions[(3 * n) // 4]
    # Insert from end to front so positions stay valid
    result = html[:late] + cta3 + html[late:]
    result = result[:mid] + cta2 + result[mid:]
    return result

def get_related(post: dict, all_posts: list, n: int = 3) -> list:
    """Return n related posts — same category first, then most recent."""
    slug = post.get("slug", "")
    cat  = post.get("category", "")
    same = [p for p in all_posts if p.get("slug") != slug and p.get("category") == cat]
    other = [p for p in all_posts if p.get("slug") != slug and p.get("category") != cat]
    return (same + other)[:n]

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

# ── CSS (shared across all post/category/404 pages) ─────────────────────────

CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap');

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
  --max:1060px;
  --serif:'Instrument Serif',Georgia,serif;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:16px;line-height:1.7;color:var(--text);background:var(--bg);overflow-x:hidden;-webkit-font-smoothing:antialiased}}
a{{color:var(--amber);text-decoration:none}}
a:hover{{text-decoration:underline}}
img{{max-width:100%;height:auto}}

/* ANIMATIONS */
@keyframes fadeUp{{from{{opacity:0;transform:translateY(20px)}}to{{opacity:1;transform:translateY(0)}}}}
.fade-1{{animation:fadeUp .6s ease both}}
.fade-2{{animation:fadeUp .6s .15s ease both}}
.fade-3{{animation:fadeUp .6s .3s ease both}}
.fade-4{{animation:fadeUp .6s .45s ease both}}

/* NAV — fixed, backdrop blur, matching homepage */
nav{{position:fixed;top:0;inset-x:0;z-index:200;background:rgba(7,8,10,0.8);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid var(--border)}}
.nav-inner{{max-width:var(--max);margin:0 auto;padding:0 24px;height:62px;display:flex;align-items:center;justify-content:space-between}}
.logo{{font-family:var(--serif);font-size:1.25rem;letter-spacing:-.3px;display:flex;align-items:center;gap:6px;color:var(--text)}}
.logo-amber{{color:var(--amber)}}
.nav-links{{display:flex;align-items:center;gap:28px}}
.nav-link{{font-size:.82rem;color:var(--text2);letter-spacing:.1px;transition:color .15s}}
.nav-link:hover{{color:var(--text);text-decoration:none}}
.nav-cta{{font-size:.82rem;font-weight:600;color:#000;background:var(--amber);padding:8px 18px;border-radius:6px;transition:background .15s}}
.nav-cta:hover{{background:var(--amber-light);text-decoration:none}}

/* Container */
.container{{max-width:var(--max);margin:0 auto;padding:0 24px}}

/* Section */
.section{{padding:56px 0}}
.section-label{{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:var(--amber);margin-bottom:12px}}
.section-title{{font-family:var(--serif);font-size:1.6rem;font-weight:400;margin-bottom:36px;color:var(--text)}}

/* Cards grid — 3 col desktop, 2 tablet, 1 mobile */
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}}

/* Card — text-only, left amber border */
.card{{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--amber);border-radius:8px;padding:22px;transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease;display:flex;flex-direction:column}}
.card:hover{{transform:translateY(-3px);box-shadow:0 8px 28px rgba(0,0,0,.45);border-color:var(--amber)}}
.card:hover .card-title a{{color:var(--amber)}}

/* Category pill */
.card-cat{{display:inline-block;background:var(--amber);color:#07080a;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:3px 9px;border-radius:4px;margin-bottom:10px;align-self:flex-start}}

/* Title — 2-line clamp */
.card-title{{font-size:1rem;font-weight:700;line-height:1.35;margin-bottom:10px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-title a{{color:var(--text);transition:color .2s}}

/* Excerpt — 2-line clamp */
.card-excerpt{{font-size:.875rem;color:var(--text2);line-height:1.55;margin-bottom:auto;padding-bottom:16px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}

/* Meta row */
.card-meta{{font-size:.72rem;color:var(--text3);display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding-top:14px;border-top:1px solid var(--border);margin-top:auto}}
.meta-sep{{color:var(--text3)}}

/* Podcast badge */
.podcast-badge{{display:inline-flex;align-items:center;gap:4px;background:var(--amber-dim);color:var(--amber);font-size:.65rem;font-weight:700;padding:3px 8px;border-radius:20px;margin-left:auto}}

/* ── Reading progress bar ─────────────────────────────────────────────────── */
#reading-progress{{position:fixed;top:0;left:0;height:3px;width:0;background:var(--amber);z-index:9999;transition:width .1s linear}}

/* ── Post page layout (2-col desktop) ────────────────────────────────────── */
.post-container{{max-width:var(--max);margin:0 auto;padding:110px 24px 48px;display:grid;grid-template-columns:1fr 280px;gap:48px;align-items:start}}
.post-main{{min-width:0}}

/* Breadcrumb */
.post-breadcrumb{{font-size:.8rem;color:var(--text3);margin-bottom:24px}}
.post-breadcrumb a{{color:var(--text2);transition:color .15s}}
.post-breadcrumb a:hover{{color:var(--text);text-decoration:none}}
.post-breadcrumb .bc-sep{{margin:0 8px;color:var(--text3);opacity:.5}}

/* Post header */
.post-eyebrow{{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:var(--amber);margin-bottom:12px}}
.post-title{{font-family:var(--serif);font-size:clamp(1.8rem,4vw,2.6rem);font-weight:400;line-height:1.15;color:var(--text);letter-spacing:-.3px;margin-bottom:20px}}
.post-byline{{display:flex;align-items:center;gap:10px;font-size:.8rem;color:var(--text3);padding-bottom:24px;border-bottom:1px solid var(--border);margin-bottom:32px;flex-wrap:wrap}}
.post-byline .sep{{color:var(--text3);opacity:.4}}

/* Post body typography */
.post-body{{font-size:17px;line-height:1.75;color:#e5e7eb}}
.post-body h2{{font-family:var(--serif);font-size:1.5rem;font-weight:400;color:var(--text);margin:48px 0 14px}}
.post-body h3{{font-size:1.15rem;font-weight:600;color:#f3f4f6;margin:32px 0 10px}}
.post-body p{{margin-bottom:20px}}
.post-body ul,.post-body ol{{margin:0 0 20px 24px}}
.post-body li{{margin-bottom:8px}}
.post-body strong{{color:#fff}}
.post-body a{{color:var(--amber);text-decoration:underline;text-underline-offset:3px}}
.post-body a:hover{{color:var(--amber-light)}}

/* ── LIGHT-MODE INLINE STYLE OVERRIDES ────────────────────────────────────── */
/* Blog HTML content comes with hardcoded inline styles from 5-blog.py.
   These use !important to override inline style="..." attributes.           */

/* Override blue links inline-styled with color:#1a73e8 */
.post-body a[style*="color:#1a73e8"],
.post-body a[style*="color: #1a73e8"]{{
  color:var(--amber)!important;
}}
.post-body a[style*="color:#1a73e8"]:hover,
.post-body a[style*="color: #1a73e8"]:hover{{
  color:var(--amber-light)!important;
}}

/* Override light background boxes: #f0f4ff, #f8f9fa, #fff8e1, #fff, #ffffff */
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

/* Override blue solid backgrounds used in CTA blocks */
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

/* Override CTA buttons styled with background:#ffffff on blue */
.post-body a[style*="background:#ffffff"],
.post-body a[style*="background: #ffffff"],
.post-body a[style*="background:#fff"],
.post-body a[style*="background: #fff"]{{
  background:var(--amber)!important;
  color:#000!important;
}}

/* Override inline blue borders */
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

/* Override FAQ section: #f8f9fa bg with blue h3 */
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

/* Override any heading with inline color:#1a73e8 */
.post-body h2[style*="color:#1a73e8"],
.post-body h3[style*="color:#1a73e8"],
.post-body h4[style*="color:#1a73e8"]{{
  color:var(--amber)!important;
}}

/* Override inline color on paragraphs/spans */
.post-body p[style*="color:#1a73e8"],
.post-body span[style*="color:#1a73e8"],
.post-body p[style*="color:#333"],
.post-body span[style*="color:#333"],
.post-body p[style*="color:#000"],
.post-body span[style*="color:#000"]{{
  color:var(--text2)!important;
}}

/* Override CTA button backgrounds that are inline blue */
.post-body a[style*="background:#1a73e8"],
.post-body a[style*="background: #1a73e8"]{{
  background:var(--amber)!important;
  color:#000!important;
}}

/* General catch: any div in post-body with padding and border-radius looks like a box */
.post-body div[style*="border-radius"]{{
  color:var(--text2);
}}

/* ── END LIGHT-MODE OVERRIDES ─────────────────────────────────────────────── */

/* TOC */
.toc{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px 24px;margin:0 0 32px}}
.toc-label{{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:var(--text3);margin-bottom:12px}}
.toc ol{{margin:0;padding-left:18px}}
.toc li{{font-size:.9rem;line-height:1.9}}
.toc a{{color:var(--text2);text-decoration:none}}
.toc a:hover{{color:var(--amber);text-decoration:none}}

/* CTA boxes */
.cta-intro{{background:var(--bg2);border:1px solid var(--amber-border);border-left:4px solid var(--amber);border-radius:8px;padding:22px 26px;margin:0 0 32px}}
.cta-intro .cta-headline{{font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--amber);margin-bottom:8px}}
.cta-intro p{{font-size:.9rem;color:var(--text2);margin:0 0 16px;line-height:1.6}}
.cta-inline{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px 18px;margin:28px 0;font-size:.875rem;color:var(--text2);display:block}}
.cta-inline a{{color:var(--amber);font-weight:600;text-decoration:none}}
.cta-inline a:hover{{color:var(--amber-light)}}
.cta-end{{background:linear-gradient(135deg,var(--surface) 0%,var(--bg2) 100%);border:1px solid var(--amber-border);border-radius:12px;padding:36px 40px;text-align:center;margin:48px 0}}
.cta-end h3{{font-family:var(--serif);font-size:1.35rem;font-weight:400;color:var(--text);margin-bottom:12px}}
.cta-end p{{font-size:.9rem;color:var(--text2);margin:0 0 24px;max-width:440px;margin-left:auto;margin-right:auto}}
.cta-end .fine{{font-size:.75rem;color:var(--text3);margin-top:12px}}
.btn-amber{{display:inline-flex;align-items:center;gap:8px;background:var(--amber);color:#000;font-size:.9rem;font-weight:700;padding:13px 26px;border-radius:7px;transition:all .2s;text-decoration:none;box-shadow:0 4px 24px rgba(245,158,11,.25)}}
.btn-amber:hover{{background:var(--amber-light);box-shadow:0 4px 32px rgba(245,158,11,.4);transform:translateY(-1px);text-decoration:none}}

/* Pro tip callout */
.callout{{border-left:3px solid var(--amber);border-radius:0 6px 6px 0;padding:14px 18px;margin:28px 0}}
.callout-tip{{background:var(--amber-dim)}}
.callout-note{{background:rgba(59,130,246,.08);border-left-color:#3b82f6}}
.callout-label{{font-size:.65rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--amber);margin-bottom:6px}}
.callout-note .callout-label{{color:#3b82f6}}
.callout p{{font-size:.9rem;color:#d1d5db;margin:0;line-height:1.65}}

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
.related-label{{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:var(--text3);margin-bottom:18px}}
.related-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.related-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;text-decoration:none;display:block;transition:border-color .2s}}
.related-card:hover{{border-color:var(--amber);text-decoration:none}}
.related-card .r-tag{{font-size:.65rem;font-weight:700;color:var(--amber);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}}
.related-card .r-title{{font-size:.85rem;font-weight:600;color:#e5e7eb;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}

/* Sidebar */
.post-sidebar{{}}
.sidebar-cta{{position:sticky;top:90px;background:var(--surface);border:1px solid var(--amber-border);border-radius:10px;padding:22px 18px;text-align:center}}
.sidebar-cta .s-headline{{font-size:.95rem;font-weight:700;color:var(--text);margin-bottom:8px}}
.sidebar-cta .s-sub{{font-size:.8rem;color:var(--text2);margin-bottom:16px;line-height:1.5}}
.sidebar-cta .s-fine{{font-size:.7rem;color:var(--text3);margin-top:10px}}

/* Pagination */
.pagination{{display:flex;gap:8px;justify-content:center;margin-top:48px;flex-wrap:wrap}}
.page-btn{{padding:8px 16px;border:1px solid var(--border);border-radius:6px;font-size:.875rem;color:var(--text2);background:var(--surface)}}
.page-btn.active{{background:var(--amber);color:#07080a;border-color:var(--amber);font-weight:700}}
.page-btn:hover{{border-color:var(--amber);color:var(--text);text-decoration:none}}

/* Category header */
.cat-header{{background:var(--bg2);border-bottom:1px solid var(--border);padding:110px 24px 48px}}
.cat-header h1{{font-family:var(--serif);font-size:1.8rem;font-weight:400;margin-bottom:8px;color:var(--text)}}
.cat-header p{{color:var(--text2);font-size:.9rem}}

/* Hero (fallback, only used when homepage_hero.html is missing) */
.hero{{background:var(--bg2);border-bottom:1px solid var(--border);padding:72px 24px;text-align:center}}
.hero-eyebrow{{font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:var(--amber);margin-bottom:16px}}
.hero h1{{font-family:var(--serif);font-size:2.8rem;font-weight:400;margin-bottom:16px;line-height:1.15;color:var(--text);letter-spacing:-.5px}}
.hero p{{font-size:1.1rem;color:var(--text2);max-width:580px;margin:0 auto 32px;line-height:1.6}}
.hero-btn{{background:var(--amber);color:#07080a;padding:14px 32px;border-radius:6px;font-weight:700;font-size:1rem;display:inline-block}}
.hero-btn:hover{{background:var(--amber-light);text-decoration:none}}

/* Footer — matching homepage */
footer{{border-top:1px solid var(--border);padding:56px 24px 36px;margin-top:80px}}
.footer-inner{{max-width:var(--max);margin:0 auto}}
.footer-top{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:48px;margin-bottom:48px}}
.footer-logo{{font-family:var(--serif);font-size:1.2rem;margin-bottom:12px;color:var(--text)}}
.footer-logo span{{color:var(--amber)}}
.footer-desc{{font-size:.82rem;color:var(--text3);line-height:1.7;margin-bottom:14px}}
.footer-disclaimer{{font-size:.74rem;color:var(--text3);line-height:1.6;opacity:.7}}
.footer-col h4{{font-size:.76rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--text2);margin-bottom:16px}}
.footer-col a{{display:block;font-size:.85rem;color:var(--text2);margin-bottom:10px;transition:color .15s}}
.footer-col a:hover{{color:var(--text);text-decoration:none}}
.footer-bottom{{border-top:1px solid var(--border);padding-top:24px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-size:.76rem;color:var(--text3)}}

@media(max-width:1024px){{
  .cards{{grid-template-columns:repeat(2,1fr)}}
  .post-container{{grid-template-columns:1fr;padding-top:90px}}
  .post-sidebar{{display:none}}
  .related-grid{{grid-template-columns:repeat(2,1fr)}}
}}
@media(max-width:640px){{
  .hero h1{{font-size:1.9rem}}
  .cards{{grid-template-columns:1fr}}
  .footer-top{{grid-template-columns:1fr;gap:32px}}
  .nav-links .nav-link{{display:none}}
  .post-title{{font-size:1.6rem}}
  .cta-end{{padding:24px 20px}}
  .related-grid{{grid-template-columns:1fr}}
  .cat-header{{padding:90px 20px 36px}}
  .footer-bottom{{flex-direction:column}}
}}
"""

# ── Base template ─────────────────────────────────────────────────────────────

def base_html(title: str, description: str, canonical: str, body: str, og_image: str = "") -> str:
    og_img = og_image or "https://storage.googleapis.com/msgsndr/VL5PlkLBYG4mKk3N6PGw/media/65c56a906c059c625980d9ac.jpeg"
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
      <a href="/category/gohighlevel-tutorials/" class="nav-link">Tutorials</a>
      <a href="{AFFILIATE}" class="nav-cta" target="_blank" rel="nofollow noopener">Free 30-Day Trial →</a>
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
        <h4>Site</h4>
        <a href="/">Home</a>
        <a href="/category/gohighlevel-tutorials/">Tutorials</a>
        <a href="{AFFILIATE}" target="_blank" rel="nofollow noopener">Free 30-Day Trial</a>
      </div>
      <div class="footer-col">
        <h4>Resources</h4>
        <a href="https://help.gohighlevel.com" target="_blank" rel="noopener">GHL Help Center</a>
        <a href="https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12&utm_source=globalhighlevel&utm_medium=footer&utm_campaign=pricing" target="_blank" rel="nofollow noopener">GHL Pricing & Plans</a>
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

    # ── Podcast section — always show Spotify link; embed player if episode exists ──
    if episode_id:
        podcast_html = f"""
<div class="podcast-embed">
  <p>🎙 Listen to this episode</p>
  <iframe width="100%" height="180" frameborder="no" scrolling="no" seamless
    src="https://share.transistor.fm/e/{episode_id}" loading="lazy"></iframe>
  <a class="podcast-link" href="https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV" target="_blank" rel="noopener">
    Follow the podcast on Spotify →
  </a>
</div>"""
    else:
        podcast_html = f"""
<div class="podcast-embed">
  <p>🎙 This tutorial also has a podcast episode</p>
  <a class="podcast-link" href="https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV" target="_blank" rel="noopener">
    Listen on Spotify — "Go High Level" podcast →
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

    # ── Inline CTAs (#2 and #3) ────────────────────────────────────────────────
    cta2 = f"""
<p class="cta-inline">This is exactly the kind of workflow GoHighLevel handles natively.
<a href="{AFFILIATE}&utm_campaign={slug}" target="_blank" rel="nofollow noopener">Try it free for 30 days →</a></p>"""
    cta3 = f"""
<p class="cta-inline">Every feature covered in this guide is included in the free trial — no credit card required.
<a href="{AFFILIATE}&utm_campaign={slug}" target="_blank" rel="nofollow noopener">Start your trial here →</a></p>"""
    body_with_ctas = inject_inline_ctas(html_content, cta2, cta3)

    # ── CTA #1 — Post intro box ────────────────────────────────────────────────
    cta1 = f"""
<div class="cta-intro">
  <div class="cta-headline">Want to follow along?</div>
  <p>GoHighLevel gives you 30 days free — full access, no credit card. Set up everything in this guide inside your trial.</p>
  <a href="{AFFILIATE}&utm_campaign={slug}" class="btn-amber" target="_blank" rel="nofollow noopener">Start Your Free 30-Day Trial →</a>
</div>"""

    # ── CTA #4 — End of article ────────────────────────────────────────────────
    cta4 = f"""
<div class="cta-end">
  <h3>Ready to put this into practice?</h3>
  <p>Start your free 30-day GoHighLevel trial — full access to every feature covered in this guide.</p>
  <a href="{AFFILIATE}&utm_campaign={slug}" class="btn-amber" target="_blank" rel="nofollow noopener">Start Free Trial — 30 Days</a>
  <div class="fine">30 days free · No credit card required</div>
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

    # ── Sidebar ────────────────────────────────────────────────────────────────
    sidebar_html = f"""
<aside class="post-sidebar">
  <div class="sidebar-cta">
    <div class="s-headline">Try GoHighLevel Free</div>
    <div class="s-sub">30 days full access — set up everything in this guide at no cost.</div>
    <a href="{AFFILIATE}&utm_campaign={slug}" class="btn-amber" style="display:block;text-align:center" target="_blank" rel="nofollow noopener">Start Free Trial →</a>
    <div class="s-fine">No credit card required</div>
  </div>
</aside>"""

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
  <main class="post-main">
    <div class="post-breadcrumb fade-1">
      <a href="/">Home</a><span class="bc-sep">›</span><a href="/category/{cat_slug}/">{category}</a><span class="bc-sep">›</span><span>{truncate(title, 50)}</span>
    </div>
    <div class="post-eyebrow fade-1"><a href="/category/{cat_slug}/" style="color:var(--amber);text-decoration:none">{category}</a></div>
    <h1 class="post-title fade-2">{title}</h1>
    <div class="post-byline fade-3">
      <span>By William Welch</span>
      {"<span class='sep'>·</span><span>" + date_str + "</span>" if date_str else ""}
      <span class="sep">·</span><span>{rtime}</span>
    </div>
    {cta1}
    {toc_html}
    {podcast_html}
    <div class="post-body">{body_with_ctas}</div>
    {cta4}
    {author_html}
    {related_html}
  </main>
  {sidebar_html}
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

    cards_html = ""
    for p in page_posts:
        slug     = p.get("slug", "")
        title    = p.get("title", p.get("seoTitle", "Untitled"))
        desc     = truncate(p.get("description", p.get("seoDescription", p.get("meta_description", ""))), 130)
        cat      = display_cat(p.get("category", ""))
        date_str = fmt_date(p.get("publishedAt", p.get("uploadedAt", "")))
        ep_id    = p.get("transistorEpisodeId", "")
        rtime    = read_time(p.get("html_content", desc))
        cat_html = f'<span class="card-cat">{cat}</span>' if cat else ""
        podcast  = '<span class="podcast-badge">🎙 Podcast</span>' if ep_id else ""

        cards_html += f"""
<article class="card">
  {cat_html}
  <h2 class="card-title"><a href="/blog/{slug}/">{title}</a></h2>
  <p class="card-excerpt">{desc}</p>
  <div class="card-meta">
    <span class="card-date">{date_str}</span>
    {"<span class='meta-sep'>·</span><span>" + rtime + "</span>" if date_str else ""}
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

    if page == 1 and HOMEPAGE_HERO.exists():
        # homepage_hero.html is <style>...</style> + raw body HTML (no doctype/html/head/body tags).
        # Split style from body content and wrap in a proper HTML document.
        hero_raw = HOMEPAGE_HERO.read_text(encoding="utf-8")

        # Extract the <style> block (everything inside the first <style>...</style>)
        style_match = re.search(r'<style>(.*?)</style>', hero_raw, re.DOTALL)
        hero_style = style_match.group(0) if style_match else ""
        # Body content = everything after the closing </style>
        hero_body = hero_raw[style_match.end():].strip() if style_match else hero_raw

        # Inject real post cards into tutorials-grid if posts exist
        if cards_html and 'id="tutorials-grid"' in hero_body:
            grid_block = f'<div id="tutorials-grid" class="tutorials-grid">\n{cards_html}\n</div>'
            hero_body = re.sub(
                r'<div id="tutorials-grid"[^>]*>.*?</div>',
                grid_block,
                hero_body,
                flags=re.DOTALL
            )

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{SITE_NAME} — {SITE_TAGLINE}</title>
<meta name="description" content="Free GoHighLevel tutorials, guides, and strategies for digital marketing agencies worldwide. Learn GHL step by step.">
<link rel="canonical" href="{SITE_URL}/">
<meta property="og:title" content="{SITE_NAME} — {SITE_TAGLINE}">
<meta property="og:description" content="Free GoHighLevel tutorials, guides, and strategies for digital marketing agencies worldwide.">
<meta property="og:url" content="{SITE_URL}/">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
{hero_style}
</head>
<body>
{hero_body}
</body>
</html>"""
        write(PUBLIC_DIR / "index.html", full_html)
        return

    if page == 1:
        hero = f"""
<div class="hero">
  <div class="hero-eyebrow">Free GoHighLevel Tutorials</div>
  <h1>Everything You Need to Master GoHighLevel</h1>
  <p>Step-by-step guides for agencies and businesses. Updated daily.</p>
  <a href="{AFFILIATE}" class="hero-btn" target="_blank" rel="nofollow noopener">Start Your Free 30-Day Trial →</a>
</div>"""
    else:
        hero = ""

    body = f"""{hero}
<div class="container" style="padding-top:{'80px' if page > 1 else '0'}">
  <div class="section">
    <div class="section-label">Tutorials</div>
    <div class="section-title">{"Latest Guides & Tutorials" if page == 1 else f"Page {page}"}</div>
    <div class="cards">{cards_html}</div>
    {pages_html}
  </div>
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
        cat = p.get("category", "GoHighLevel Tutorials")
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
            cat_html  = f'<span class="card-cat">{cat_label}</span>' if cat_label else ""
            podcast   = '<span class="podcast-badge">🎙 Podcast</span>' if ep_id else ""
            cards_html += f"""
<article class="card">
  {cat_html}
  <h2 class="card-title"><a href="/blog/{slug}/">{title}</a></h2>
  <p class="card-excerpt">{desc}</p>
  <div class="card-meta">
    <span class="card-date">{date_str}</span>
    {"<span class='meta-sep'>·</span><span>" + rtime + "</span>" if date_str else ""}
    {podcast}
  </div>
</article>"""

        body = f"""
<div class="cat-header">
  <div class="container">
    <div class="section-label fade-1">Category</div>
    <h1 class="fade-2">{cat}</h1>
    <p class="fade-3">{len(cat_posts)} guides and tutorials</p>
  </div>
</div>
<div class="container">
  <div class="section">
    <div class="cards">{cards_html}</div>
  </div>
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
  <h1 style="font-family:var(--serif);font-size:5rem;font-weight:400;color:var(--amber);margin-bottom:8px">404</h1>
  <h2 style="font-family:var(--serif);font-size:1.5rem;font-weight:400;margin-bottom:16px;color:var(--text)">Page Not Found</h2>
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

    posts     = load_posts()
    published = load_published()
    merged    = merge_data(posts, published)

    print(f"  Posts found: {len(posts)}")
    print(f"  Episodes in published.json: {len(published)}")
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
