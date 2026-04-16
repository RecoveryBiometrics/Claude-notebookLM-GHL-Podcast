"""
verticals_measure.py

Daily measurement loop for shipped vertical URLs. Reads shipped rows from the
Verticals Queue Sheet tab (the single source of truth), pulls GSC data per URL,
writes metrics back to the Sheet, and posts a narrative-English digest to Slack
#globalhighlevel. Fires a DECISION GATE at Day 14, and an 8-week winning-metric
check at Day 56.

Sheet: GlobalHighLevel Tracker (1A2eD2LeBpWFjDMe6W9BZbN6FvfW-em_7gD002pJD7_E)
  - Verticals Queue tab: reads status=shipped rows, writes position/ctr/affiliate_clicks_14d
  - Columns: vertical | tier | part | language | status | shipped_date | url | position | ctr | affiliate_clicks_14d

Usage:
  venv/bin/python3 scripts/verticals_measure.py            # real run, post to Slack, write Sheet
  venv/bin/python3 scripts/verticals_measure.py --dry      # print to terminal, no Slack, no Sheet write

Auth:
  - When called from the CEO/SEO triggers env: GOOGLE_SERVICE_ACCOUNT_KEY_B64 env var
  - When called locally: falls back to token-gsc.json (read-only, no Sheet write unless the
    local token also has spreadsheets scope — if not, Sheet write-back will 403)
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SCRIPTS = BASE_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPREADSHEET_ID = "1A2eD2LeBpWFjDMe6W9BZbN6FvfW-em_7gD002pJD7_E"
VERTICALS_QUEUE_TAB = "Verticals Queue"
GSC_SITE_URL = "sc-domain:globalhighlevel.com"
SLACK_CHANNEL = "C0AQ95LG97F"  # #globalhighlevel

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
COMBINED_SCOPES = GSC_SCOPES + SHEETS_SCOPES


def log(msg: str):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] [MEASURE] {msg}", flush=True)


# ── Auth ───────────────────────────────────────────────────────────────────────

def get_credentials():
    """Build credentials from GOOGLE_SERVICE_ACCOUNT_KEY_B64 env var (trigger env)
    or fall back to local token-gsc.json (user-auth, GSC-only).

    Returns (creds, supports_sheets_write: bool)."""
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials as UserCredentials

    sa_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY_B64", "")
    if sa_b64:
        try:
            info = json.loads(base64.b64decode(sa_b64))
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=COMBINED_SCOPES
            )
            log("  auth: service account (SA has sheets+webmasters scopes)")
            return creds, True
        except Exception as e:
            log(f"  SA key decode failed: {e}. Falling back to local token.")

    # Local fallback
    gsc_token = BASE_DIR / "token-gsc.json"
    if not gsc_token.exists():
        raise FileNotFoundError(
            "No GOOGLE_SERVICE_ACCOUNT_KEY_B64 env var AND no token-gsc.json locally. "
            "Either set the env var (trigger context) or run analytics.py once to bootstrap."
        )
    creds = UserCredentials.from_authorized_user_file(str(gsc_token), GSC_SCOPES)
    log("  auth: local user token (GSC only, no Sheet write)")
    return creds, False


# ── Sheet read / write ────────────────────────────────────────────────────────

def read_shipped_urls(sheets_service) -> list:
    """Read Verticals Queue tab, return list of shipped-row dicts."""
    resp = sheets_service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{VERTICALS_QUEUE_TAB}!A1:J1000",
    ).execute()
    values = resp.get("values", [])
    if not values:
        return []

    headers = values[0]
    rows = values[1:]

    # Build column name → index map
    col_idx = {name.strip(): i for i, name in enumerate(headers)}

    shipped = []
    for row_num, row in enumerate(rows, start=2):  # start=2 because row 1 is header
        # Pad row to full length
        row = row + [""] * (len(headers) - len(row))
        status = (row[col_idx.get("status", 4)] or "").strip().lower()
        if status != "shipped":
            continue
        url = (row[col_idx.get("url", 6)] or "").strip()
        if not url:
            continue
        shipped.append({
            "sheet_row": row_num,
            "vertical": row[col_idx.get("vertical", 0)].strip(),
            "tier": int(row[col_idx.get("tier", 1)] or 1),
            "part": int(row[col_idx.get("part", 2)] or 0),
            "language": row[col_idx.get("language", 3)].strip(),
            "shipped_date": row[col_idx.get("shipped_date", 5)].strip(),
            "url": url,
        })
    return shipped


def write_metrics_to_sheet(sheets_service, sheet_row: int, position: float,
                            ctr: float, affiliate_clicks_14d: int):
    """Write metrics back to the Sheet row. Columns H/I/J = position/ctr/affiliate_clicks_14d."""
    try:
        sheets_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{VERTICALS_QUEUE_TAB}!H{sheet_row}:J{sheet_row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[position, ctr, affiliate_clicks_14d]]},
        ).execute()
    except Exception as e:
        log(f"  Sheet write row {sheet_row} failed: {e}")


# ── GSC ────────────────────────────────────────────────────────────────────────

def query_url_metrics(gsc_service, url: str, days: int = 7) -> dict:
    """Query GSC for one URL over the last N days. GSC has ~3-day lag."""
    end_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=3 + days)).strftime("%Y-%m-%d")
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["page"],
        "dimensionFilterGroups": [{
            "filters": [{"dimension": "page", "operator": "equals", "expression": url}]
        }],
        "rowLimit": 1,
    }
    try:
        resp = gsc_service.searchanalytics().query(siteUrl=GSC_SITE_URL, body=body).execute()
        rows = resp.get("rows", [])
        if not rows:
            return {"indexed": False, "impressions": 0, "clicks": 0, "ctr": 0.0, "position": 0.0,
                    "window": f"{start_date} to {end_date}"}
        r = rows[0]
        return {
            "indexed": True,
            "impressions": r.get("impressions", 0),
            "clicks": r.get("clicks", 0),
            "ctr": round(r.get("ctr", 0) * 100, 2),
            "position": round(r.get("position", 0), 1),
            "window": f"{start_date} to {end_date}",
        }
    except Exception as e:
        return {"indexed": False, "impressions": 0, "clicks": 0, "ctr": 0.0, "position": 0.0,
                "error": str(e)[:200], "window": f"{start_date} to {end_date}"}


# ── Decision gate + narrative ─────────────────────────────────────────────────

def days_since(date_str: str) -> int:
    try:
        return (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days
    except Exception:
        return -1


def gate_recommendation(metrics: dict) -> str:
    """Decision-gate recommendation at Day 14 (narrative English, not data dump)."""
    if not metrics["indexed"]:
        return ("🚦 BLOCKED: Google still has not indexed this page after 2 weeks. "
                "That is a structural or thin-content problem, not a traffic problem. "
                "Do NOT ship Parts 2-9 of this series. Investigate first via GSC URL Inspection.")
    if metrics["impressions"] < 10:
        return (f"⚠️ Indexed but only {metrics['impressions']} people saw it in Google search in the last 7 days. "
                "The keyword or search intent is not matching what you wrote. "
                "Rewrite the title and meta description to target a higher-intent query before shipping Parts 2-3.")
    if metrics["clicks"] == 0 and metrics["impressions"] >= 50:
        return (f"⚠️ Google showed the page {metrics['impressions']} times but 0 people clicked. "
                "Your title or description is failing the SERP competition. "
                "Rewrite them to be more compelling before shipping Parts 2-3.")
    if metrics["clicks"] >= 1:
        return (f"✅ GREEN-LIGHT. Google showed the page {metrics['impressions']} times, {metrics['clicks']} people clicked, "
                f"ranking at position {metrics['position']}. "
                "The format works for this vertical + language. SHIP PARTS 2-3 ES next.")
    return f"📊 Indexed with {metrics['impressions']} impressions, still watching. Wait 2-4 more days for decision."


def narrative_line(item: dict, metrics: dict) -> str:
    """Write the per-URL narrative paragraph (Bezos-style plain English)."""
    days_live = days_since(item["shipped_date"])
    page_type = "hub" if item.get("part", 0) == 0 else f"Part {item['part']}"
    lang_name = {"es": "Spanish", "en": "English", "in": "India English", "ar": "Arabic"}.get(
        item["language"], item["language"]
    )
    vertical_name = item["vertical"].replace("-", " ")

    if not metrics["indexed"]:
        status = (f"Google has not shown this page in search yet. "
                  f"With a ~3-day lag in GSC reporting, that is expected at Day {days_live}. "
                  f"Real signal usually starts at Day 7-10.")
    else:
        pos_pretty = f"position {metrics['position']}"
        page_num = int(metrics["position"] / 10) + 1 if metrics["position"] > 0 else "?"
        status = (f"Google showed this page {metrics['impressions']} times in the last 7 days. "
                  f"{metrics['clicks']} of those viewers clicked through "
                  f"(CTR {metrics['ctr']}%), ranking at {pos_pretty} "
                  f"(~page {page_num} of search results). ")

    return (
        f"*{page_type} — {vertical_name} ({lang_name})*\n"
        f"<{item['url']}|{item['url']}>\n"
        f"Day {days_live} live. {status}"
    )


# ── Slack post ───────────────────────────────────────────────────────────────

def post_to_slack(text: str, dry: bool = False):
    if dry:
        print("\n--- SLACK DRY RUN ---")
        print(text)
        print("--- END SLACK ---\n")
        return
    try:
        from ops_log import post_to_channel
        post_to_channel(SLACK_CHANNEL, text)
        log("posted to #globalhighlevel")
    except Exception as e:
        log(f"Slack post failed: {e}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main(dry: bool = None):
    """Run measurement. dry=None → parse CLI args; dry=True/False → use directly."""
    if dry is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--dry", action="store_true", help="Print to terminal, don't post/write")
        args, _ = parser.parse_known_args()
        dry = args.dry

    try:
        from googleapiclient.discovery import build
        creds, supports_sheets_write = get_credentials()
    except Exception as e:
        log(f"Auth failed: {e}")
        post_to_slack(f"⚠️ verticals_measure: auth failed — {e}", dry=dry)
        return

    try:
        gsc_service = build("searchconsole", "v1", credentials=creds)
        sheets_service = build("sheets", "v4", credentials=creds) if supports_sheets_write else build(
            "sheets", "v4", credentials=creds
        )
    except Exception as e:
        log(f"Service build failed: {e}")
        return

    # Read shipped URLs from Sheet
    try:
        shipped = read_shipped_urls(sheets_service)
    except Exception as e:
        log(f"Sheet read failed: {e}")
        post_to_slack(
            f"⚠️ verticals_measure: could not read Verticals Queue tab — {str(e)[:300]}\n"
            "If 403: share the Sheet with the service account email "
            "(seo-agent@safebath-seo-agent.iam.gserviceaccount.com) as Editor.",
            dry=dry,
        )
        return

    if not shipped:
        log("No shipped rows in Verticals Queue. Nothing to measure.")
        if not dry:
            post_to_slack("📊 Verticals Measurement: no shipped URLs in Verticals Queue tab. Add a row with status=shipped to start tracking.", dry=False)
        return

    log(f"Found {len(shipped)} shipped URL(s) in Sheet.")

    narratives = []
    decision_gates = []

    for item in shipped:
        metrics = query_url_metrics(gsc_service, item["url"], days=7)
        narratives.append(narrative_line(item, metrics))

        # Write metrics back to Sheet
        if supports_sheets_write and not dry:
            # affiliate_clicks_14d would come from FirstPromoter if that integration existed; 0 for now
            write_metrics_to_sheet(
                sheets_service, item["sheet_row"],
                metrics["position"], metrics["ctr"], 0
            )

        days_live = days_since(item["shipped_date"])

        # Day-14 decision gate (fire once in the 14-17 day window for idempotency)
        if 14 <= days_live <= 17 and item.get("part", 0) >= 1:
            rec = gate_recommendation(metrics)
            decision_gates.append(
                f"🚦 *DECISION GATE — Day {days_live}*\n"
                f"<{item['url']}|{item['url']}>\n"
                f"{rec}"
            )

        # Day-56 (8-week) winning metric check
        if 56 <= days_live <= 59 and item.get("part", 0) >= 1:
            criteria_met = sum([
                metrics["position"] > 0 and metrics["position"] <= 15,
                metrics["ctr"] >= 1.5,
            ])
            tier = item.get("tier", 1)
            threshold = 2 if tier == 1 else (1 if tier == 2 else 1)
            verdict = "KEEP GOING" if criteria_met >= threshold else "CULL"
            decision_gates.append(
                f"🎯 *8-WEEK METRIC GATE — Day {days_live}*\n"
                f"<{item['url']}|{item['url']}>\n"
                f"Met {criteria_met}/2 criteria (position≤15, CTR≥1.5%). "
                f"Tier {tier} threshold: {threshold}. Verdict: *{verdict}*"
            )

    # Compose Slack message
    header = f"📊 *Verticals Measurement Digest — {datetime.now().strftime('%Y-%m-%d')}*"
    body = "\n\n".join(narratives)
    msg_parts = [header, "", body]
    if decision_gates:
        msg_parts.append("")
        msg_parts.append("─" * 30)
        msg_parts.extend(decision_gates)

    post_to_slack("\n".join(msg_parts), dry=dry)


if __name__ == "__main__":
    main()
