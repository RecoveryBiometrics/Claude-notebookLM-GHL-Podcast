"""
Lightweight language detection + URL-to-expected-language mapping.

Used by build.py, 8-seo-optimizer.py, and seo-deploy-gate to ensure pages
under /es/, /in/, /ar/ ship with meta tags written in the correct language.

No external deps — regex + stopword scoring over the 4 languages we support.
"""
import re

# Common function words that don't appear in other supported languages.
# Kept small and distinctive to avoid false positives from borrowed terms.
SPANISH_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "que", "qué", "para", "con", "por", "sin", "pero", "cómo", "aprende",
    "configurar", "guía", "guías", "tutoriales", "paso", "escalar", "tu",
    "es", "son", "está", "están", "gratis", "gratuitas", "gratuitos",
    "automatizar", "agencia", "agencias", "ventas",
}

ENGLISH_STOPWORDS = {
    "the", "and", "for", "with", "your", "free", "step", "help", "guides",
    "tutorials", "agencies", "businesses", "how", "to", "learn", "master",
    "setup", "growth", "this", "that",
}

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
SPANISH_ACCENT_RE = re.compile(r"[ñáéíóúü¿¡]", re.IGNORECASE)


def detect_language(text: str) -> str:
    """Return 'ar', 'es', or 'en'. 'en' is the fallback."""
    if not text or not text.strip():
        return "en"

    # Arabic: strong signal from Unicode block alone.
    arabic_chars = len(ARABIC_RE.findall(text))
    if arabic_chars >= 5:
        return "ar"

    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    if not words:
        return "en"

    es_hits = sum(1 for w in words if w in SPANISH_STOPWORDS)
    en_hits = sum(1 for w in words if w in ENGLISH_STOPWORDS)
    es_hits += len(SPANISH_ACCENT_RE.findall(text)) * 2  # accents weigh heavier

    if es_hits > en_hits and es_hits >= 2:
        return "es"
    return "en"


def expected_language_for_url(url_or_path: str) -> str:
    """Map a URL or path prefix to the language its meta should be written in.

    /es/*  → es
    /ar/*  → ar
    /in/*  → en  (India pages are in Indian English, not Hindi)
    else    → en
    """
    path = url_or_path.split("://", 1)[-1]
    path = "/" + path.split("/", 1)[-1] if "/" in path else path
    if path.startswith("/es/") or path == "/es":
        return "es"
    if path.startswith("/ar/") or path == "/ar":
        return "ar"
    return "en"


def classify_post_language(html_body: str, expected: str, source: str = "blog",
                           warn_fn=None) -> str:
    """Derive the `language` field for a post JSON from the body content itself.

    Source-of-truth rule: the BODY is authoritative. If the blog script's intent
    disagrees with what the content actually is, the content wins — we label it
    accurately and emit a warning so upstream prompts can be audited.
    """
    text = re.sub(r"<[^>]+>", " ", html_body or "")
    text = re.sub(r"\s+", " ", text).strip()[:3000]
    detected = detect_language(text)

    # en-IN is a dialect tag; detector returns plain "en" for Indian English.
    if expected == "en-IN" and detected == "en":
        return "en-IN"

    if detected == expected:
        return expected

    msg = (
        f"{source}: expected '{expected}' but body detects as '{detected}'. "
        f"Saving with language='{detected}' (body authoritative). Upstream prompt may be failing."
    )
    if warn_fn:
        try:
            warn_fn(source, msg, level="warning")
        except TypeError:
            warn_fn(msg)
    else:
        import sys
        print(f"[lang_check WARNING] {msg}", file=sys.stderr)
    return detected


def validate_meta(url: str, title: str, description: str) -> tuple[bool, str]:
    """Return (ok, message). ok=False means the meta doesn't match the URL's language."""
    expected = expected_language_for_url(url)
    # Only enforce non-English buckets — English is the fallback and rarely misclassified.
    if expected == "en":
        return True, ""

    desc_lang = detect_language(description)
    title_lang = detect_language(title)

    # For Arabic we also accept mixed (title can contain brand "GoHighLevel" in ASCII).
    if expected == "ar":
        if ARABIC_RE.search(description) and ARABIC_RE.search(title):
            return True, ""
        return False, f"URL {url} expects Arabic meta; detected title={title_lang}, description={desc_lang}"

    if expected == "es":
        if desc_lang == "es":
            return True, ""
        return False, f"URL {url} expects Spanish meta; detected description={desc_lang} (\"{description[:80]}...\")"

    return True, ""
