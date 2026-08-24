import json
import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

KEYRING_SERVICE = "FRIDAY-google-oauth"
KEYRING_USERNAME = "default"


def get_credentials() -> Credentials:
    creds = None
    stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if stored:
        creds = Credentials.from_authorized_user_info(json.loads(stored), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, creds.to_json())

    return creds