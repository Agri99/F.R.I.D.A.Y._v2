from __future__ import annotations
import os
import sys
import time
from pathlib import Path
import psutil
from .registry import Tool, VerificationResult
from .metadata import build_schema


# Safe core utilities - Whitelist (GREEN tier, open directly without confirmation)
WHITELIST_APPS: dict[str, str] = {
    "vscode": r"C:\Users\agria\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "notepad": "notepad.exe",
    "text editor": "notepad.exe",
    "explorer": "explorer.exe",
    "calculator": "calc.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
}

# Alias for backward compatibility
APPS = WHITELIST_APPS

_INSTALLED_APPS_CACHE: dict[str, str] = {}


def _scan_installed_apps(force_refresh: bool = False) -> dict[str, str]:
    """Scan Windows Start Menu and Registry App Paths for all installed applications."""
    global _INSTALLED_APPS_CACHE
    if _INSTALLED_APPS_CACHE and not force_refresh:
        return _INSTALLED_APPS_CACHE

    discovered: dict[str, str] = {}

    if sys.platform == "win32":
        # 1. Start Menu Shortcuts (.lnk)
        for base in [os.environ.get("ProgramData", ""), os.environ.get("APPDATA", "")]:
            if not base:
                continue
            programs_dir = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if programs_dir.exists():
                try:
                    for item in programs_dir.rglob("*.lnk"):
                        name = item.stem.strip().lower()
                        # Skip uninstallers and helpers
                        if any(x in name for x in ("uninstall", "help", "readme", "documentation")):
                            continue
                        if name not in discovered:
                            discovered[name] = str(item)
                except Exception:
                    pass

        # 2. Registry App Paths
        try:
            import winreg
            for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root_key, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                        count = winreg.QueryInfoKey(key)[0]
                        for i in range(count):
                            sub_name = winreg.EnumKey(key, i)
                            try:
                                with winreg.OpenKey(key, sub_name) as subkey:
                                    val, _ = winreg.QueryValueEx(subkey, "")
                                    if val and os.path.exists(val):
                                        clean_name = sub_name.lower().replace(".exe", "").strip()
                                        if clean_name not in discovered:
                                            discovered[clean_name] = str(val)
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

    _INSTALLED_APPS_CACHE = discovered
    return _INSTALLED_APPS_CACHE


def _resolve_app(app_id: str) -> tuple[str, str, str]:
    """Resolve an app_id to (clean_name, target_path_or_exe, tier).

    Returns:
        (app_name, target_path, tier) where tier is 'GREEN' for whitelisted apps
        or 'ORANGE' for arbitrary installed apps.
    Raises:
        KeyError if not found.
    """
    clean = (app_id or "").strip().lower()

    # 1. Check Whitelist (GREEN)
    if clean in WHITELIST_APPS:
        return clean, WHITELIST_APPS[clean], "GREEN"

    for k, v in WHITELIST_APPS.items():
        if clean == k or clean == k.replace(" ", ""):
            return k, v, "GREEN"

    # 2. Check Discovered Installed Apps (ORANGE)
    installed = _scan_installed_apps()

    # Exact match
    if clean in installed:
        return clean, installed[clean], "ORANGE"

    # Match stem or normalized name
    for name, path in installed.items():
        if clean == name or clean == name.replace(" ", ""):
            return name, path, "ORANGE"

    # Substring / fuzzy match (e.g. 'chrome' matches 'google chrome')
    for name, path in installed.items():
        if clean in name or name in clean:
            return name, path, "ORANGE"

    # 3. Check system PATH
    import shutil
    found = shutil.which(clean) or shutil.which(f"{clean}.exe")
    if found:
        return clean, found, "ORANGE"

    raise KeyError(f"No application found with ID {app_id}")


def _open_app(app_id: str, force_new: bool = False, confirmed: bool = False) -> dict:
    app_id = (app_id or "").strip().lower()
    try:
        app_name, target, tier = _resolve_app(app_id)
    except KeyError:
        return {"status": "error", "message": f"No application found with ID {app_id}"}

    # If ORANGE tier and not confirmed, require voice/user authorization
    if tier == "ORANGE" and not confirmed:
        return {
            "status": "requires_confirmation",
            "tier": "ORANGE",
            "app_id": app_name,
            "target": target,
            "message": f"Opening '{app_name}' is an ORANGE-tier action requiring confirmation. Boss, should I proceed with opening {app_name}?",
        }

    # Check if already running unless force_new is true
    if not force_new:
        if app_name in ("notepad", "text editor"):
            names = ["notepad.exe"]
        elif app_name == "calculator":
            names = ["calculatorapp.exe", "calc.exe"]
        else:
            names = [Path(target).name.lower()]

        for p in psutil.process_iter(['name', 'pid']):
            try:
                p_name = p.info['name']
                if p_name and p_name.lower() in names:
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
                    return {
                        "status": "opened",
                        "tier": tier,
                        "app_id": app_name,
                        "message": f"{app_name} is already running. Restored and brought to foreground.",
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    try:
        if sys.platform == "win32":
            os.startfile(target)
        else:
            import subprocess
            subprocess.Popen(["open", target])
        return {
            "status": "opened",
            "tier": tier,
            "app_id": app_name,
            "target": target,
            "message": f"Opened {app_name}.",
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _list_installed_apps(query: str = "") -> dict:
    """List or search discovered installed applications."""
    installed = _scan_installed_apps()
    q = (query or "").strip().lower()
    if q:
        matches = [name for name in sorted(installed.keys()) if q in name]
    else:
        matches = sorted(installed.keys())
    return {
        "status": "ok",
        "count": len(matches),
        "apps": matches[:50],
    }


def _check_running(app_id: str) -> dict:
    app_id = (app_id or "").strip().lower()
    try:
        app_name, target, _ = _resolve_app(app_id)
    except KeyError:
        return {"status": "error", "message": f"No application found with ID {app_id}"}

    if app_name in ("notepad", "text editor"):
        names = ["notepad.exe"]
    elif app_name == "calculator":
        names = ["calculatorapp.exe", "calc.exe"]
    else:
        names = [Path(target).name.lower()]

    for p in psutil.process_iter(['name']):
        try:
            if p.info['name'] and p.info['name'].lower() in names:
                return {"status": "ok", "running": True, "message": f"{app_name} is running."}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return {"status": "ok", "running": False, "message": f"{app_name} is not running."}


def _verify_open_app(args: dict, result: dict) -> VerificationResult:
    if result.get("status") == "requires_confirmation":
        return VerificationResult(True, "Pending user confirmation for ORANGE tier action.")
    if result.get("status") != "opened":
        return VerificationResult(False, result.get("message", "Tool failed to launch app"))
    app_id = args.get("app_id", "").strip().lower()
    if app_id in ("notepad", "text editor"):
        names = ["notepad.exe"]
    elif app_id == "calculator":
        names = ["calculatorapp.exe", "calc.exe"]
    else:
        target = result.get("target") or APPS.get(app_id, "")
        names = [Path(target).name.lower()]

    start_t = time.time()
    while time.time() - start_t < 1.0:
        for p in psutil.process_iter(['name']):
            try:
                if p.info['name'] and p.info['name'].lower() in names:
                    return VerificationResult(True, f"Found process for {app_id}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.05)
    return VerificationResult(False, f"Process for {app_id} not found after 1s")


def _close_app(app_id: str) -> dict:
    app_id = (app_id or "").strip().lower()
    try:
        app_name, target, _ = _resolve_app(app_id)
    except KeyError:
        return {"status": "error", "message": f"No application found with ID {app_id}"}
    killed = 0
    names = [Path(target).name.lower()]
    for p in psutil.process_iter(['name']):
        try:
            if p.info['name'] and p.info['name'].lower() in names:
                p.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"status": "closed", "count": killed}


def _verify_close_app(args: dict, result: dict) -> VerificationResult:
    if isinstance(result, dict) and result.get("status") == "closed":
        return VerificationResult(True, f"Closed {args.get('app_id', 'application')}")
    return VerificationResult(False, "Failed to close application")


def register_all_tools(registry) -> None:
    registry.register(Tool(
        name="applications.open",
        description=(
            "Open an installed application. Whitelisted utilities (notepad, calculator, "
            "vscode, terminal, explorer) open directly (GREEN tier). All other installed "
            "applications are ORANGE tier and require user confirmation."
        ),
        tier="GREEN",
        capability_scope="system.control",
        input_schema=build_schema({
            "app_id": {"type": "string"},
            "confirmed": {"type": "boolean"},
            "force_new": {"type": "boolean"},
        }, ["app_id"]),
        handler=_open_app,
        verify=_verify_open_app,
    ))
    registry.register(Tool(
        name="applications.list_installed_apps",
        description="Search or list all installed applications on the computer.",
        tier="GREEN",
        capability_scope="system.read",
        input_schema=build_schema({"query": {"type": "string"}}, []),
        handler=_list_installed_apps,
    ))
    registry.register(Tool(
        name="applications.check_running",
        description="Check if an application is currently running.",
        tier="GREEN",
        capability_scope="system.read",
        input_schema=build_schema({"app_id": {"type": "string"}}, ["app_id"]),
        handler=_check_running,
    ))
    registry.register(Tool(
        name="applications.close",
        description="Close an application by name.",
        tier="YELLOW",
        capability_scope="system.control",
        input_schema=build_schema({"app_id": {"type": "string"}}, ["app_id"]),
        handler=_close_app,
        verify=_verify_close_app,
    ))
