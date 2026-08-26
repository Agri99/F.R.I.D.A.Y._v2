"""
src/friday/tools/calendar.py

WHAT THIS IS FOR:
Provides Google Calendar integration tools (list, create, update, delete) per blueprint §21, §46.
"""

from __future__ import annotations

import datetime
from typing import Any

from .registry import Tool, VerificationResult
from .metadata import build_schema


def _list(max_results: int = 5, **kwargs) -> dict[str, Any]:
    """Check upcoming events on primary Google Calendar."""
    from friday.security.google_auth import get_credentials
    from googleapiclient.discovery import build

    max_results = max(1, min(20, int(kwargs.get("count", kwargs.get("limit", max_results)))))
    try:
        service = build("calendar", "v3", credentials=get_credentials())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        results = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = [
            {
                "id": e.get("id"),
                "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date")),
                "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date")),
                "title": e.get("summary", "(no title)"),
                "location": e.get("location", ""),
            }
            for e in results.get("items", [])
        ]
        return {"status": "ok", "events": events, "count": len(events)}
    except FileNotFoundError as exc:
        return {"status": "error", "message": f"Calendar not configured: {exc}"}
    except Exception as exc:
        return {"status": "error", "message": f"Could not check calendar: {exc}"}


def _create(title: str, start: str, end: str, description: str = "") -> dict[str, Any]:
    """Create a new event on primary Google Calendar."""
    from friday.security.google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        service = build("calendar", "v3", credentials=get_credentials())
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start if "T" in start else f"{start}T09:00:00Z"},
            "end": {"dateTime": end if "T" in end else f"{end}T10:00:00Z"},
        }
        event = service.events().insert(calendarId="primary", body=body).execute()
        return {"status": "ok", "event_id": event.get("id"), "title": title, "start": start, "end": end}
    except Exception as exc:
        return {"status": "error", "message": f"Could not create event: {exc}"}


def _update(event_id: str, title: str | None = None, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """Update an existing calendar event."""
    from friday.security.google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        service = build("calendar", "v3", credentials=get_credentials())
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        if title:
            event["summary"] = title
        if start:
            event["start"] = {"dateTime": start if "T" in start else f"{start}T09:00:00Z"}
        if end:
            event["end"] = {"dateTime": end if "T" in end else f"{end}T10:00:00Z"}

        updated = service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        return {"status": "ok", "event_id": updated.get("id"), "title": updated.get("summary")}
    except Exception as exc:
        return {"status": "error", "message": f"Could not update event: {exc}"}


def _delete(event_id: str) -> dict[str, Any]:
    """Delete an event from Google Calendar."""
    from friday.security.google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        service = build("calendar", "v3", credentials=get_credentials())
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return {"status": "ok", "event_id": event_id, "deleted": True}
    except Exception as exc:
        return {"status": "error", "message": f"Could not delete event: {exc}"}


def _verify_create(args: dict, result: dict) -> VerificationResult:
    if isinstance(result, dict) and result.get("status") == "ok" and result.get("event_id"):
        return VerificationResult(True, f"Calendar event created with ID {result.get('event_id')}")
    return VerificationResult(False, result.get("message", "Failed to create calendar event"))


def register_all_tools(registry) -> None:
    registry.register(Tool(
        name="calendar.list",
        description="Check upcoming events on primary Google Calendar.",
        tier="GREEN",
        capability_scope="calendar.read",
        online_required=True,
        input_schema=build_schema({"max_results": {"type": "integer"}}, []),
        handler=_list,
    ))
    registry.register(Tool(
        name="calendar.create",
        description="Create an event on Google Calendar.",
        tier="ORANGE",
        capability_scope="calendar.write",
        online_required=True,
        input_schema=build_schema({
            "title": {"type": "string"},
            "start": {"type": "string"},
            "end": {"type": "string"},
            "description": {"type": "string"},
        }, ["title", "start", "end"]),
        handler=_create,
        verify=_verify_create,
    ))
    registry.register(Tool(
        name="calendar.update",
        description="Update an existing calendar event.",
        tier="ORANGE",
        capability_scope="calendar.write",
        online_required=True,
        input_schema=build_schema({
            "event_id": {"type": "string"},
            "title": {"type": "string"},
            "start": {"type": "string"},
            "end": {"type": "string"},
        }, ["event_id"]),
        handler=_update,
    ))
    registry.register(Tool(
        name="calendar.delete",
        description="Delete an event from Google Calendar.",
        tier="RED",
        capability_scope="calendar.write",
        online_required=True,
        critical=True,
        input_schema=build_schema({"event_id": {"type": "string"}}, ["event_id"]),
        handler=_delete,
    ))
