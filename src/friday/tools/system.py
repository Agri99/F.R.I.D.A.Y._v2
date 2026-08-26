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


def _get_time() -> dict:
    return {"time": datetime.datetime.now().isoformat(timespec="seconds")}


def _lock() -> dict:
    ctypes.windll.user32.LockWorkStation()
    return {"status": "locked"}


def _verify_lock(args: dict, result: dict) -> VerificationResult:
    return VerificationResult(True, "Session lock command executed")


SHUTDOWN_REQUESTED = False


def _shutdown_friday() -> dict:
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True
    return {"status": "shutting down", "message": "Shutting down FRIDAY. Goodbye!"}


def _toggle_orb(visible: bool = True, **kwargs) -> dict:
    from friday.ui.orb_server import set_orb_visibility
    vis = bool(visible)
    res = set_orb_visibility(vis)
    action_str = "shown" if vis else "hidden"
    return {"status": "ok", "visible": vis, "message": f"Orb has been {action_str}."}


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
        description="Get the current local date and time.",
        tier="GREEN",
        capability_scope="system.read",
        input_schema=build_schema({}),
        handler=_get_time,
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
    ))
    registry.register(Tool(
        name="toggle_orb",
        description="Show or hide the floating 3D visualizer orb.",
        tier="GREEN",
        capability_scope="system.control",
        input_schema=build_schema({"visible": {"type": "boolean"}}, ["visible"]),
        handler=_toggle_orb,
    ))
