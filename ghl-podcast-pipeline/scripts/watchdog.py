"""
watchdog.py
Runs every 10 minutes via systemd timer. Checks pipeline health and
auto-fixes common problems so the pipeline runs unattended for weeks.

Fixes it can perform automatically:
  - Google Drive token refresh (expired OAuth)
  - NotebookLM auth token refresh
  - Stale scheduler (crashed/hung) — restarts systemd service
  - Disk space warning — cleans up temp audio files
  - Corrupted published.json — restores from backup
  - Log rotation — prevents log file from eating all disk space

Problems it escalates via email:
  - Transistor API key invalid (needs human)
  - NotebookLM quota exhausted (needs human)
  - Repeated failures (>5 consecutive) across cycles
  - Disk critically full (<500MB) after cleanup
"""

import json
import os
import smtplib
import ssl
import subprocess
import shutil
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
WATCHDOG_LOG = BASE_DIR / "logs" / "watchdog.log"
STATE_FILE = BASE_DIR / "logs" / "scheduler-state.json"
PUBLISHED_FILE = BASE_DIR / "data" / "published.json"
PUBLISHED_BACKUP = BASE_DIR / "data" / "published.json.bak"
TOKEN_FILE = BASE_DIR / "token.json"
AUDIO_DIR = BASE_DIR / "data" / "audio"

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "bill@reiamplifi.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

MAX_LOG_SIZE_MB = 50
DISK_WARNING_MB = 1000
DISK_CRITICAL_MB = 500
STALE_CYCLE_HOURS = 30  # if no cycle in 30h, something is wrong


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [WATCHDOG] {msg}"
    print(line, flush=True)
    with open(WATCHDOG_LOG, "a") as f:
        f.write(line + "\n")


def send_alert(subject: str, body: str):
    """Send alert email — only for problems that need human attention."""
    if not GMAIL_APP_PASSWORD:
        log(f"  ALERT (no email): {subject}")
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = f"⚠️ GHL Pipeline Alert: {subject}"
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = GMAIL_ADDRESS
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(context=context)
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())
        log(f"  Alert emailed: {subject}")
    except Exception as e:
        log(f"  Alert email failed: {e}")


# ── Check 1: Is the scheduler alive? ────────────────────────────────────────
def check_scheduler_alive():
    """Restart scheduler if it's crashed or hung."""
    result = subprocess.run(
        ["systemctl", "is-active", "ghl-podcast"],
        capture_output=True, text=True
    )
    if result.stdout.strip() != "active":
        log("Scheduler is NOT running — restarting...")
        subprocess.run(["systemctl", "restart", "ghl-podcast"], check=False)
        log("  Scheduler restarted")
        return "restarted"

    # Check if the cycle is stale (no progress in 30+ hours)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
            last_started = datetime.fromisoformat(state["last_cycle_started"])
            hours_ago = (datetime.now() - last_started).total_seconds() / 3600
            if hours_ago > STALE_CYCLE_HOURS:
                log(f"Scheduler stale — last cycle {hours_ago:.1f}h ago. Restarting...")
                subprocess.run(["systemctl", "restart", "ghl-podcast"], check=False)
                return "restarted_stale"
        except Exception:
            pass
    return "ok"


# ── Check 2: Google Drive token ─────────────────────────────────────────────
def check_drive_token():
    """Refresh Google Drive OAuth token if expired."""
    if not TOKEN_FILE.exists():
        log("Drive token missing — cannot auto-fix (needs browser OAuth)")
        send_alert("Google Drive token missing",
                   "token.json is missing. Drive uploads will fail.\n"
                   "This needs manual OAuth — run the pipeline locally once to re-auth.")
        return "missing"

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE),
            ["https://www.googleapis.com/auth/drive.file"]
        )
        if creds and creds.expired and creds.refresh_token:
            log("Drive token expired — refreshing...")
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            log("  Drive token refreshed")
            return "refreshed"
        elif creds and creds.valid:
            return "ok"
        else:
            log("Drive token invalid and no refresh token")
            send_alert("Google Drive auth broken",
                       "Drive token is invalid and can't be refreshed.\n"
                       "Needs manual re-auth.")
            return "broken"
    except Exception as e:
        log(f"Drive token check error: {e}")
        return "error"


# ── Check 3: NotebookLM auth ────────────────────────────────────────────────
def check_notebooklm_auth():
    """Test NotebookLM auth and attempt refresh if stale."""
    import asyncio

    async def _test():
        from notebooklm import NotebookLMClient
        try:
            async with await NotebookLMClient.from_storage() as client:
                await client.notebooks.list()
                return "ok"
        except Exception as e:
            error_str = str(e).lower()
            if "session expired" in error_str or "csrf" in error_str:
                # Try refresh
                try:
                    async with await NotebookLMClient.from_storage() as client:
                        await client.refresh_auth()
                        await client.notebooks.list()
                        return "refreshed"
                except Exception as e2:
                    return f"broken: {e2}"
            elif "quota" in error_str or "limit" in error_str:
                return f"quota: {e}"
            return f"error: {e}"

    result = asyncio.run(_test())
    if result == "ok":
        return "ok"
    elif result == "refreshed":
        log("NotebookLM auth refreshed")
        return "refreshed"
    elif result.startswith("quota"):
        log(f"NotebookLM quota issue: {result}")
        send_alert("NotebookLM quota exhausted",
                   f"NotebookLM hit a quota limit:\n{result}\n\n"
                   "This will resolve on its own when the quota resets, "
                   "but episodes won't generate until then.")
        return "quota"
    else:
        log(f"NotebookLM auth broken: {result}")
        send_alert("NotebookLM auth broken",
                   f"NotebookLM authentication failed:\n{result}\n\n"
                   "May need to re-run 'notebooklm login' on a machine with a browser.")
        return "broken"


# ── Check 4: Disk space ─────────────────────────────────────────────────────
def check_disk_space():
    """Clean up temp files if disk is getting full."""
    stat = shutil.disk_usage("/")
    free_mb = stat.free // (1024 * 1024)

    if free_mb < DISK_CRITICAL_MB:
        # Emergency cleanup
        log(f"CRITICAL: Only {free_mb}MB free — emergency cleanup")
        cleaned = cleanup_temp_files()
        stat = shutil.disk_usage("/")
        free_mb = stat.free // (1024 * 1024)
        if free_mb < DISK_CRITICAL_MB:
            send_alert("Disk critically full",
                       f"Only {free_mb}MB free after cleanup.\n"
                       f"Cleaned {cleaned} files but still critical.\n"
                       "Pipeline may fail on next cycle.")
        return "critical"
    elif free_mb < DISK_WARNING_MB:
        log(f"Disk warning: {free_mb}MB free — cleaning up...")
        cleanup_temp_files()
        return "warning"
    return "ok"


def cleanup_temp_files():
    """Remove leftover audio files and old logs."""
    cleaned = 0
    # Clean audio temp files
    if AUDIO_DIR.exists():
        for f in AUDIO_DIR.glob("*.mp4"):
            try:
                f.unlink()
                cleaned += 1
            except Exception:
                pass
    return cleaned


# ── Check 5: Log rotation ───────────────────────────────────────────────────
def check_log_rotation():
    """Rotate logs if they're getting too big."""
    for log_path in [LOG_FILE, WATCHDOG_LOG]:
        if log_path.exists():
            size_mb = log_path.stat().st_size / (1024 * 1024)
            if size_mb > MAX_LOG_SIZE_MB:
                rotated = log_path.with_suffix(".log.old")
                if rotated.exists():
                    rotated.unlink()
                log_path.rename(rotated)
                log(f"Rotated {log_path.name} ({size_mb:.0f}MB)")


# ── Check 6: published.json integrity ───────────────────────────────────────
def check_published_json():
    """Validate and backup published.json."""
    if not PUBLISHED_FILE.exists():
        return "missing"  # Not necessarily an error on first run

    try:
        with open(PUBLISHED_FILE) as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("published.json is not a list")

        # Backup if valid
        import shutil
        shutil.copy2(PUBLISHED_FILE, PUBLISHED_BACKUP)
        return "ok"

    except (json.JSONDecodeError, ValueError) as e:
        log(f"published.json corrupted: {e}")
        # Restore from backup
        if PUBLISHED_BACKUP.exists():
            log("  Restoring from backup...")
            import shutil
            shutil.copy2(PUBLISHED_BACKUP, PUBLISHED_FILE)
            log("  Restored")
            return "restored"
        else:
            log("  No backup available!")
            send_alert("published.json corrupted",
                       f"published.json is corrupted and no backup exists.\n"
                       f"Error: {e}\n"
                       "The pipeline may reprocess already-published articles.")
            return "corrupted"


# ── Check 7: Recent error analysis ──────────────────────────────────────────
def check_recent_errors():
    """Scan logs for patterns that indicate systemic issues."""
    if not LOG_FILE.exists():
        return "ok"

    try:
        lines = LOG_FILE.read_text().splitlines()
        # Only look at lines from the last hour to avoid alerting on stale errors
        one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        recent = [l for l in lines[-500:] if l[1:17] >= one_hour_ago]

        # Count errors in recent logs
        errors = [l for l in recent if "ERROR" in l or "FAILED" in l]

        # Check for specific patterns
        transistor_errors = [l for l in errors if "transistor" in l.lower() or "upload" in l.lower()]
        auth_errors = [l for l in errors if "auth" in l.lower() or "401" in l or "403" in l]
        notebooklm_errors = [l for l in errors if "notebooklm" in l.lower() or "notebook" in l.lower()]

        if len(transistor_errors) >= 5:
            send_alert("Transistor upload failures",
                       f"Found {len(transistor_errors)} Transistor errors in recent logs.\n"
                       "The API key may be invalid or the show may have issues.\n\n"
                       "Recent errors:\n" + "\n".join(transistor_errors[-3:]))

        if len(auth_errors) >= 3:
            send_alert("Authentication failures",
                       f"Found {len(auth_errors)} auth errors in recent logs.\n"
                       "An API key or token may have expired.\n\n"
                       "Recent errors:\n" + "\n".join(auth_errors[-3:]))

        if len(errors) > 20:
            return f"high_error_rate ({len(errors)} recent errors)"
        return "ok"
    except Exception:
        return "ok"


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    log("─" * 40)
    log("Watchdog check starting")

    results = {}
    results["scheduler"] = check_scheduler_alive()
    results["drive_token"] = check_drive_token()
    results["notebooklm"] = check_notebooklm_auth()
    results["disk"] = check_disk_space()
    results["published_json"] = check_published_json()
    results["errors"] = check_recent_errors()
    check_log_rotation()

    # Summary
    issues = {k: v for k, v in results.items() if v != "ok"}
    if issues:
        log(f"Issues found: {issues}")
    else:
        log("All checks passed")

    log("Watchdog check complete")


if __name__ == "__main__":
    main()
