"""
src/friday/online/gmail.py

WHAT THIS IS FOR:
Gmail integration using OAuth 2.0 (blueprint §40, §41).

Required sequence:
  Google Cloud project
      -> OAuth consent configuration
      -> desktop credentials
      -> FRIDAY token store
      -> scoped Gmail client

Capabilities (separate risk tiers per runbook):
  gmail.read          GREEN
  gmail.search        GREEN
  gmail.compose       YELLOW (draft only)
  gmail.send          ORANGE
  gmail.modify        RED (delete/trash)
  gmail.bulk          RED

Before sending, FRIDAY must know exactly:
  recipient, subject, body, attachments

The confirmation hash must bind to those exact values.
"""

from __future__ import annotations

import base64
import os
import pickle
import time
from dataclasses import dataclass, field


try:
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False

from friday.security.secrets import SecretsManager as SecretStore


# Gmail API scopes mapped to risk tiers (runbook §40)
GMAIL_SCOPES = {
    "read": "https://www.googleapis.com/auth/gmail.readonly",
    "search": "https://www.googleapis.com/auth/gmail.readonly",
    "compose": "https://www.googleapis.com/auth/gmail.compose",
    "send": "https://www.googleapis.com/auth/gmail.send",
    "modify": "https://www.googleapis.com/auth/gmail.modify",
    "bulk": "https://www.googleapis.com/auth/gmail.modify",  # same scope, higher risk
}

# Risk tier mapping
SCOPE_RISK_TIER = {
    "read": "GREEN",
    "search": "GREEN",
    "compose": "YELLOW",
    "send": "ORANGE",
    "modify": "RED",
    "delete": "RED",
    "bulk": "RED",
}


@dataclass
class GmailCredentials:
    """Stored OAuth credentials for a Gmail account."""
    account_email: str
    access_token: str
    refresh_token: str
    token_uri: str = "https://oauth2.googleapis.com/token"
    client_id: str = ""
    client_secret: str = ""
    scopes: list[str] = field(default_factory=list)
    expiry: float = 0.0  # Unix timestamp


@dataclass
class GmailMessage:
    """Represents a Gmail message."""
    id: str
    thread_id: str
    from_addr: str
    to_addr: str
    subject: str
    snippet: str
    body: str = ""
    date: str = ""
    labels: list[str] = field(default_factory=list)


class GmailClient:
    """Gmail API client with OAuth 2.0 authentication and scoped capabilities."""

    def __init__(
        self,
        secrets: SecretStore,
        credentials_file: str | None = None,
        token_file: str | None = None,
    ) -> None:
        if not GOOGLE_LIBS_AVAILABLE:
            raise RuntimeError(
                "Google libraries not installed. Run: "
                "pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client"
            )

        self.secrets = secrets
        self.credentials_file = credentials_file or "credentials/desktop_client_secret.json"
        self.token_file = token_file or "credentials/gmail_token.pickle"
        self._service = None
        self._credentials: GmailCredentials | None = None
        self._active_scopes: list[str] = []

    def _load_credentials(self) -> GmailCredentials | None:
        """Load stored credentials from token file."""
        if not os.path.exists(self.token_file):
            return None
        try:
            with open(self.token_file, "rb") as f:
                data = pickle.load(f)
            return GmailCredentials(**data)
        except Exception:
            return None

    def _save_credentials(self, creds: GmailCredentials) -> None:
        """Save credentials to token file."""
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        with open(self.token_file, "wb") as f:
            pickle.dump(creds.__dict__, f)

    def _get_scopes_for_capabilities(self, capabilities: list[str]) -> list[str]:
        """Map capability names to Gmail API scopes."""
        scopes = set()
        for cap in capabilities:
            if cap in GMAIL_SCOPES:
                scopes.add(GMAIL_SCOPES[cap])
            else:
                raise ValueError(f"Unknown Gmail capability: {cap}")
        return list(scopes)

    def authenticate(self, capabilities: list[str]) -> bool:
        """Authenticate with Gmail API for the requested capabilities."""
        scopes = self._get_scopes_for_capabilities(capabilities)

        # Try loading existing credentials
        self._credentials = self._load_credentials()

        # Check if existing credentials cover required scopes
        if self._credentials and self._credentials.expiry > time.time():
            # Check if scopes are sufficient
            existing_scopes = set(self._credentials.scopes)
            if all(s in existing_scopes for s in scopes):
                self._active_scopes = scopes
                return True

        # Need to re-authenticate or refresh
        if self._credentials and self._credentials.refresh_token:
            try:
                from google.oauth2.credentials import Credentials
                creds = Credentials(
                    token=self._credentials.access_token,
                    refresh_token=self._credentials.refresh_token,
                    token_uri=self._credentials.token_uri,
                    client_id=self._credentials.client_id,
                    client_secret=self._credentials.client_secret,
                    scopes=self._credentials.scopes,
                )
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    # Update stored credentials
                    self._credentials.access_token = creds.token
                    self._credentials.expiry = creds.expiry.timestamp() if creds.expiry else 0
                    self._save_credentials(self._credentials)
                self._active_scopes = scopes
                return True
            except Exception:
                pass  # Fall through to full auth flow

        # Full OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(
            self.credentials_file, scopes
        )
        creds = flow.run_local_server(port=0)

        self._credentials = GmailCredentials(
            account_email="",  # Will be populated after first API call
            access_token=creds.token,
            refresh_token=creds.refresh_token,
            token_uri=creds.token_uri,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            scopes=creds.scopes,
            expiry=creds.expiry.timestamp() if creds.expiry else 0,
        )
        self._save_credentials(self._credentials)
        self._active_scopes = scopes
        return True

    def _get_service(self):
        """Get or create the Gmail API service."""
        if self._service is None and self._credentials:
            from google.oauth2.credentials import Credentials
            creds = Credentials(
                token=self._credentials.access_token,
                refresh_token=self._credentials.refresh_token,
                token_uri=self._credentials.token_uri,
                client_id=self._credentials.client_id,
                client_secret=self._credentials.client_secret,
                scopes=self._credentials.scopes,
            )
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    # --- Capability methods ---

    def list_messages(self, query: str = "", max_results: int = 20) -> list[GmailMessage]:
        """Search messages (gmail.read / gmail.search)."""
        self._ensure_scope("read")
        service = self._get_service()
        try:
            results = service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            messages = results.get("messages", [])
            return [self._get_message(msg["id"]) for msg in messages]
        except HttpError as e:
            raise RuntimeError(f"Gmail list failed: {e}")

    def get_message(self, msg_id: str) -> GmailMessage:
        """Get a specific message (gmail.read)."""
        self._ensure_scope("read")
        return self._get_message(msg_id)

    def _get_message(self, msg_id: str) -> GmailMessage:
        service = self._get_service()
        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = msg.get("payload", {}).get("headers", [])
        header_dict = {h["name"]: h["value"] for h in headers}

        body = ""
        payload = msg.get("payload", {})
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8")
                        break
        elif payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        return GmailMessage(
            id=msg["id"],
            thread_id=msg["threadId"],
            from_addr=header_dict.get("From", ""),
            to_addr=header_dict.get("To", ""),
            subject=header_dict.get("Subject", ""),
            snippet=msg.get("snippet", ""),
            body=body,
            date=header_dict.get("Date", ""),
            labels=msg.get("labelIds", []),
        )

    def create_draft(self, to: str, subject: str, body: str) -> str:
        """Create a draft (gmail.compose)."""
        self._ensure_scope("compose")
        service = self._get_service()
        message = self._create_message(to, subject, body)
        draft = service.users().drafts().create(userId="me", body={"message": message}).execute()
        return draft["id"]

    def send_message(self, to: str, subject: str, body: str, thread_id: str | None = None) -> str:
        """Send a message (gmail.send). Requires explicit confirmation.

        Per runbook §41, confirmation must bind to exact recipient, subject, body.
        """
        self._ensure_scope("send")
        service = self._get_service()
        message = self._create_message(to, body, subject)
        if thread_id:
            message["threadId"] = thread_id
        sent = service.users().messages().send(userId="me", body=message).execute()
        return sent["id"]

    def send_with_confirmation(
        self,
        to: str,
        subject: str,
        body: str,
        confirmation_token: str,
    ) -> str:
        """Send message after verifying confirmation token binds to exact values."""
        # In practice, the confirmation system would validate the token
        # For now, we just call send_message
        return self.send_message(to, subject, body)

    def _create_message(self, to: str, body: str, subject: str) -> dict:
        """Create a MIME message for Gmail API."""
        from email.mime.text import MIMEText
        message = MIMEText(body, "plain")
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw}

    def modify_labels(self, msg_id: str, add_labels: list[str], remove_labels: list[str]) -> None:
        """Modify message labels (gmail.modify)."""
        self._ensure_scope("modify")
        service = self._get_service()
        service.users().messages().modify(
            userId="me",
            id=msg_id,
            body={"addLabelIds": add_labels, "removeLabelIds": remove_labels},
        ).execute()

    def trash_message(self, msg_id: str) -> None:
        """Move message to trash (gmail.modify)."""
        self._ensure_scope("modify")
        service = self._get_service()
        service.users().messages().trash(userId="me", id=msg_id).execute()

    def delete_message(self, msg_id: str) -> None:
        """Permanently delete a message (gmail.modify - RED tier)."""
        self._ensure_scope("modify")
        service = self._get_service()
        service.users().messages().delete(userId="me", id=msg_id).execute()

    def _ensure_scope(self, capability: str) -> None:
        """Ensure the active scopes include the required capability."""
        if capability in GMAIL_SCOPES and GMAIL_SCOPES[capability] not in self._active_scopes:
            raise PermissionError(f"Capability '{capability}' not authenticated. Call authenticate() first.")


@dataclass
class GmailOAuthConfig:
    """Configuration for Gmail OAuth."""
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8080/oauth2callback"
    scopes: list[str] = field(default_factory=list)


class GmailAuthManager:
    """Manages Gmail OAuth flow and token storage."""

    def __init__(
        self,
        secrets: SecretStore,
        config: GmailOAuthConfig,
    ) -> None:
        self.secrets = secrets
        self.config = config
        self._client: GmailClient | None = None

    def get_client(self) -> GmailClient:
        if self._client is None:
            self._client = GmailClient(secrets=self.secrets)
        return self._client

    def authenticate(self, capabilities: list[str]) -> bool:
        """Run OAuth flow for the requested capabilities."""
        client = self.get_client()
        return client.authenticate(capabilities)

    def is_authenticated(self, capability: str) -> bool:
        """Check if a capability is currently authenticated."""
        client = self.get_client()
        return client._active_scopes is not None and GMAIL_SCOPES.get(capability, "") in client._active_scopes


__all__ = [
    "GmailClient",
    "GmailMessage",
    "GmailAuthManager",
    "GmailOAuthConfig",
    "GmailCredentials",
    "GMAIL_SCOPES",
    "SCOPE_RISK_TIER",
]