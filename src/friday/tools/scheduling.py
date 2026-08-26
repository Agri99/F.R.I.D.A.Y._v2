from __future__ import annotations
import threading
from .registry import Tool
from .metadata import build_schema

_timers = {}

def _fire_reminder(message: str) -> None:
    print(f"[reminder] {message}")

def _set(seconds: int, message: str = "Time's up.") -> dict:
    seconds = max(1, int(seconds))
    timer = threading.Timer(seconds, _fire_reminder, args=[message])
    timer.daemon = True
    timer.start()
    timer_id = str(id(timer))
    _timers[timer_id] = timer
    return {"status": "ok", "message": f"Timer set for {seconds} seconds.", "timer_id": timer_id}

def _cancel(timer_id: str) -> dict:
    timer = _timers.get(timer_id)
    if timer:
        timer.cancel()
        del _timers[timer_id]
        return {"status": "ok", "message": "Timer cancelled."}
    return {"status": "error", "message": "Timer not found."}

def register_all_tools(registry) -> None:
    registry.register(Tool(
        name="timer.set",
        description="Set reminder timer.",
        tier="GREEN",
        capability_scope="system.control",
        input_schema=build_schema({
            "seconds": {"type": "integer"},
            "message": {"type": "string"}
        }, ["seconds"]),
        handler=_set
    ))
    registry.register(Tool(
        name="timer.cancel",
        description="Cancel timer.",
        tier="GREEN",
        capability_scope="system.control",
        input_schema=build_schema({"timer_id": {"type": "string"}}, ["timer_id"]),
        handler=_cancel
    ))
