#!/usr/bin/env python3
"""
indexing_api.py — Dumb CLI that pings Google Indexing API.

No judgment. No source resolution. No retry logic. Takes URLs in, emits JSONL out.

Judgment lives in the /indexing-api skill (SKILL.md). This tool only:
  1. Reads URLs from --urls args or stdin (one per line)
  2. POSTs each to https://indexing.googleapis.com/v3/urlNotifications:publish
     with body {"url": "<url>", "type": "URL_UPDATED"}
  3. Emits one JSON line per URL to stdout: {url, ts, status_code, response, error}
  4. Exits 0 if all 2xx, 1 if any non-2xx

Usage:
  python3 indexing_api.py --urls https://a.com/p1 https://a.com/p2
  printf 'https://a.com/p1\\nhttps://a.com/p2\\n' | python3 indexing_api.py
  python3 indexing_api.py --dry-run --urls https://a.com/p1

Requires SA JSON at ~/.secrets/safebath-seo-agent-c5d8ed814401.json with:
  - Indexing API enabled in the GCP project
  - SA added as Owner on the GSC property (not just User)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
import google.auth.transport.requests

KEY_PATH = Path.home() / ".secrets/safebath-seo-agent-c5d8ed814401.json"
API_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]
DELAY_MS = 150


def load_urls(args) -> list[str]:
    if args.urls:
        return [u.strip() for u in args.urls if u.strip()]
    if not sys.stdin.isatty():
        return [line.strip() for line in sys.stdin if line.strip()]
    return []


def get_auth_session():
    if not KEY_PATH.exists():
        raise SystemExit(f"ERROR: SA key not found at {KEY_PATH}")
    credentials = service_account.Credentials.from_service_account_file(
        str(KEY_PATH), scopes=SCOPES
    )
    session = google.auth.transport.requests.AuthorizedSession(credentials)
    return session


def ping_url(session, url: str) -> dict:
    body = {"url": url, "type": "URL_UPDATED"}
    try:
        resp = session.post(API_ENDPOINT, json=body, timeout=15)
        payload = {"url": url, "ts": datetime.now(timezone.utc).isoformat(),
                   "status_code": resp.status_code}
        try:
            payload["response"] = resp.json()
        except Exception:
            payload["response"] = {"raw": resp.text[:500]}
        return payload
    except Exception as e:
        return {
            "url": url,
            "ts": datetime.now(timezone.utc).isoformat(),
            "status_code": 0,
            "error": str(e),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ping Google Indexing API.")
    parser.add_argument("--urls", nargs="*", help="URLs to ping (else read from stdin)")
    parser.add_argument("--dry-run", action="store_true", help="Show URLs without pinging")
    args = parser.parse_args()

    urls = load_urls(args)
    if not urls:
        print("ERROR: no URLs supplied (use --urls or pipe stdin)", file=sys.stderr)
        return 2

    if args.dry_run:
        for url in urls:
            print(json.dumps({"url": url, "dry_run": True}))
        return 0

    session = get_auth_session()
    any_error = False
    for i, url in enumerate(urls):
        if i > 0:
            time.sleep(DELAY_MS / 1000)
        result = ping_url(session, url)
        print(json.dumps(result))
        sys.stdout.flush()
        if result.get("status_code", 0) < 200 or result.get("status_code", 0) >= 300:
            any_error = True

    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
