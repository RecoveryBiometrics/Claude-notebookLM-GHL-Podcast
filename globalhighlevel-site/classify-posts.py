"""
classify-posts.py — Classify all blog posts into categories using keyword matching.

Reads categories.json for keyword definitions, then updates the category field
in every posts/*.json file. Prints a summary report.

Run:  python3 classify-posts.py
"""

import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent
POSTS_DIR = BASE_DIR / "posts"
CATEGORIES_FILE = BASE_DIR / "categories.json"


def classify(title: str, categories: list[dict]) -> str:
    """Classify a post by matching keywords against the lowercased title."""
    title_lower = title.lower()
    for cat in categories:
        # Check longer keywords first (more specific matches win)
        sorted_kw = sorted(cat["keywords"], key=len, reverse=True)
        for kw in sorted_kw:
            if kw in title_lower:
                return cat["name"]
    # Fallback to last category (Agency & Platform)
    return categories[-1]["name"]


def main():
    categories = json.loads(CATEGORIES_FILE.read_text())
    print(f"Loaded {len(categories)} categories\n")

    # Classify all posts
    results = defaultdict(list)
    post_files = sorted(POSTS_DIR.glob("*.json"))

    for f in post_files:
        data = json.loads(f.read_text())
        title = data.get("title", data.get("seoTitle", ""))
        old_cat = data.get("category", "")
        new_cat = classify(title, categories)

        data["category"] = new_cat
        f.write_text(json.dumps(data, indent=2))

        results[new_cat].append(title)

    # Print report
    print(f"{'='*60}")
    print(f"CLASSIFIED {len(post_files)} POSTS")
    print(f"{'='*60}\n")

    for cat in categories:
        name = cat["name"]
        posts = results.get(name, [])
        print(f"\n{name} ({len(posts)} posts)")
        print(f"{'-'*40}")
        for t in posts:
            print(f"  {t[:70]}")

    print(f"\n{'='*60}")
    for cat in categories:
        name = cat["name"]
        count = len(results.get(name, []))
        print(f"  {name:<25} {count:>3} posts")
    print(f"  {'TOTAL':<25} {len(post_files):>3} posts")


if __name__ == "__main__":
    main()
