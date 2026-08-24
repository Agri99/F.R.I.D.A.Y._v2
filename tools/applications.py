"""Allowlisted application launching.

The model only ever sees and requests an `app_id` — never a raw executable path.
The fixed mapping below is the entire launch surface; an id not in it is
rejected (fail closed), so the model cannot trick FRIDAY into running an
arbitrary program. Extend this table to grant FRIDAY access to more apps.
"""
import os
import sys

from tools.registry import register_tool
from security.policy import RiskClass

# app_id -> launch target. Targets may be an absolute path or a name resolvable
# on PATH (os.startfile / subprocess finds it). Add your own apps here.
APPS: dict[str, str] = {
    "vscode": r"C:\Users\agria\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "notepad": "notepad.exe",
    "explorer": "explorer.exe",
    "calculator": "calc.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
}


def _launch(target: str) -> None:
    """Open a target in the OS-native way. On Windows that's os.startfile."""
    if sys.platform == "win32":
        os.startfile(target)                 # noqa: S606 — typed allowlist only
    else:
        # macOS/other: 'open' is the equivalent of startfile.
        import subprocess
        subprocess.Popen(["open", target])   # noqa: S603 — typed allowlist only


@register_tool(risk=RiskClass.YELLOW)
def open_application(app_id: str) -> dict:
    """Open an application by its short id. Only apps on FRIDAY's allowlist can be opened.

    Args:
        app_id: One of the allowlisted app ids, e.g. 'vscode', 'notepad', 'explorer'.

    Returns:
        dict: status of the launch and the resolved app name
    """
    app_id = (app_id or "").strip().lower()
    if app_id not in APPS:
        return {"status": "error",
                "message": f"'{app_id}' is not on the application allowlist. "
                           f"Available apps: {', '.join(sorted(APPS))}"}
    target = APPS[app_id]
    try:
        _launch(target)
    except OSError as exc:
        return {"status": "error", "message": f"Could not open '{app_id}' ({target}): {exc}"}
    return {"status": "opened", "app_id": app_id, "target": target}
