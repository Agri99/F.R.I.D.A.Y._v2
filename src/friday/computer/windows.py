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

    def maximize(self) -> None:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd: win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

    def minimize(self) -> None:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd: win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

    def restore(self) -> None:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd: win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    def close(self) -> None:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd: win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

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
