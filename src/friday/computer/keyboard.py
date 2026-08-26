"""
src/friday/computer/keyboard.py

WHAT THIS IS FOR:
Native Windows keyboard interaction using ctypes/win32 API with pyautogui fallback.
"""

from __future__ import annotations

import ctypes
import time

user32 = ctypes.windll.user32

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


def type_text(text: str, interval: float = 0.01) -> None:
    """Type arbitrary unicode text into foreground window."""
    try:
        import pyautogui
        pyautogui.write(text, interval=interval)
        return
    except Exception:
        pass

    for char in text:
        if char == "\n":
            press("enter")
        elif char == "\t":
            press("tab")
        else:
            # Send character as unicode event
            code = ord(char)
            user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
            user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
        if interval > 0:
            time.sleep(interval)


def hotkey(*keys: str) -> None:
    """Press a combination of keys."""
    for k in keys:
        key_down(k)
    time.sleep(0.05)
    for k in reversed(keys):
        key_up(k)
