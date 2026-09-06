"""
tests/online/test_calendar.py

WHAT THIS IS FOR:
Unit tests for Calendar client — OAuth flow, event operations, verification.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from friday.online.calendar import (
    CalendarClient,
    CalendarEvent,
    CalendarListEntry,
    CalendarOAuthConfig,
    CalendarAuthManager,
    CalendarCredentials,
    CALENDAR_SCOPES,
    SCOPE_RISK_TIER,
)


class TestCalendarScopes:
    def test_scope_map(self):
        assert "read" in CALENDAR_SCOPES
        assert "create" in CALENDAR_SCOPES
        assert "calendar.readonly" in CALENDAR_SCOPES["read"]

    def test_risk_tiers(self):
        assert SCOPE_RISK_TIER["read"] == "GREEN"
        assert SCOPE_RISK_TIER["create"] == "ORANGE"
        assert SCOPE_RISK_TIER["delete"] == "RED"


class TestCalendarEvent:
    def test_event_dataclass(self):
        event = CalendarEvent(
            id="evt123",
            summary="Meeting",
            start_time="2024-01-15T10:00:00Z",
            end_time="2024-01-15T11:00:00Z",
            timezone="UTC",
        )
        assert event.id == "evt123"
        assert event.summary == "Meeting"
        assert event.timezone == "UTC"


class TestCalendarClient:
    def test_require_scope_raises(self):
        mock_secrets = MagicMock()
        client = CalendarClient(secrets=mock_secrets)
        with pytest.raises(PermissionError):
            client._ensure_scope("create")

    def test_require_scope_ok(self):
        mock_secrets = MagicMock()
        client = CalendarClient(secrets=mock_secrets)
        client._active_scopes = [CALENDAR_SCOPES["read"]]
        client._ensure_scope("read")

    def test_get_scopes_for_capabilities(self):
        mock_secrets = MagicMock()
        client = CalendarClient(secrets=mock_secrets)
        scopes = client._get_scopes_for_capabilities(["read", "create"])
        assert CALENDAR_SCOPES["read"] in scopes
        assert CALENDAR_SCOPES["create"] in scopes

    def test_parse_time(self):
        mock_secrets = MagicMock()
        client = CalendarClient(secrets=mock_secrets)
        ts = client._parse_time("2024-01-15T10:00:00Z")
        assert ts > 0

    def test_parse_event(self):
        mock_secrets = MagicMock()
        client = CalendarClient(secrets=mock_secrets)
        event = {
            "id": "evt1",
            "summary": "Test",
            "start": {"dateTime": "2024-01-15T10:00:00Z", "timeZone": "UTC"},
            "end": {"dateTime": "2024-01-15T11:00:00Z", "timeZone": "UTC"},
            "description": "Desc",
            "location": "Room 1",
            "attendees": [{"email": "a@b.com"}],
            "status": "confirmed",
            "htmlLink": "link",
            "created": "2024-01-01T00:00:00Z",
            "updated": "2024-01-01T00:00:00Z",
        }
        parsed = CalendarClient(secrets=MagicMock())._parse_event(event)
        assert parsed.id == "evt1"
        assert parsed.summary == "Test"
        assert parsed.start_time == "2024-01-15T10:00:00Z"
        assert parsed.timezone == "UTC"


class TestCalendarAuthManager:
    def test_config_creation(self):
        config = CalendarOAuthConfig(
            client_id="cid",
            client_secret="csec",
            redirect_uri="http://localhost:8080/callback",
        )
        assert config.client_id == "cid"
        assert config.redirect_uri == "http://localhost:8080/callback"