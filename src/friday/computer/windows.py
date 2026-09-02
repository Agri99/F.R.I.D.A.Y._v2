"""Window management logic."""
from __future__ import annotations
import win32gui
import win32con
import win32process
import psutil
import os
import sys
from dataclasses import dataclass


@dataclass
class WindowInfo:
    """Information about a window."""
    title: str
    process_name: str
    rect: tuple[int, int, int, int]
    is_foreground: bool


APPS: dict[str, str] = {
    "vscode": r"C:\Users\agria\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "notepad": "notepad.exe",
    "explorer": "explorer.exe",
    "calculator": "calc.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
}

class WindowManager:
    """Manages OS windows."""
    
    def get_active_window(self) -> WindowInfo:
        """Get the active window information."""
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return WindowInfo("", "", (0,0,0,0), False)
        
        title = win32gui.GetWindowText(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name()
        except Exception:
            process_name = ""
            
        return WindowInfo(title, process_name, rect, True)

    def _foreground_hwnd(self) -> int:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            raise RuntimeError("No foreground window available")
        return hwnd

    def _window_state(self, hwnd: int) -> str:
        placement = win32gui.GetWindowPlacement(hwnd)
        return placement[1] if len(placement) > 1 else "unknown"

    def maximize(self) -> tuple[bool, str]:
        try:
            hwnd = self._foreground_hwnd()
            title = win32gui.GetWindowText(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return True, f"Maximized '{title}'"
        except Exception as exc:
            return False, f"Maximize failed: {exc}"

    def minimize(self) -> tuple[bool, str]:
        try:
            hwnd = self._foreground_hwnd()
            title = win32gui.GetWindowText(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return True, f"Minimized '{title}'"
        except Exception as exc:
            return False, f"Minimize failed: {exc}"

    def restore(self) -> tuple[bool, str]:
        try:
            hwnd = self._foreground_hwnd()
            title = win32gui.GetWindowText(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            return True, f"Restored '{title}'"
        except Exception as exc:
            return False, f"Restore failed: {exc}"

    def close(self) -> tuple[bool, str]:
        try:
            hwnd = self._foreground_hwnd()
            title = win32gui.GetWindowText(hwnd)
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return True, f"Sent close to '{title}'"
        except Exception as exc:
            return False, f"Close failed: {exc}"

    def focus(self, title: str) -> None:
        """Focus a window by its exact or partial title."""
        def callback(hwnd, extra):
            if title.lower() in win32gui.GetWindowText(hwnd).lower():
                win32gui.SetForegroundWindow(hwnd)
        win32gui.EnumWindows(callback, None)

    def list_windows(self) -> list[WindowInfo]:
        """List all visible windows."""
        windows: list[WindowInfo] = []
        def callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                title = win32gui.GetWindowText(hwnd)
                rect = win32gui.GetWindowRect(hwnd)
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process_name = psutil.Process(pid).name()
                except Exception:
                    process_name = ""
                windows.append(WindowInfo(title, process_name, rect, False))
        win32gui.EnumWindows(callback, None)
        return windows

    def launch_application(self, app_id: str) -> bool:
        """Launch an application from the allowlist."""
        app_id = app_id.strip().lower()
        if app_id not in APPS:
            return False
            
        target = APPS[app_id]
        try:
            if sys.platform == "win32":
                os.startfile(target) # type: ignore
            else:
                import subprocess
                subprocess.Popen(["open", target])
            return True
        except OSError:
            return False
