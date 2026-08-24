from tools.registry import register_tool
from security.policy import RiskClass

SHUTDOWN_REQUESTED = False


@register_tool(risk=RiskClass.RED)
def shutdown_friday() -> dict:
    """Shut down the FRIDAY assistant program entirely. Use only for explicit exit
    phrases like 'shut down', 'close yourself', 'stop running', 'goodbye Friday',
    'exit program'. Do not use this for 'go away', 'hide', or 'disappear' — those
    hide the orb with toggle_orb instead. Does not shut down the computer.

    Returns:
        dict: confirmation status
    """
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True
    return {"status": "ok", "message": "Shutting down."}