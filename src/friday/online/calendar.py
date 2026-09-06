"""
src/friday/online/calendar.py

WHAT THIS IS FOR:
Google Calendar integration using OAuth 2.0 (blueprint §42, §43).

Capabilities (separate risk tiers per runbook §42):
  calendar.read       GREEN
  calendar.search     GREEN
  calendar.create     ORANGE
  calendar.modify     ORANGE
  calendar.delete     RED

Verification after create/update (runbook §43):
  query calendar -> locate event -> check title, start/end, timezone, calendar ID
"""

from __future__ import annotations

import os
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False

from friday.security.secrets import SecretsManager as SecretStore


# Calendar API scopes mapped to risk tiers (runbook §42)
CALENDAR_SCOPES = {
    "read": "https://www.googleapis.com/auth/calendar.readonly",
    "search": "https://www.googleapis.com/auth/calendar.readonly",
    "create": "https://www.googleapis.com/auth/calendar",
    "modify": "https://www.googleapis.com/auth/calendar",
    "delete": "https://www.googleapis.com/auth/calendar",
}

SCOPE_RISK_TIER = {
    "read": "GREEN",
    "search": "GREEN",
    "create": "ORANGE",
    "modify": "ORANGE",
    "delete": "RED",
}


@dataclass
class CalendarCredentials:
    """Stored OAuth credentials for a Calendar account."""
    account_email: str
    access_token: str
    refresh_token: str
    token_uri: str = "https://oauth2.googleapis.com/token"
    client_id: str = ""
    client_secret: str = ""
    scopes: list[str] = field(default_factory=list)
    expiry: float = 0.0


@dataclass
class CalendarEvent:
    """Represents a Calendar event."""
    id: str
    summary: str
    start_time: str
    end_time: str
    timezone: str
    calendar_id: str = "primary"
    description: str = ""
    location: str = ""
    attendees: list[str] = field(default_factory=list)
    status: str = "confirmed"
    html_link: str = ""
    created: str = ""
    updated: str = ""


@dataclass
class CalendarListEntry:
    """A calendar in the user's calendar list."""
    id: str
    summary: str
    primary: bool = False
    access_role: str = ""
    background_color: str = ""
    foreground_color: str = ""


class CalendarClient:
    """Google Calendar API client with OAuth 2.0 authentication."""

    def __init__(
        self,
        secrets: "SecretStore",
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
        self.token_file = token_file or "credentials/calendar_token.pickle"
        self._service = None
        self._credentials: CalendarCredentials | None = None
        self._active_scopes: list[str] = []

    def _load_credentials(self) -> CalendarCredentials | None:
        """Load stored credentials from token file."""
        if not os.path.exists(self.token_file):
            return None
        try:
            with open(self.token_file, "rb") as f:
                data = pickle.load(f)
            return CalendarCredentials(**data)
        except Exception:
            return None

    def _save_credentials(self, creds: CalendarCredentials) -> None:
        """Save credentials to token file."""
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        with open(self.token_file, "wb") as f:
            pickle.dump(creds.__dict__, f)

    def _get_scopes_for_capabilities(self, capabilities: list[str]) -> list[str]:
        """Map capability names to Calendar API scopes."""
        scopes = set()
        for cap in capabilities:
            if cap in CALENDAR_SCOPES:
                scopes.add(CALENDAR_SCOPES[cap])
            else:
                raise ValueError(f"Unknown Calendar capability: {cap}")
        return list(scopes)

    def authenticate(self, capabilities: list[str]) -> bool:
        """Authenticate with Calendar API for the requested capabilities."""
        scopes = self._get_scopes_for_capabilities(capabilities)

        # Try loading existing credentials
        self._credentials = self._load_credentials()

        # Check if existing credentials cover required scopes
        if self._credentials and self._credentials.expiry > time.time():
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

        self._credentials = CalendarCredentials(
            account_email="",
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
        """Get or create the Calendar API service."""
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
            self._service = build("calendar", "v3", credentials=creds)
        return self._service

    # --- Capability methods ---

    def list_calendars(self) -> list[CalendarListEntry]:
        """List all calendars (calendar.read)."""
        self._ensure_scope("read")
        service = self._get_service()
        try:
            results = service.calendarList().list().execute()
            items = results.get("items", [])
            return [
                CalendarListEntry(
                    id=item["id"],
                    summary=item.get("summary", ""),
                    primary=item.get("primary", False),
                    access_role=item.get("accessRole", ""),
                    background_color=item.get("backgroundColor", ""),
                    foreground_color=item.get("foregroundColor", ""),
                )
                for item in items
            ]
        except HttpError as e:
            raise RuntimeError(f"Calendar list failed: {e}")

    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 50,
        query: str | None = None,
    ) -> list[CalendarEvent]:
        """List events (calendar.read / calendar.search)."""
        self._ensure_scope("read")
        service = self._get_service()
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                q=query,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = events_result.get("items", [])
            return [self._parse_event(event) for event in events]
        except HttpError as e:
            raise RuntimeError(f"Calendar list events failed: {e}")

    def get_event(self, event_id: str, calendar_id: str = "primary") -> CalendarEvent:
        """Get a specific event (calendar.read)."""
        self._ensure_scope("read")
        service = self._get_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        return self._parse_event(event)

    def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        timezone: str = "UTC",
        calendar_id: str = "primary",
        description: str = "",
        location: str = "",
        attendees: list[str] | None = None,
    ) -> CalendarEvent:
        """Create an event (calendar.create - ORANGE)."""
        self._ensure_scope("create")
        service = self._get_service()

        event_body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time, "timeZone": timezone},
            "end": {"dateTime": end_time, "timeZone": timezone},
        }
        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]

        try:
            event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
            return self._parse_event(event)
        except HttpError as e:
            raise RuntimeError(f"Calendar create failed: {e}")

    def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        **updates,
    ) -> CalendarEvent:
        """Update an event (calendar.modify - ORANGE)."""
        self._ensure_scope("modify")
        service = self._get_service()

        # Get existing event first
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        # Apply updates
        for key, value in updates.items():
            if key in ("summary", "description", "location"):
                event[key] = value
            elif key == "start_time":
                event["start"] = {"dateTime": value, "timeZone": event["start"].get("timeZone", "UTC")}
            elif key == "end_time":
                event["end"] = {"dateTime": value, "timeZone": event["end"].get("timeZone", "UTC")}
            elif key == "timezone":
                event["start"]["timeZone"] = value
                event["end"]["timeZone"] = value
            elif key == "attendees":
                event["attendees"] = [{"email": email} for email in value]

        try:
            updated = service.events().update(
                calendarId=calendar_id, eventId=event_id, body=event
            ).execute()
            return self._parse_event(updated)
        except HttpError as e:
            raise RuntimeError(f"Calendar update failed: {e}")

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> None:
        """Delete an event (calendar.delete - RED)."""
        self._ensure_scope("delete")
        service = self._get_service()
        try:
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        except HttpError as e:
            raise RuntimeError(f"Calendar delete failed: {e}")

    # --- Verification (runbook §43) ---

    def verify_event_created(
        self,
        expected: CalendarEvent,
        calendar_id: str = "primary",
    ) -> tuple[bool, str]:
        """Verify that an event was created with expected properties (runbook §43)."""
        self._ensure_scope("read")
        service = self._get_service()

        try:
            # Search for events matching the summary around the expected time
            events_result = service.events().list(
                calendarId=calendar_id,
                q=expected.summary,
                timeMin=expected.start_time,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = events_result.get("items", [])
            for event in events:
                parsed = self._parse_event(event)
                # Check title
                if parsed.summary.lower() != expected.summary.lower():
                    continue
                # Check time (allow 1 minute tolerance)
                if abs(self._parse_time(parsed.start_time) - self._parse_time(expected.start_time)) > 60:
                    continue
                if abs(self._parse_time(parsed.end_time) - self._parse_time(expected.end_time)) > 60:
                    continue
                # Check timezone
                if parsed.timezone != expected.timezone:
                    continue
                # Check calendar ID
                if parsed.calendar_id != expected.calendar_id:
                    continue
                return True, f"Event verified: {parsed.id}"

            return False, "Event not found with matching properties"
        except HttpError as e:
            return False, f"Verification query failed: {e}"

    def verify_event_updated(
        self,
        event_id: str,
        expected_updates: dict,
        calendar_id: str = "primary",
    ) -> tuple[bool, str]:
        """Verify that an event was updated correctly."""
        self._ensure_scope("read")
        service = self._get_service()
        try:
            event = service.events().get(calendarId="primary", eventId=event_id).execute()
            parsed = self._parse_event(event)

            for key, expected_value in expected_updates.items():
                if key == "summary" and parsed.summary != expected_value:
                    return False, f"Summary mismatch: got '{parsed.summary}', expected '{expected_value}'"
                if key == "description" and parsed.description != expected_value:
                    return False, f"Description mismatch"
                if key == "location" and parsed.location != expected_value:
                    return False, f"Location mismatch"
                if key == "start_time" and parsed.start_time != expected_value:
                    return False, f"Start time mismatch"
                if key == "end_time" and parsed.end_time != expected_value:
                    return False, f"End time mismatch"
                if key == "timezone" and parsed.timezone != expected_value:
                    return False, f"Timezone mismatch"

            return True, "Event verified with all updates"
        except HttpError as e:
            return False, f"Verification query failed: {e}"

    def _parse_event(self, event: dict) -> CalendarEvent:
        """Parse Google Calendar API event into CalendarEvent."""
        start = event.get("start", {})
        end = event.get("end", {})
        start_time = start.get("dateTime", start.get("date", ""))
        end_time = end.get("dateTime", end.get("date", ""))
        timezone = start.get("timeZone", "UTC")

        return CalendarEvent(
            id=event.get("id", ""),
            summary=event.get("summary", ""),
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            calendar_id=event.get("organizer", {}).get("email", "primary"),
            description=event.get("description", ""),
            location=event.get("location", ""),
            attendees=[a.get("email", "") for a in event.get("attendees", [])],
            status=event.get("status", "confirmed"),
            html_link=event.get("htmlLink", ""),
            created=event.get("created", ""),
            updated=event.get("updated", ""),
        )

    def _parse_time(self, time_str: str) -> float:
        """Parse ISO datetime string to Unix timestamp."""
        try:
            from datetime import datetime
            return datetime.fromisoformat(time_str.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    def _ensure_scope(self, capability: str) -> None:
        """Ensure the active scopes include the required capability."""
        if capability in CALENDAR_SCOPES and CALENDAR_SCOPES[capability] not in self._active_scopes:
            raise PermissionError(f"Capability '{capability}' not authenticated. Call authenticate() first.")


@dataclass
class CalendarOAuthConfig:
    """Configuration for Calendar OAuth."""
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8080/oauth2callback"
    scopes: list[str] = field(default_factory=list)


class CalendarAuthManager:
    """Manages Calendar OAuth flow and token storage."""

    def __init__(
        self,
        secrets: "SecretStore",
        config: CalendarOAuthConfig,
    ) -> None:
        self.secrets = secrets
        self.config = config
        self._client: CalendarClient | None = None

    def get_client(self) -> CalendarClient:
        if self._client is None:
            self._client = CalendarClient(secrets=self.secrets)
        return self._client

    def authenticate(self, capabilities: list[str]) -> bool:
        """Run OAuth flow for the requested capabilities."""
        client = self.get_client()
        return client.authenticate(capabilities)

    def is_authenticated(self, capability: str) -> bool:
        """Check if a capability is currently authenticated."""
        client = self.get_client()
        return client._active_scopes is not None and CALENDAR_SCOPES.get(capability, "") in client._active_scopes


__all__ = [
    "CalendarClient",
    "CalendarEvent",
    "CalendarListEntry",
    "CalendarAuthManager",
    "CalendarOAuthConfig",
    "CalendarCredentials",
    "CALENDAR_SCOPES",
    "SCOPE_RISK_TIER",
]