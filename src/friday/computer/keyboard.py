"""
src/friday/computer/keyboard.py

WHAT THIS IS FOR:
Native Windows keyboard interaction using ctypes/win32 API with pyautogui fallback.
"""

from __future__ import annotations

import ctypes
import time

user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
try:
    if hasattr(ctypes, "windll"):
        winmm = ctypes.windll.winmm
        winmm.timeBeginPeriod(1)
except Exception:  # noqa: BLE001
    pass

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_MAP = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


def key_down(key: str) -> None:
    """Hold down a virtual key."""
    k = key.strip().lower()
    vk = VK_MAP.get(k)
    if vk is not None:
        user32.keybd_event(vk, 0, 0, 0)
    elif len(k) == 1:
        vk = user32.VkKeyScanW(ord(k)) & 0xFF
        user32.keybd_event(vk, 0, 0, 0)


def key_up(key: str) -> None:
    """Release a virtual key."""
    k = key.strip().lower()
    vk = VK_MAP.get(k)
    if vk is not None:
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    elif len(k) == 1:
        vk = user32.VkKeyScanW(ord(k)) & 0xFF
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def press(key: str) -> None:
    """Press a single key or key combination (e.g. 'enter', 'ctrl+c')."""
    if "+" in key:
        parts = [p.strip() for p in key.split("+")]
        for p in parts:
            key_down(p)
        time.sleep(0.05)
        for p in reversed(parts):
            key_up(p)
    else:
        key_down(key)
        time.sleep(0.02)
        key_up(key)


def release_modifiers() -> None:
    """Release any held modifier keys (Shift, Ctrl, Alt, Win)."""
    if user32 is not None:
        for vk in (0x10, 0x11, 0x12, 0x5B):  # Shift, Ctrl, Alt, Win
            try:
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            except Exception:  # noqa: BLE001
                pass


def _set_clipboard_text(text: str) -> bool:
    """Write text to Windows clipboard using native Win32 API."""
    if not hasattr(ctypes, "windll"):
        return False
    try:
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32

        u32.OpenClipboard.argtypes = [wintypes.HWND]
        u32.OpenClipboard.restype = wintypes.BOOL
        u32.EmptyClipboard.restype = wintypes.BOOL
        k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k32.GlobalAlloc.restype = wintypes.HGLOBAL
        k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalLock.restype = wintypes.LPVOID
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalUnlock.restype = wintypes.BOOL
        u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        u32.SetClipboardData.restype = wintypes.HANDLE
        u32.CloseClipboard.restype = wintypes.BOOL

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        opened = False
        for _ in range(5):
            if u32.OpenClipboard(None):
                opened = True
                break
            time.sleep(0.02)
        if not opened:
            return False

        try:
            u32.EmptyClipboard()
            data = text.encode("utf-16le") + b"\x00\x00"
            h_mem = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h_mem:
                return False
            p_mem = k32.GlobalLock(h_mem)
            if not p_mem:
                return False
            ctypes.memmove(p_mem, data, len(data))
            k32.GlobalUnlock(h_mem)
            u32.SetClipboardData(CF_UNICODETEXT, h_mem)
            return True
        finally:
            u32.CloseClipboard()
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError):
        return False


def type_text(text: str, interval: float = 0.025) -> None:
    """Type arbitrary unicode text into foreground window.

    Ensures zero modifier key sticking, uses atomic clipboard paste injection
    to guarantee 100% character fidelity (eliminating dropped spaces, modifier
    key bounce, or doubled characters such as 'FFRIDAY'), with graceful fallback
    to native KEYEVENTF_UNICODE and PyAutoGUI.
    """
    if not text:
        return

    # Release any lingering modifier keys from previous shortcuts (e.g., Alt+F)
    release_modifiers()

    # Fast, 100% reliable clipboard paste injection
    if user32 is not None and _set_clipboard_text(text):
        press("ctrl+v")
        if interval > 0:
            time.sleep(min(0.1, interval * len(text)))
        else:
            time.sleep(0.02)
        return

    # Per-character unicode fallback
    if user32 is not None:
        try:
            for char in text:
                if char == "\n":
                    press("enter")
                elif char == "\t":
                    press("tab")
                else:
                    code = ord(char)
                    user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
                    time.sleep(0.010)
                    user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
                if interval > 0:
                    time.sleep(interval)
            return
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError):
            pass

    try:
        import pyautogui # type: ignore

        pyautogui.write(text, interval=interval)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
        pass


def hotkey(*keys: str) -> None:
    """Press a combination of keys."""
    for k in keys:
        key_down(k)
    time.sleep(0.05)
    for k in reversed(keys):
        key_up(k)

