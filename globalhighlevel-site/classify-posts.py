"""
classify-posts.py — Two-dimensional classifier: language + topic.

Reads categories.json (languages + topics), then for each post in posts/:
  1. Detects language from existing fields or heuristics
  2. Classifies into a topic using language-appropriate keywords
  3. Writes back only `language` and `category` fields

Run:  python3 classify-posts.py
"""

import json
import re
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent
POSTS_DIR = BASE_DIR / "posts"
CATEGORIES_FILE = BASE_DIR / "categories.json"

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def detect_language(data: dict) -> str:
    """Detect the language code for a post."""
    # 1. Explicit language field
    if data.get("language"):
        return data["language"]

    # 2. Legacy category field
    cat = data.get("category", "")
    if cat in ("GoHighLevel en Español", "GoHighLevel en Espanol"):
        return "es"
    if cat == "GoHighLevel India":
        return "en-IN"

    # 3. Arabic characters in title or slug
    title = data.get("title", "")
    slug = data.get("slug", "")
    if ARABIC_RE.search(title) or ARABIC_RE.search(slug):
        return "ar"

    # 4. Default English
    return "en"


def classify_topic(title: str, lang: str, topics: list[dict]) -> str:
    """Classify a post into a topic using language-appropriate keywords."""
    title_lower = title.lower()

    # Pick the right keyword list based on language
    if lang == "es":
        kw_field = "keywords_es"
    elif lang == "en-IN":
        kw_field = "keywords_in"
    else:
        kw_field = "keywords"

    for topic in topics:
        keywords = topic.get(kw_field, topic.get("keywords", []))
        # Check longer keywords first (more specific matches win)
        sorted_kw = sorted(keywords, key=len, reverse=True)
        for kw in sorted_kw:
            if kw in title_lower:
                return topic["name"]

    # Fallback: Agency & Platform (the catch-all)
    return "Agency & Platform"


def main():
    config = json.loads(CATEGORIES_FILE.read_text())
    languages = config["languages"]
    topics = config["topics"]

    lang_lookup = {l["code"]: l["name"] for l in languages}

    print(f"Loaded {len(languages)} languages, {len(topics)} topics\n")

    # Counters
    lang_counts = defaultdict(int)
    topic_counts = defaultdict(int)
    cross_table = defaultdict(lambda: defaultdict(int))

    post_files = sorted(POSTS_DIR.glob("*.json"))
    changed = 0

    for f in post_files:
        data = json.loads(f.read_text())
        title = data.get("title", data.get("seoTitle", ""))

        lang = detect_language(data)
        topic = classify_topic(title, lang, topics)

        # Only write if something changed
        old_lang = data.get("language", "")
        old_cat = data.get("category", "")
        if old_lang != lang or old_cat != topic:
            data["language"] = lang
            data["category"] = topic
            f.write_text(json.dumps(data, indent=2))
            changed += 1

        lang_name = lang_lookup.get(lang, lang)
        lang_counts[lang_name] += 1
        topic_counts[topic] += 1
        cross_table[lang_name][topic] += 1

    # --- Report ---
    total = len(post_files)
    print(f"{'=' * 70}")
    print(f"CLASSIFIED {total} POSTS  ({changed} files updated)")
    print(f"{'=' * 70}\n")

    # Posts per language
    print("POSTS PER LANGUAGE")
    print("-" * 40)
    for lang in languages:
        name = lang["name"]
        print(f"  {name:<20} {lang_counts[name]:>4} posts")
    print(f"  {'TOTAL':<20} {total:>4} posts\n")

    # Posts per topic
    print("POSTS PER TOPIC")
    print("-" * 40)
    for topic in topics:
        name = topic["name"]
        print(f"  {name:<25} {topic_counts[name]:>4} posts")
    print(f"  {'TOTAL':<25} {total:>4} posts\n")

    # Cross-table: language x topic
    lang_names = [l["name"] for l in languages if lang_counts[l["name"]] > 0]
    topic_names = [t["name"] for t in topics]

    # Header
    col_w = 8
    header = f"  {'Topic':<25}" + "".join(f"{n:>{col_w}}" for n in lang_names) + f"{'Total':>{col_w}}"
    print("LANGUAGE x TOPIC CROSS-TABLE")
    print("-" * len(header))
    print(header)
    print("-" * len(header))

    for tname in topic_names:
        row = f"  {tname:<25}"
        row_total = 0
        for lname in lang_names:
            c = cross_table[lname][tname]
            row_total += c
            row += f"{c:>{col_w}}"
        row += f"{row_total:>{col_w}}"
        print(row)

    # Totals row
    totals_row = f"  {'TOTAL':<25}"
    for lname in lang_names:
        totals_row += f"{lang_counts[lname]:>{col_w}}"
    totals_row += f"{total:>{col_w}}"
    print("-" * len(header))
    print(totals_row)


if __name__ == "__main__":
    main()
