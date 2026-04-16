"""
verticals_measure.py

Daily measurement loop for shipped vertical URLs. Pulls GSC data per URL,
posts a digest to #globalhighlevel Slack, fires a "DECISION GATE" alert at
Day 14 from shipped_date.

Hardcoded URL list for now (per build-per-business-no-premature-abstraction).
When Part 2 ships, add a row to SHIPPED_URLS. At ~5 shipped pillars, extract
to read from Verticals Queue Sheet tab.

Usage:
  venv/bin/python3 scripts/verticals_measure.py            # run measurement, post to Slack
  venv/bin/python3 scripts/verticals_measure.py --dry      # print to terminal, don't Slack
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SCRIPTS = BASE_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

GSC_TOKEN_FILE = BASE_DIR / "token-gsc.json"
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GSC_SITE_URL = "sc-domain:globalhighlevel.com"
SLACK_CHANNEL = "C0AQ95LG97F"  # #globalhighlevel

# Hardcoded shipped URLs. When a new pillar ships, append a row here.
# (Per feedback_build_per_business_no_premature_abstraction.md — extract to
# Sheet-read at N=5 pillars, not before.)
SHIPPED_URLS = [
    {
        "url": "https://globalhighlevel.com/es/para/agencias-de-marketing/",
        "label": "Hub: agencias-de-marketing (ES)",
        "vertical": "agencias-de-marketing",
        "language": "es",
        "type": "hub",
        "shipped_date": "2026-04-16",
        "tier": 1,
    },
    {
        "url": "https://globalhighlevel.com/es/para/agencias-de-marketing/por-que-agencias-marketing-necesitan-crm-2026-parte-1/",
        "label": "Pillar P1: agencias-de-marketing (ES)",
        "vertical": "agencias-de-marketing",
        "language": "es",
        "type": "pillar",
        "part": 1,
        "shipped_date": "2026-04-16",
        "tier": 1,
    },
]


def log(msg: str):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] [MEASURE] {msg}", flush=True)


# ── GSC ────────────────────────────────────────────────────────────────────────

def get_gsc_service():
    """Build GSC API service. Reuses token-gsc.json from analytics.py."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not GSC_TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"GSC token not found at {GSC_TOKEN_FILE}. Run analytics.py once to bootstrap auth."
        )
    creds = Credentials.from_authorized_user_file(str(GSC_TOKEN_FILE), GSC_SCOPES)
    return build("searchconsole", "v1", credentials=creds)


def query_url_metrics(service, url: str, days: int = 7) -> dict:
    """Query GSC for one URL's impressions/clicks/CTR/position over the last N days.
    GSC has a ~3-day lag, so window is days-3 to days+days-3 ago."""
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
        resp = service.searchanalytics().query(siteUrl=GSC_SITE_URL, body=body).execute()
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


# ── Decision-gate logic ──────────────────────────────────────────────────────

def days_since(date_str: str) -> int:
    try:
        ship = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - ship).days
    except Exception:
        return -1


def gate_recommendation(item: dict, metrics: dict, days_live: int) -> str:
    """Return a recommendation string for the decision gate (Day 14)."""
    if not metrics["indexed"]:
        return "🚦 BLOCKED: not indexed at Day 14. Check GSC URL Inspection. Likely structure or thin-content issue. DO NOT ship Parts 2-9."
    if metrics["impressions"] < 10:
        return f"⚠️ INDEXED but only {metrics['impressions']} impressions in 7 days. Keyword/intent mismatch. REWRITE TITLE+META before shipping Parts 2-3."
    if metrics["clicks"] == 0 and metrics["impressions"] >= 50:
        return f"⚠️ {metrics['impressions']} impressions but 0 clicks. Title/meta is failing. REWRITE before shipping Parts 2-3."
    if metrics["clicks"] >= 1:
        return f"✅ GREEN-LIGHT: {metrics['clicks']} clicks, {metrics['impressions']} impressions, position {metrics['position']}. SHIP PARTS 2-3."
    return f"📊 INDEXED, {metrics['impressions']} impressions, watching."


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
    """Run measurement. dry=None → parse from CLI args; dry=True/False → use directly.
    Callable both as CLI (`python verticals_measure.py --dry`) and from scheduler (`main()`)."""
    if dry is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--dry", action="store_true", help="Print to terminal, don't post Slack")
        # parse_known_args avoids exit if scheduler passed unrelated args
        args, _ = parser.parse_known_args()
        dry = args.dry

    log(f"Measuring {len(SHIPPED_URLS)} shipped URLs...")

    try:
        service = get_gsc_service()
    except Exception as e:
        log(f"GSC auth failed: {e}")
        post_to_slack(f"⚠️ verticals_measure: GSC auth failed — {e}", dry=dry)
        return

    lines = ["📊 *Verticals Measurement Digest*", ""]
    decision_gates = []
    today = datetime.now().strftime("%Y-%m-%d")

    for item in SHIPPED_URLS:
        metrics = query_url_metrics(service, item["url"], days=7)
        days_live = days_since(item["shipped_date"])

        index_emoji = "✅" if metrics["indexed"] else "❌"
        line = (
            f"{index_emoji} *{item['label']}* (Day {days_live})\n"
            f"    Impressions: {metrics['impressions']} · Clicks: {metrics['clicks']} · "
            f"CTR: {metrics['ctr']}% · Position: {metrics['position']}\n"
            f"    Window: {metrics['window']}"
        )
        if "error" in metrics:
            line += f"\n    ⚠️ GSC error: {metrics['error']}"
        lines.append(line)
        lines.append("")

        # Day-14 decision gate (fires once when days_live first hits 14, but to keep idempotent
        # we fire whenever days_live is in [14, 17] — Slack dedup is fine, this is just an
        # alerting window)
        if 14 <= days_live <= 17 and item["type"] == "pillar":
            rec = gate_recommendation(item, metrics, days_live)
            decision_gates.append(f"🚦 *DECISION GATE* — {item['label']} (Day {days_live})\n    {rec}")

        # Day-56 (8-week) winning metric check
        if 56 <= days_live <= 59 and item["type"] == "pillar":
            criteria_met = sum([
                metrics["position"] > 0 and metrics["position"] <= 15,
                metrics["ctr"] >= 1.5,
                # affiliate clicks check would go here if FirstPromoter integration existed
            ])
            tier = item.get("tier", 1)
            threshold = 2 if tier == 1 else (1 if tier == 2 else 1)
            verdict = "KEEP GOING" if criteria_met >= threshold else "CULL"
            decision_gates.append(
                f"🎯 *8-WEEK WINNING METRIC* — {item['label']} (Day {days_live})\n"
                f"    Criteria met: {criteria_met}/2 (position≤15, CTR≥1.5%) — Tier {tier} threshold: {threshold}\n"
                f"    Verdict: *{verdict}*"
            )

    if decision_gates:
        lines.append("")
        lines.append("─" * 30)
        lines.extend(decision_gates)

    text = "\n".join(lines)
    post_to_slack(text, dry=dry)


if __name__ == "__main__":
    main()
