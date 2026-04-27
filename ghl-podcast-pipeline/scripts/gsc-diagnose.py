"""
gsc-diagnose.py
One-off: pull GSC day-by-day for the last 10 days, find the crash day,
and show which pages/queries/countries lost the most impressions.

Run: venv/bin/python3 scripts/gsc-diagnose.py
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
GSC_TOKEN_FILE = BASE_DIR / "token-gsc.json"
CREDENTIALS_FILE = BASE_DIR / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GSC_SITE_URL = "sc-domain:globalhighlevel.com"


def get_gsc_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if GSC_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(GSC_TOKEN_FILE), GSC_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            gsc_creds_file = BASE_DIR / "credentials-gsc.json"
            if not gsc_creds_file.exists():
                gsc_creds_file = CREDENTIALS_FILE
            flow = InstalledAppFlow.from_client_secrets_file(str(gsc_creds_file), GSC_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GSC_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("searchconsole", "v1", credentials=creds)


def query(service, body):
    return service.searchanalytics().query(siteUrl=GSC_SITE_URL, body=body).execute()


def main():
    service = get_gsc_service()
    end = datetime.now().date()
    start = end - timedelta(days=10)

    print(f"\nGSC site: {GSC_SITE_URL}")
    print(f"Window: {start} → {end} (GSC has ~2-3 day lag, latest days will be empty/partial)\n")

    # ---- Day-by-day totals ----
    daily = query(service, {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["date"],
        "rowLimit": 30,
    })

    rows = sorted(daily.get("rows", []), key=lambda r: r["keys"][0])
    print("=" * 70)
    print(f"{'DATE':<12} {'CLICKS':>8} {'IMPR':>10} {'CTR%':>7} {'POS':>6}   Δ-impr")
    print("=" * 70)
    prev = None
    for r in rows:
        d = r["keys"][0]
        c = r.get("clicks", 0)
        i = r.get("impressions", 0)
        ctr = round(r.get("ctr", 0) * 100, 1)
        pos = round(r.get("position", 0), 1)
        delta = ""
        if prev is not None:
            diff = i - prev
            pct = (diff / prev * 100) if prev else 0
            delta = f"  {diff:+d} ({pct:+.0f}%)"
        print(f"{d:<12} {c:>8} {i:>10} {ctr:>7} {pos:>6}{delta}")
        prev = i

    if len(rows) < 2:
        print("\nNot enough days returned to diagnose.")
        return

    # Find the steepest drop
    biggest_drop = None
    for i in range(1, len(rows)):
        prev_i = rows[i - 1].get("impressions", 0)
        cur_i = rows[i].get("impressions", 0)
        diff = cur_i - prev_i
        if biggest_drop is None or diff < biggest_drop[0]:
            biggest_drop = (diff, rows[i - 1]["keys"][0], rows[i]["keys"][0], prev_i, cur_i)

    diff, day_before, drop_day, prev_i, cur_i = biggest_drop
    print(f"\nSteepest drop: {day_before} → {drop_day}")
    print(f"  {prev_i} → {cur_i} impressions ({diff:+d}, {diff/prev_i*100 if prev_i else 0:+.1f}%)\n")

    # ---- Compare top pages: day_before vs drop_day ----
    def pages_for(date_str):
        resp = query(service, {
            "startDate": date_str,
            "endDate": date_str,
            "dimensions": ["page"],
            "rowLimit": 200,
        })
        return {r["keys"][0]: r.get("impressions", 0) for r in resp.get("rows", [])}

    before_pages = pages_for(day_before)
    after_pages = pages_for(drop_day)

    all_pages = set(before_pages) | set(after_pages)
    page_diffs = []
    for p in all_pages:
        b = before_pages.get(p, 0)
        a = after_pages.get(p, 0)
        page_diffs.append((a - b, p, b, a))
    page_diffs.sort()  # most negative first

    print("=" * 70)
    print(f"TOP 15 PAGES THAT LOST IMPRESSIONS ({day_before} → {drop_day})")
    print("=" * 70)
    print(f"{'Δ':>8} {'BEFORE':>8} {'AFTER':>8}   PAGE")
    for diff_p, p, b, a in page_diffs[:15]:
        if diff_p >= 0:
            break
        page_short = p.replace("https://globalhighlevel.com", "") or "/"
        if len(page_short) > 55:
            page_short = page_short[:52] + "..."
        print(f"{diff_p:+8d} {b:>8} {a:>8}   {page_short}")

    # ---- Compare top queries ----
    def queries_for(date_str):
        resp = query(service, {
            "startDate": date_str,
            "endDate": date_str,
            "dimensions": ["query"],
            "rowLimit": 200,
        })
        return {r["keys"][0]: r.get("impressions", 0) for r in resp.get("rows", [])}

    before_q = queries_for(day_before)
    after_q = queries_for(drop_day)
    all_q = set(before_q) | set(after_q)
    q_diffs = sorted([(after_q.get(q, 0) - before_q.get(q, 0), q, before_q.get(q, 0), after_q.get(q, 0)) for q in all_q])

    print(f"\n{'=' * 70}")
    print(f"TOP 15 QUERIES THAT LOST IMPRESSIONS ({day_before} → {drop_day})")
    print("=" * 70)
    print(f"{'Δ':>8} {'BEFORE':>8} {'AFTER':>8}   QUERY")
    for diff_q, q, b, a in q_diffs[:15]:
        if diff_q >= 0:
            break
        q_short = q if len(q) <= 55 else q[:52] + "..."
        print(f"{diff_q:+8d} {b:>8} {a:>8}   {q_short}")

    # ---- Country-level on the drop day vs day before ----
    def country_for(date_str):
        resp = query(service, {
            "startDate": date_str,
            "endDate": date_str,
            "dimensions": ["country"],
            "rowLimit": 50,
        })
        return {r["keys"][0]: r.get("impressions", 0) for r in resp.get("rows", [])}

    before_c = country_for(day_before)
    after_c = country_for(drop_day)
    all_c = set(before_c) | set(after_c)
    c_diffs = sorted([(after_c.get(c, 0) - before_c.get(c, 0), c, before_c.get(c, 0), after_c.get(c, 0)) for c in all_c])

    print(f"\n{'=' * 70}")
    print(f"COUNTRY MIX ({day_before} → {drop_day}) — top 10 movers")
    print("=" * 70)
    print(f"{'Δ':>8} {'BEFORE':>8} {'AFTER':>8}   COUNTRY")
    for diff_c, c, b, a in c_diffs[:10]:
        print(f"{diff_c:+8d} {b:>8} {a:>8}   {c}")


if __name__ == "__main__":
    main()
