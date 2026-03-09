"""
One-time Google Drive authentication.
Run this once: venv/bin/python3 setup-drive-auth.py
It will open a browser — sign in with your Google account.
After that, the pipeline handles Drive automatically.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

BASE_DIR = Path(__file__).parent
TOKEN_FILE = BASE_DIR / "token.json"
CREDENTIALS_FILE = BASE_DIR / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

creds = None
if TOKEN_FILE.exists():
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

print("Google Drive auth complete — token.json saved.")
print("You never need to run this again.")
