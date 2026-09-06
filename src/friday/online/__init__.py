"""
Online subsystem for F.R.I.D.A.Y. v2.
Handles network state, capability gating, search, and live data.
"""
from __future__ import annotations

from friday.online.gmail import (
    GmailClient,
    GmailMessage,
    GmailAuthManager,
    GmailOAuthConfig,
    GmailCredentials,
    GMAIL_SCOPES,
    SCOPE_RISK_TIER,
)

from friday.online.calendar import (
    CalendarClient,
    CalendarEvent,
    CalendarListEntry,
    CalendarAuthManager,
    CalendarOAuthConfig,
    CalendarCredentials,
    CALENDAR_SCOPES,
    SCOPE_RISK_TIER,
)

from friday.online.gate import (
    ConnectivityState,
    CapabilityGateConfig,
    OnlineCapabilityGate,
    get_capability_gate,
)

__all__ = [
    # Gmail
    "GmailClient",
    "GmailMessage",
    "GmailAuthManager",
    "GmailOAuthConfig",
    "GmailCredentials",
    "GMAIL_SCOPES",
    "SCOPE_RISK_TIER",
    # Calendar
    "CalendarClient",
    "CalendarEvent",
    "CalendarListEntry",
    "CalendarAuthManager",
    "CalendarOAuthConfig",
    "CalendarCredentials",
    "CALENDAR_SCOPES",
    "SCOPE_RISK_TIER",
    # Gate
    "ConnectivityState",
    "CapabilityGateConfig",
    "OnlineCapabilityGate",
    "get_capability_gate",
]
