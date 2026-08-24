import win32gui
import win32con

from tools.registry import register_tool
from security.policy import RiskClass


@register_tool(risk=RiskClass.YELLOW)
def control_active_window(action: str) -> dict:
    """Control the currently focused window: maximize, minimize, restore, or close.

    Args:
        action: One of 'maximize', 'minimize', 'restore', 'close'.

    Returns:
        dict: status and the window title acted on
    """
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return {"status": "error", "message": "No active window found."}

    title = win32gui.GetWindowText(hwnd)
    actions = {
        "maximize": lambda: win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE),
        "minimize": lambda: win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE),
        "restore": lambda: win32gui.ShowWindow(hwnd, win32con.SW_RESTORE),
        "close": lambda: win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0),
    }

    action = (action or "").strip().lower()
    if action not in actions:
        return {"status": "error", "message": f"Unknown action '{action}'. Use: {', '.join(actions)}"}

    actions[action]()
    return {"status": "ok", "action": action, "window": title}