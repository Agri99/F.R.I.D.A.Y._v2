import datetime
from googleapiclient.discovery import build

from tools.registry import register_tool
from security.policy import RiskClass
from security.google_auth import get_credentials


@register_tool(risk=RiskClass.GREEN)
def check_calendar(max_results: int = 5, **kwargs) -> dict:
    max_results = kwargs.get("count", kwargs.get("limit", max_results))
    """Check upcoming events on the primary Google Calendar.

    Args:
        max_results: How many upcoming events to fetch (default 5, max 20).

    Returns:
        dict: list of upcoming events with start time and title
    """
    max_results = max(1, min(20, max_results))
    try:
        service = build("calendar", "v3", credentials=get_credentials())
        now = datetime.datetime.utcnow().isoformat() + "Z"
        results = service.events().list(
            calendarId="primary", timeMin=now, maxResults=max_results,
            singleEvents=True, orderBy="startTime",
        ).execute()

        events = [
            {"start": e["start"].get("dateTime", e["start"].get("date")),
             "title": e.get("summary", "(no title)")}
            for e in results.get("items", [])
        ]
        return {"status": "ok", "events": events}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": f"Could not check calendar: {exc}"}