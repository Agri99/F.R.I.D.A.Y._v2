"""
src/friday/tools/system.py

WHAT THIS IS FOR:
Provides operating system metrics, local datetime, workstation locking,
orb visibility controls, and graceful assistant shutdown tools.
"""

from __future__ import annotations

import datetime
import ctypes
import psutil
from .registry import Tool, VerificationResult
from .metadata import build_schema


def _get_status() -> dict:
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_free_gb": round(psutil.disk_usage("C:\\").free / (1024 ** 3), 1),
    }


def _verify_get_status(args: dict, result: dict) -> VerificationResult:
    if "cpu_percent" in result and "ram_percent" in result:
        return VerificationResult(True, "Status keys present")
    return VerificationResult(False, "Missing expected keys in status result")


# Common city-to-timezone mapping for user convenience
# Also includes explicit UTC offsets as fallback when ZoneInfo DB is unavailable
_CITY_TO_IANA = {
    "tokyo": "Asia/Tokyo",
    "new york": "America/New_York",
    "london": "Europe/London",
    "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "sf": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "denver": "America/Denver",
    "phoenix": "America/Phoenix",
    "houston": "America/Chicago",
    "dallas": "America/Chicago",
    "miami": "America/New_York",
    "seattle": "America/Los_Angeles",
    "boston": "America/New_York",
    "washington": "America/New_York",
    "dc": "America/New_York",
    "washington dc": "America/New_York",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "moscow": "Europe/Moscow",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "singapore": "Asia/Singapore",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "auckland": "Pacific/Auckland",
    "dubai": "Asia/Dubai",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
    "chennai": "Asia/Kolkata",
    "seoul": "Asia/Seoul",
    "taipei": "Asia/Taipei",
    "bangkok": "Asia/Bangkok",
    "jakarta": "Asia/Jakarta",
    "manila": "Asia/Manila",
    "kuala lumpur": "Asia/Kuala_Lumpur",
}

# Explicit UTC offsets for when ZoneInfo database is unavailable
# Format: city_name -> (offset_hours, offset_minutes)
_CITY_TO_UTC_OFFSET = {
    "tokyo": (9, 0),
    "new york": (-5, 0),      # EST (will be -4 during DST)
    "london": (0, 0),         # GMT (will be +1 during BST)
    "los angeles": (-8, 0),   # PST (will be -7 during PDT)
    "la": (-8, 0),
    "san francisco": (-8, 0),
    "sf": (-8, 0),
    "chicago": (-6, 0),       # CST (will be -5 during CDT)
    "denver": (-7, 0),        # MST (will be -6 during MDT)
    "phoenix": (-7, 0),       # MST (no DST)
    "houston": (-6, 0),
    "dallas": (-6, 0),
    "miami": (-5, 0),
    "seattle": (-8, 0),
    "boston": (-5, 0),
    "washington": (-5, 0),
    "dc": (-5, 0),
    "washington dc": (-5, 0),
    "paris": (1, 0),          # CET (will be +2 during CEST)
    "berlin": (1, 0),
    "moscow": (3, 0),
    "beijing": (8, 0),
    "shanghai": (8, 0),
    "hong kong": (8, 0),
    "singapore": (8, 0),
    "sydney": (10, 0),        # AEST (will be +11 during AEDT)
    "melbourne": (10, 0),
    "auckland": (12, 0),      # NZST (will be +13 during NZDT)
    "dubai": (4, 0),
    "mumbai": (5, 30),
    "delhi": (5, 30),
    "bangalore": (5, 30),
    "kolkata": (5, 30),
    "chennai": (5, 30),
    "seoul": (9, 0),
    "taipei": (8, 0),
    "bangkok": (7, 0),
    "jakarta": (7, 0),
    "manila": (8, 0),
    "kuala lumpur": (8, 0),
}


def _get_time(timezone: str | None = None, **kwargs) -> dict:
    """Return the current time.

    ``timezone`` accepts an IANA name (e.g. ``"America/New_York"``) or a
    fixed-offset string (e.g. ``"+05:30"``, ``"UTC-8"``). When None or
    unrecognised, the host's local time is returned.

    For convenience, common city names (e.g. "tokyo", "new york") are also
    accepted and mapped to their IANA timezone.
    """
    tzinfo = None
    tz_name = "local"
    if timezone:
        tz_key = timezone.strip().lower()
        # Try city mapping first (for IANA zoneinfo)
        if tz_key in _CITY_TO_IANA:
            timezone = _CITY_TO_IANA[tz_key]
        try:
            from zoneinfo import ZoneInfo
            tzinfo = ZoneInfo(timezone)
        except Exception:
            # ZoneInfo database not available on this system (e.g. Windows without tzdata).
            # First try the raw key as a city name.
            if tz_key in _CITY_TO_UTC_OFFSET:
                hours, minutes = _CITY_TO_UTC_OFFSET[tz_key]
                from datetime import timezone as dt_timezone, timedelta
                tzinfo = dt_timezone(timedelta(hours=hours, minutes=minutes))
                tz_name = f"UTC{hours:+d}:{minutes:02d}"
            else:
                # If the timezone looks like an IANA name (e.g. "America/New_York"),
                # extract the city part ("new york") and try the city offset map.
                city_part = timezone.split("/")[-1].replace("_", " ").lower()
                if city_part in _CITY_TO_UTC_OFFSET:
                    hours, minutes = _CITY_TO_UTC_OFFSET[city_part]
                    from datetime import timezone as dt_timezone, timedelta
                    tzinfo = dt_timezone(timedelta(hours=hours, minutes=minutes))
                    tz_name = f"{timezone} (UTC{hours:+d}:{minutes:02d})"
                else:
                    # Last resort: try fixed offset parser (e.g. "+05:30", "UTC-8")
                    tzinfo = _parse_offset(timezone)
        if tzinfo is None:
            # Could not resolve the timezone at all — fall back to local time with
            # an honest label so FRIDAY doesn't silently claim the wrong timezone.
            tz_name = f"{timezone} (fallback to local — tzdata not installed)"
    now = datetime.datetime.now(tz=tzinfo)
    if tzinfo is not None and tz_name == "local":
        tz_name = str(tzinfo)
    elif tzinfo is None and not tz_name.endswith(")"):
        if timezone and timezone not in ("local", ""):
            tz_name = f"{timezone} (fallback to local — tzdata not installed)"
        else:
            tz_name = "local"
    return {
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "timezone": tz_name,
    }


def _parse_offset(spec: str) -> datetime.tzinfo | None:
    """Parse ``"+HH:MM"`` / ``"-HH:MM"`` / ``"UTC-8"`` into a tzinfo."""
    spec = spec.strip()
    sign = 1
    body = spec
    if body.startswith("UTC") or body.startswith("utc"):
        body = body[3:].strip()
    if body.startswith("+"):
        sign = 1
        body = body[1:]
    elif body.startswith("-"):
        sign = -1
        body = body[1:]
    if not body:
        return None
    if ":" in body:
        h_s, m_s = body.split(":", 1)
    else:
        h_s, m_s = body, "0"
    try:
        hours = int(h_s)
        minutes = int(m_s)
    except ValueError:
        return None
    return datetime.timezone(datetime.timedelta(hours=sign * hours, minutes=sign * minutes))


def _lock() -> dict:
    ctypes.windll.user32.LockWorkStation()
    return {"status": "locked"}


def _verify_lock(args: dict, result: dict) -> VerificationResult:
    return VerificationResult(True, "Session lock command executed")


SHUTDOWN_REQUESTED = False


def _shutdown_friday() -> dict:
    """Shut down FRIDAY gracefully.

    Sets the global shutdown flag and returns a result. The caller
    (voice loop in app.py) is responsible for actually exiting the process.
    """
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True
    return {"status": "shutting down", "message": "Shutting down FRIDAY. Goodbye!"}


def _verify_get_time(args: dict, result: dict) -> VerificationResult:
    if isinstance(result, dict) and "time" in result:
        return VerificationResult(True, f"Current time is {result.get('time')}")
    return VerificationResult(False, "Failed to retrieve current time")


def _toggle_orb(visible: bool = True, **kwargs) -> dict:
    from friday.ui.orb_server import set_orb_visibility
    vis = bool(visible)
    res = set_orb_visibility(vis)
    action_str = "shown" if vis else "hidden"
    return {"status": "ok", "visible": vis, "message": f"Orb has been {action_str}."}


def _verify_toggle_orb(args: dict, result: dict) -> VerificationResult:
    if isinstance(result, dict) and result.get("status") == "ok":
        return VerificationResult(True, result.get("message", "Orb toggled successfully"))
    return VerificationResult(False, "Failed to toggle orb")


def register_all_tools(registry) -> None:
    registry.register(Tool(
        name="system.get_status",
        description="Get current CPU, RAM, and disk usage.",
        tier="GREEN",
        capability_scope="system.read",
        input_schema=build_schema({}),
        handler=_get_status,
        verify=_verify_get_status,
    ))
    registry.register(Tool(
        name="system.get_time",
        description=(
            "Get the current date and time. Pass an IANA timezone name "
            "(e.g. 'America/New_York') or fixed offset (e.g. '+05:30', "
            "'UTC-8') to convert. Without a timezone argument, returns "
            "the host's local time."
        ),
        tier="GREEN",
        capability_scope="system.read",
        input_schema=build_schema(
            {
                "timezone": {
                    "type": "string",
                    "description": "Optional specific timezone or city (e.g. 'Tokyo', 'London'). Omit or leave empty for the user's local time.",
                }
            },
            required=[],
        ),
        handler=_get_time,
        verify=_verify_get_time,
    ))
    registry.register(Tool(
        name="system.lock",
        description="Lock the workstation.",
        tier="ORANGE",
        capability_scope="system.control",
        input_schema=build_schema({}),
        handler=_lock,
        verify=_verify_lock,
    ))
    registry.register(Tool(
        name="system.shutdown_friday",
        description="Shut down the FRIDAY assistant program.",
        tier="ORANGE",
        capability_scope="system.control",
        input_schema=build_schema({}),
        handler=_shutdown_friday,
        critical=False,
    ))
    registry.register(Tool(
        name="shutdown_friday",
        description="Shut down the FRIDAY assistant program.",
        tier="ORANGE",
        capability_scope="system.control",
        input_schema=build_schema({}),
        handler=_shutdown_friday,
        critical=False,
    ))

    registry.register(Tool(
        name="system.toggle_orb",
        description="Show or hide the floating 3D visualizer orb.",
        tier="GREEN",
        capability_scope="system.control",
        input_schema=build_schema({"visible": {"type": "boolean"}}, ["visible"]),
        handler=_toggle_orb,
        verify=_verify_toggle_orb,
    ))
    registry.register(Tool(
        name="toggle_orb",
        description="Show or hide the floating 3D visualizer orb.",
        tier="GREEN",
        capability_scope="system.control",
        input_schema=build_schema({"visible": {"type": "boolean"}}, ["visible"]),
        handler=_toggle_orb,
        verify=_verify_toggle_orb,
    ))

    def _remember(fact: str) -> dict:
        from friday.memory.database import MemoryDatabase
        from friday.memory.semantic import SemanticMemory
        try:
            # We must instantiate it or access it, but tool handler gets called dynamically.
            # Using the main db path.
            db = MemoryDatabase("data/friday.db")
            mem = SemanticMemory(db)
            mem.store_fact(subject="User", predicate="stated", value=fact, source="user_explicit", confidence=1.0)
            return {"status": "ok", "message": "Fact stored successfully."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    registry.register(Tool(
        name="system.remember",
        description="Explicitly store a fact or preference in persistent long-term semantic memory. Use this when the user asks you to remember something.",
        tier="GREEN",
        capability_scope="system.read",
        input_schema=build_schema({"fact": {"type": "string", "description": "The information to remember."}}, ["fact"]),
        handler=_remember,
    ))
