"""
src/friday/computer/mouse.py

WHAT THIS IS FOR:
Native Windows mouse interaction using ctypes/win32 API with pyautogui fallback.
"""

from __future__ import annotations

import ctypes
import time

user32 = ctypes.windll.user32

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x00010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000


def move(x: int, y: int) -> None:
    """Move cursor to screen coordinates."""
    try:
        import pyautogui
        pyautogui.moveTo(x, y)
    except Exception:
        user32.SetCursorPos(int(x), int(y))


def click(x: int | None = None, y: int | None = None) -> None:
    """Left click at current position or specified coordinates."""
    if x is not None and y is not None:
        move(x, y)
        time.sleep(0.05)
    try:
        import pyautogui
        pyautogui.click()
    except Exception:
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def double_click(x: int | None = None, y: int | None = None) -> None:
    """Double-click at current position or specified coordinates."""
    if x is not None and y is not None:
        move(x, y)
        time.sleep(0.05)
    try:
        import pyautogui
        pyautogui.doubleClick()
    except Exception:
        click()
        time.sleep(0.1)
        click()


def right_click(x: int | None = None, y: int | None = None) -> None:
    """Right click at current position or specified coordinates."""
    if x is not None and y is not None:
        move(x, y)
        time.sleep(0.05)
    try:
        import pyautogui
        pyautogui.rightClick()
    except Exception:
        user32.mouse_event(MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def drag(from_x: int, from_y: int, to_x: int, to_y: int) -> None:
    """Drag from source to destination coordinates."""
    try:
        import pyautogui
        pyautogui.moveTo(from_x, from_y)
        pyautogui.dragTo(to_x, to_y, button="left")
    except Exception:
        move(from_x, from_y)
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        move(to_x, to_y)
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def scroll(amount: int) -> None:
    """Scroll mouse wheel (positive = up, negative = down)."""
    try:
        import pyautogui
        pyautogui.scroll(amount)
    except Exception:
        wheel_delta = int(amount) * 120
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, wheel_delta, 0)
