"""
src/friday/browser/active_tab.py

WHAT THIS IS FOR:
Detects the active browser window and inspects the currently open tab/URL
via Windows UI Automation and window enumeration without requiring the user
to manually copy-paste or speak a URL.
"""

from __future__ import annotations

import re
import sys
import threading
from dataclasses import dataclass
from typing import Any

BROWSER_PROCESSES = {
    "brave.exe",
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "opera.exe",
    "vivaldi.exe",
    "arc.exe",
}

BROWSER_TITLE_SUFFIXES = re.compile(
    r"\s+-\s+(?:Brave|Google Chrome|Microsoft Edge|Personal\s+-\s+Microsoft Edge|Mozilla Firefox|Opera|Vivaldi)$",
    re.IGNORECASE,
)


@dataclass
class ActiveBrowserInfo:
    url: str | None = None
    title: str | None = None
    browser: str | None = None
    hwnd: int | None = None


def _ensure_default_desktop() -> None:
    """Ensure the calling thread has access to the interactive user desktop station."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        h_def = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if h_def:
            user32.SetThreadDesktop(h_def)
    except Exception:
        pass


def _detect_browser_worker(result_container: list[ActiveBrowserInfo | None]) -> None:
    _ensure_default_desktop()

    try:
        import win32gui
        import win32process
        import psutil
    except ImportError:
        return

    candidate_hwnds: list[tuple[int, str, str]] = []

    # 1. Check foreground window first
    fg_hwnd = win32gui.GetForegroundWindow()
    if fg_hwnd and win32gui.IsWindowVisible(fg_hwnd):
        try:
            _, pid = win32process.GetWindowThreadProcessId(fg_hwnd)
            pname = psutil.Process(pid).name().lower()
            if pname in BROWSER_PROCESSES:
                title = win32gui.GetWindowText(fg_hwnd)
                candidate_hwnds.append((fg_hwnd, pname, title))
        except Exception:
            pass

    # 2. If foreground window isn't a browser, enumerate visible top-level windows
    if not candidate_hwnds:
        def _enum_cb(hwnd: int, _: Any) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.strip():
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        pname = psutil.Process(pid).name().lower()
                        if pname in BROWSER_PROCESSES:
                            candidate_hwnds.append((hwnd, pname, title))
                    except Exception:
                        pass
            return True

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception:
            pass

    if not candidate_hwnds:
        return

    for hwnd, pname, title in candidate_hwnds:
        cleaned_title = BROWSER_TITLE_SUFFIXES.sub("", title).strip()
        detected_url: str | None = None

        # Try extracting URL via UIA edit control (address bar)
        try:
            from pywinauto import Application

            app = Application(backend="uia").connect(handle=hwnd)
            win = app.window(handle=hwnd)
            edits = win.descendants(control_type="Edit")
            for e in edits:
                val = ""
                try:
                    val = e.get_value() if hasattr(e, "get_value") else ""
                except Exception:
                    pass
                if not val:
                    try:
                        val = e.window_text()
                    except Exception:
                        pass
                val = (val or "").strip()
                # Check if it looks like a URL or domain
                if val and ("." in val or val.startswith("http://") or val.startswith("https://")):
                    # Avoid placeholder strings like "Search Google or type a URL"
                    if "search or enter" in val.lower() or "type a url" in val.lower():
                        continue
                    if not val.startswith(("http://", "https://")):
                        val = f"https://{val}"
                    detected_url = val
                    break
        except Exception:
            pass

        # If no URL in address bar, check if cleaned title looks like a URL or domain
        if not detected_url and cleaned_title:
            if "." in cleaned_title and " " not in cleaned_title:
                detected_url = f"https://{cleaned_title}"

        result_container[0] = ActiveBrowserInfo(
            url=detected_url,
            title=cleaned_title or title,
            browser=pname.replace(".exe", ""),
            hwnd=hwnd,
        )
        return


def get_active_browser_info(timeout: float = 6.0) -> ActiveBrowserInfo | None:
    """
    Detect the active or topmost visible browser window (Brave, Chrome, Edge, etc.)
    and extract its active tab URL and title.
    Runs on a dedicated worker thread to ensure clean desktop station switching.
    """
    if sys.platform != "win32":
        return None

    container: list[ActiveBrowserInfo | None] = [None]
    t = threading.Thread(target=_detect_browser_worker, args=(container,), daemon=True)
    t.start()
    t.join(timeout=timeout)
    return container[0]

