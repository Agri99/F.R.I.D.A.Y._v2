"""
src/friday/security/google_auth.py

WHAT THIS IS FOR:
Handles OAuth 2.0 user credentials for Google Workspace APIs (Gmail, Calendar).
Credentials and tokens are managed outside the LLM context (blueprint §21, §40).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Standard tested scopes for Gmail and Google Calendar
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

KEYRING_SERVICE = "FRIDAY-google-oauth"
KEYRING_USERNAME = "default"


def get_credentials_path() -> Path | None:
    for candidate in [
        Path("secrets/credentials.json"),
        Path("credentials.json"),
    ]:
        if candidate.exists():
            return candidate
    return None


def get_credentials() -> Any:
    """Load or refresh Google OAuth2 credentials."""
    import keyring
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds: Any = None
    stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if stored:
        try:
            creds = Credentials.from_authorized_user_info(json.loads(stored), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # Token expired or scope mismatch — force re-auth
                creds = None

        if not creds or not creds.valid:
            cred_file = get_credentials_path()
            if not cred_file:
                raise FileNotFoundError(
                    "Google OAuth credentials file not found. Place credentials.json into secrets/ or project root."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
            creds = flow.run_local_server(port=0)

        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, creds.to_json())

    return creds
