"""
sheets-auth-setup.py
One-time: authenticate Bill's Google account with Sheets scope and save token
so future pipeline runs can write to the SEO Changelog Tracker.

Run: python3 scripts/sheets-auth-setup.py
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).parent.parent
TOKEN_FILE = BASE_DIR / "token-sheets.json"
CREDS_FILE = BASE_DIR / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def main():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                # Try the GSC creds file as fallback (same OAuth client)
                fallback = BASE_DIR / "credentials-gsc.json"
                if fallback.exists():
                    flow = InstalledAppFlow.from_client_secrets_file(str(fallback), SCOPES)
                else:
                    raise SystemExit(f"No credentials file at {CREDS_FILE} or {fallback}")
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    print(f"✓ Sheets auth saved → {TOKEN_FILE}")
    print(f"  Scopes: {creds.scopes}")


if __name__ == "__main__":
    main()
