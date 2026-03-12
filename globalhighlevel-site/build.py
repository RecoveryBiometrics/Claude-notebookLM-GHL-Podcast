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

def write(path: Path, html: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print(f"  ✓ {path.relative_to(PUBLIC_DIR)}")

# ── CSS (shared across all pages) ────────────────────────────────────────────

CSS = f"""
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;font-size:16px;line-height:1.7;color:#eef2ff;background:#07080a}}
a{{color:{ACCENT};text-decoration:none}}
a:hover{{text-decoration:underline}}
img{{max-width:100%;height:auto}}

/* Header */
.site-header{{background:#0a0c12;border-bottom:1px solid #1e2433;padding:0 24px}}
.header-inner{{max-width:1140px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:64px}}
.site-logo{{font-size:1.4rem;font-weight:800;color:#eef2ff;letter-spacing:-.5px}}
.site-logo span{{color:{ACCENT};font-weight:400}}
.site-nav a{{color:#7c8aab;margin-left:24px;font-size:.9rem;font-weight:500}}
.site-nav a:hover{{color:#eef2ff;text-decoration:none}}
.nav-cta{{background:{ACCENT};color:#07080a!important;padding:8px 18px;border-radius:6px;font-weight:700!important}}
.nav-cta:hover{{background:{ACCENT_DARK}!important;text-decoration:none!important}}

/* Hero */
.hero{{background:#0a0c12;border-bottom:1px solid #1e2433;padding:72px 24px;text-align:center}}
.hero-eyebrow{{font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:{ACCENT};margin-bottom:16px}}
.hero h1{{font-size:2.8rem;font-weight:800;margin-bottom:16px;line-height:1.15;color:#eef2ff;letter-spacing:-.5px}}
.hero p{{font-size:1.1rem;color:#7c8aab;max-width:580px;margin:0 auto 32px;line-height:1.6}}
.hero-btn{{background:{ACCENT};color:#07080a;padding:14px 32px;border-radius:6px;font-weight:700;font-size:1rem;display:inline-block}}
.hero-btn:hover{{background:{ACCENT_DARK};text-decoration:none}}

/* Container */
.container{{max-width:1140px;margin:0 auto;padding:0 24px}}

/* Section */
.section{{padding:56px 0}}
.section-label{{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:{ACCENT};margin-bottom:12px}}
.section-title{{font-size:1.6rem;font-weight:700;margin-bottom:36px;color:#eef2ff}}

/* Cards grid — 3 col desktop, 2 tablet, 1 mobile */
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}}

/* Card — text-only, left amber border */
.card{{background:#111520;border:1px solid #1e2433;border-left:3px solid {ACCENT};border-radius:8px;padding:22px;transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease;display:flex;flex-direction:column}}
.card:hover{{transform:translateY(-3px);box-shadow:0 8px 28px rgba(0,0,0,.45);border-color:{ACCENT}}}
.card:hover .card-title a{{color:{ACCENT}}}

/* Category pill — amber, above title */
.card-cat{{display:inline-block;background:{ACCENT};color:#07080a;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:3px 9px;border-radius:4px;margin-bottom:10px;align-self:flex-start}}

/* Title — 2-line clamp */
.card-title{{font-size:1rem;font-weight:700;line-height:1.35;margin-bottom:10px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-title a{{color:#eef2ff;transition:color .2s}}

/* Excerpt — 2-line clamp */
.card-excerpt{{font-size:.875rem;color:#7c8aab;line-height:1.55;margin-bottom:auto;padding-bottom:16px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}

/* Meta row */
.card-meta{{font-size:.72rem;color:#3d4a63;display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding-top:14px;border-top:1px solid #1e2433;margin-top:auto}}
.meta-sep{{color:#2a3347}}

/* Podcast badge */
.podcast-badge{{display:inline-flex;align-items:center;gap:4px;background:rgba(245,158,11,.12);color:{ACCENT};font-size:.65rem;font-weight:700;padding:3px 8px;border-radius:20px;margin-left:auto}}

/* Post page */
.post-wrap{{max-width:780px;margin:0 auto;padding:48px 24px}}
.post-breadcrumb{{font-size:.8rem;color:#3d4a63;margin-bottom:24px}}
.post-breadcrumb a{{color:#7c8aab}}
.post-breadcrumb a:hover{{color:#eef2ff;text-decoration:none}}
.post-header{{margin-bottom:36px;padding-bottom:36px;border-bottom:1px solid #1e2433}}
.post-cat{{display:inline-block;background:{ACCENT};color:#07080a;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:3px 9px;border-radius:4px;margin-bottom:14px}}
.post-title{{font-size:2rem;font-weight:800;line-height:1.25;margin-bottom:16px;color:#eef2ff;letter-spacing:-.3px}}
.post-meta{{font-size:.85rem;color:#3d4a63;display:flex;gap:12px;flex-wrap:wrap}}
.post-content{{color:#c8d0e7}}
.post-content h2{{font-size:1.4rem;font-weight:700;margin:40px 0 14px;color:#eef2ff}}
.post-content h3{{font-size:1.1rem;font-weight:700;margin:28px 0 10px;color:#eef2ff}}
.post-content p{{margin-bottom:18px;line-height:1.75}}
.post-content ul,.post-content ol{{margin:0 0 18px 24px}}
.post-content li{{margin-bottom:8px}}
.post-content strong{{color:#eef2ff}}
.post-content a{{color:{ACCENT}}}
.post-content a:hover{{color:{ACCENT_DARK}}}

/* Podcast embed */
.podcast-embed{{background:#111520;border:1px solid #1e2433;border-left:3px solid {ACCENT};border-radius:8px;padding:20px;margin:36px 0}}
.podcast-embed p{{font-size:.85rem;font-weight:600;color:#7c8aab;margin-bottom:12px}}
.podcast-embed iframe{{border-radius:6px}}

/* Pagination */
.pagination{{display:flex;gap:8px;justify-content:center;margin-top:48px;flex-wrap:wrap}}
.page-btn{{padding:8px 16px;border:1px solid #1e2433;border-radius:6px;font-size:.875rem;color:#7c8aab;background:#111520}}
.page-btn.active{{background:{ACCENT};color:#07080a;border-color:{ACCENT};font-weight:700}}
.page-btn:hover{{border-color:{ACCENT};color:#eef2ff;text-decoration:none}}

/* Category header */
.cat-header{{background:#0a0c12;border-bottom:1px solid #1e2433;padding:48px 24px}}
.cat-header h1{{font-size:1.8rem;font-weight:800;margin-bottom:8px;color:#eef2ff}}
.cat-header p{{color:#7c8aab;font-size:.9rem}}

/* Footer */
.site-footer{{background:#0a0c12;border-top:1px solid #1e2433;color:#7c8aab;padding:56px 24px 28px;margin-top:80px}}
.footer-inner{{max-width:1140px;margin:0 auto}}
.footer-grid{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:48px;margin-bottom:48px}}
.footer-logo{{font-size:1.2rem;font-weight:800;color:#eef2ff}}
.footer-logo span{{color:{ACCENT}}}
.footer-brand p{{font-size:.875rem;margin-top:12px;line-height:1.65}}
.footer-col h4{{color:#eef2ff;font-size:.75rem;font-weight:700;margin-bottom:16px;text-transform:uppercase;letter-spacing:1px}}
.footer-col a{{display:block;font-size:.875rem;color:#7c8aab;margin-bottom:10px}}
.footer-col a:hover{{color:#eef2ff;text-decoration:none}}
.footer-bottom{{border-top:1px solid #1e2433;padding-top:24px;font-size:.75rem;display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;color:#3d4a63}}
.disclaimer{{font-size:.72rem;color:#3d4a63;margin-top:14px;line-height:1.6}}

@media(max-width:1024px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:640px){{
  .hero h1{{font-size:1.9rem}}
  .cards{{grid-template-columns:1fr}}
  .footer-grid{{grid-template-columns:1fr}}
  .site-nav .nav-links{{display:none}}
  .post-title{{font-size:1.5rem}}
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
<header class="site-header">
  <div class="header-inner">
    <a href="/" class="site-logo">GlobalHigh<span>Level</span></a>
    <nav class="site-nav">
      <span class="nav-links">
        <a href="/">Home</a>
        <a href="/category/gohighlevel-tutorials/">Tutorials</a>
      </span>
      <a href="{AFFILIATE}" class="nav-cta" target="_blank" rel="nofollow">Free 30-Day Trial →</a>
    </nav>
  </div>
</header>
{body}
<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-grid">
      <div>
        <div class="footer-logo">GlobalHigh<span>Level</span></div>
        <p>Free GoHighLevel tutorials, guides, and strategies for digital marketing agencies and businesses worldwide.</p>
        <p class="disclaimer">Affiliate disclosure: Some links on this site are affiliate links. If you sign up through our link, we may earn a commission at no extra cost to you.</p>
      </div>
      <div class="footer-col">
        <h4>Quick Links</h4>
        <a href="/">Home</a>
        <a href="/category/gohighlevel-tutorials/">Tutorials</a>
        <a href="{AFFILIATE}" target="_blank" rel="nofollow">Free 30-Day Trial</a>
      </div>
      <div class="footer-col">
        <h4>Resources</h4>
        <a href="https://help.gohighlevel.com" target="_blank" rel="nofollow noopener">GHL Help Center</a>
        <a href="https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12&utm_source=globalhighlevel&utm_medium=footer&utm_campaign=pricing" target="_blank" rel="nofollow noopener">GHL Pricing</a>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© {datetime.now().year} GlobalHighLevel.com — All rights reserved</span>
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

def build_post_page(post: dict):
    slug        = post["slug"]
    title       = post.get("title", post.get("seoTitle", ""))
    description = post.get("description", post.get("seoDescription", post.get("meta_description", "")))
    category    = display_cat(post.get("category", "")) or "GoHighLevel Tutorials"
    cat_slug    = slugify(category)
    date_str    = fmt_date(post.get("publishedAt", post.get("uploadedAt", "")))
    html_content = post.get("html_content", "")
    episode_id  = post.get("transistorEpisodeId", "")
    canonical   = f"{SITE_URL}/blog/{slug}/"

    podcast_html = ""
    if episode_id:
        podcast_html = f"""
<div class="podcast-embed">
  <p>🎙️ Listen to the podcast episode</p>
  <iframe width="100%" height="180" frameborder="no" scrolling="no" seamless
    src="https://share.transistor.fm/e/{episode_id}"></iframe>
</div>"""

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

    body = f"""
<div class="post-wrap">
  <div class="post-breadcrumb">
    <a href="/">Home</a> › <a href="/category/{cat_slug}/">{category}</a> › {title[:50]}
  </div>
  <header class="post-header">
    <div class="post-cat">{category}</div>
    <h1 class="post-title">{title}</h1>
    <div class="post-meta">
      <span>By William Welch</span>
      {"<span>" + date_str + "</span>" if date_str else ""}
    </div>
  </header>
  {podcast_html}
  <div class="post-content">
    {html_content}
  </div>
  <script type="application/ld+json">{article_schema}</script>
</div>"""

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
<div class="container">
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
    <h1>{cat}</h1>
    <p>{len(cat_posts)} guides and tutorials</p>
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
    body = """
<div style="text-align:center;padding:100px 24px">
  <h1 style="font-size:4rem;font-weight:800;color:#e2e8f0">404</h1>
  <h2 style="font-size:1.5rem;margin-bottom:16px">Page Not Found</h2>
  <p style="color:#6b7280;margin-bottom:32px">The page you're looking for doesn't exist.</p>
  <a href="/" style="background:#1a73e8;color:#fff;padding:12px 28px;border-radius:6px;font-weight:700">Go Home</a>
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
        build_post_page(p)

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
