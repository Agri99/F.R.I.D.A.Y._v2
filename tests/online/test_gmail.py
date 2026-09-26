"""
tests/online/test_gmail.py

WHAT THIS IS FOR:
Unit tests for Gmail client — OAuth flow, message operations, send confirmation.
Platform-independent: mocks the Google API.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from friday.online.gmail import (
    GmailClient,
    GmailMessage,
    GMAIL_SCOPES,
    SCOPE_RISK_TIER,
)


class TestGmailScopes:
    def test_scope_map(self):
        assert "read" in GMAIL_SCOPES
        assert "send" in GMAIL_SCOPES
        assert "gmail.readonly" in GMAIL_SCOPES["read"]

    def test_risk_tiers(self):
        assert SCOPE_RISK_TIER["read"] == "GREEN"
        assert SCOPE_RISK_TIER["send"] == "ORANGE"
        assert SCOPE_RISK_TIER["modify"] == "RED"
        assert SCOPE_RISK_TIER["compose"] == "YELLOW"


class TestGmailMessage:
    def test_message_dataclass(self):
        msg = GmailMessage(
            id="msg123",
            thread_id="t123",
            from_addr="sender@example.com",
            to_addr="receiver@example.com",
            subject="Test",
            snippet="Hello",
        )
        assert msg.id == "msg123"
        assert msg.from_addr == "sender@example.com"
        assert msg.labels == []


class TestGmailClient:
    def test_require_scope_raises(self):
        mock_secrets = MagicMock()
        client = GmailClient(secrets=mock_secrets)
        with pytest.raises(PermissionError):
            client._ensure_scope("send")

    def test_require_scope_ok(self):
        mock_secrets = MagicMock()
        client = GmailClient(secrets=mock_secrets)
        client._active_scopes = [GMAIL_SCOPES["read"]]
        client._ensure_scope("read")

    def test_get_scopes_for_capabilities(self):
        mock_secrets = MagicMock()
        client = GmailClient(secrets=mock_secrets)
        scopes = client._get_scopes_for_capabilities(["read", "send"])
        assert GMAIL_SCOPES["read"] in scopes
        assert GMAIL_SCOPES["send"] in scopes

    def test_get_scopes_unknown_capability(self):
        mock_secrets = MagicMock()
        client = GmailClient(secrets=mock_secrets)
        with pytest.raises(ValueError, match="Unknown Gmail capability"):
            client._get_scopes_for_capabilities(["unknown_cap"])

    def test_create_message(self):
        mock_secrets = MagicMock()
        client = GmailClient(secrets=mock_secrets)
        msg = client._create_message("to@example.com", "Hello", "Subject")
        assert "raw" in msg
        assert isinstance(msg["raw"], str)
