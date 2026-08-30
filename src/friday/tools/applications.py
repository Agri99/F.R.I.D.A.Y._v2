from __future__ import annotations
import os
import sys
import time
from pathlib import Path
import psutil
from .registry import Tool, VerificationResult
from .metadata import build_schema


APPS: dict[str, str] = {
    "vscode": r"C:\Users\agria\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "notepad": "notepad.exe",
    "text editor": "notepad.exe",
    "explorer": "explorer.exe",
    "calculator": "calc.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
}

def _open_app(app_id: str, force_new: bool = False) -> dict:
    app_id = (app_id or "").strip().lower()
    if app_id not in APPS:
        return {"status": "error", "message": f"App not in allowlist. Available: {', '.join(APPS)}"}
    target = APPS[app_id]

    # Check if already running unless force_new is true
    if not force_new:
        if app_id == "notepad" or app_id == "text editor":
            names = ["notepad.exe"]
        elif app_id == "calculator":
            names = ["CalculatorApp.exe", "calc.exe"]
        else:
            names = [Path(target).name.lower()]

        for p in psutil.process_iter(['name', 'pid']):
            if p.info['name'] and p.info['name'].lower() in names:
                # Try to restore the window if minimized
                if sys.platform == "win32":
                    try:
                        import ctypes
                        hwnd = ctypes.windll.user32.FindWindowW(None, None)
                        if hwnd:
                            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                            ctypes.windll.user32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                return {"status": "opened", "message": f"{app_id} is already running. Restored and brought to foreground."}

    try:
        if sys.platform == "win32":
            os.startfile(target)
        else:
            import subprocess
            subprocess.Popen(["open", target])
        return {"status": "opened", "app_id": app_id, "target": target}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

def _check_running(app_id: str) -> dict:
    app_id = (app_id or "").strip().lower()
    if app_id not in APPS:
        return {"status": "error", "message": f"App not in allowlist. Available: {', '.join(APPS)}"}
    
    target = APPS[app_id]
    if app_id == "notepad" or app_id == "text editor":
        names = ["notepad.exe"]
    elif app_id == "calculator":
        names = ["CalculatorApp.exe", "calc.exe"]
    else:
        names = [Path(target).name.lower()]
        
    for p in psutil.process_iter(['name']):
        if p.info['name'] and p.info['name'].lower() in names:
            return {"status": "ok", "running": True, "message": f"{app_id} is running."}
            
    return {"status": "ok", "running": False, "message": f"{app_id} is not running."}

def _verify_open_app(args: dict, result: dict) -> VerificationResult:
    if result.get("status") != "opened":
        return VerificationResult(False, "Tool failed to launch app")
    # Wait and check processes
    time.sleep(2)
    app_id = args.get("app_id", "").strip().lower()
    if app_id == "notepad":
        names = ["notepad.exe"]
    elif app_id == "calculator":
        names = ["CalculatorApp.exe", "calc.exe"]
    else:
        names = [Path(APPS.get(app_id, "")).name.lower()]
        
    for p in psutil.process_iter(['name']):
        if p.info['name'] and p.info['name'].lower() in names:
            return VerificationResult(True, f"Found process for {app_id}")
    return VerificationResult(False, f"Process for {app_id} not found after 3s")

def _close_app(app_id: str) -> dict:
    # A simple process kill for demo purposes
    app_id = (app_id or "").strip().lower()
    if app_id not in APPS:
        return {"status": "error", "message": "App not in allowlist"}
    killed = 0
    names = [Path(APPS[app_id]).name.lower()]
    for p in psutil.process_iter(['name']):
        if p.info['name'] and p.info['name'].lower() in names:
            try:
                p.kill()
                killed += 1
            except Exception:
                pass
    return {"status": "closed", "count": killed}

def register_all_tools(registry) -> None:
    from pathlib import Path
    registry.register(Tool(
        name="applications.open",
        description="Open an allowlisted application.",
        tier="GREEN",
        capability_scope="system.control",
        input_schema=build_schema({"app_id": {"type": "string"}, "force_new": {"type": "boolean"}}, ["app_id"]),
        handler=_open_app,
        verify=_verify_open_app
    ))
    registry.register(Tool(
        name="applications.check_running",
        description="Check if an application is currently running.",
        tier="GREEN",
        capability_scope="system.read",
        input_schema=build_schema({"app_id": {"type": "string"}}, ["app_id"]),
        handler=_check_running
    ))
    registry.register(Tool(
        name="applications.close",
        description="Close an application by name.",
        tier="YELLOW",
        capability_scope="system.control",
        input_schema=build_schema({"app_id": {"type": "string"}}, ["app_id"]),
        handler=_close_app
    ))
