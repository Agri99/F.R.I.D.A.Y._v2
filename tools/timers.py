import threading

from tools.registry import register_tool
from security.policy import RiskClass

_notify_callback = None  # set once at startup from test_voice.py


def set_notify_callback(callback) -> None:
    global _notify_callback
    _notify_callback = callback


def _fire_reminder(message: str) -> None:
    if _notify_callback:
        _notify_callback(message)
    else:
        print(f"[reminder] {message}")


@register_tool(risk=RiskClass.YELLOW)
def set_timer(seconds: int, message: str = "Time's up.") -> dict:
    """Set a one-time timer that speaks a reminder after a delay.

    Args:
        seconds: Delay in seconds before the reminder fires.
        message: What FRIDAY should say when the timer goes off.

    Returns:
        dict: confirmation the timer was scheduled
    """
    seconds = max(1, int(seconds))
    timer = threading.Timer(seconds, _fire_reminder, args=[message])
    timer.daemon = True
    timer.start()
    return {"status": "ok", "message": f"Timer set for {seconds} seconds."}