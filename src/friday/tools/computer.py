"""
src/friday/tools/computer.py

WHAT THIS IS FOR:
Computer control and perception tools for F.R.I.D.A.Y. v2 (blueprint §10, §46).
Includes screen perception, OCR, vision description, mouse/keyboard control,
and window operations.
"""

from __future__ import annotations

import time
from typing import Any

from .registry import Tool, VerificationResult
from .metadata import build_schema
from friday.computer.controller import WindowsComputerController, Target
from friday.computer.screen import describe_screen, ocr, save_screenshot
from friday.computer.windows import WindowManager

_controller = WindowsComputerController()
_window_mgr = WindowManager()


def _capture_screen(filename: str = "screenshot.png") -> dict[str, Any]:
    """Capture current screen and save to workspace."""
    try:
        path = save_screenshot(filename)
        return {"status": "ok", "path": path}
    except Exception as exc:
        return {"status": "error", "message": f"Screen capture failed: {exc}"}


def _describe(question: str = "Describe what is on screen.") -> dict[str, Any]:
    """Use Ollama vision model (llava/gemma3/qwen3-vl) to describe the screen."""
    return describe_screen(question=question)


def _read_text() -> dict[str, Any]:
    """Read visible text on screen using OCR."""
    text = ocr()
    return {"status": "ok", "text": text}


def _click(
    x: int | None = None,
    y: int | None = None,
    text_label: str | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Click on screen coordinates or a button/menu item by visible text label."""
    coords = (int(x), int(y)) if x is not None and y is not None else None
    target = Target(coordinates=coords, text_label=text_label or kwargs.get("label"))
    result = _controller.click(target)
    return {"status": "ok" if result.success else "error", "message": result.message}


def _type_text(text: str, text_label: str | None = None, **kwargs) -> dict[str, Any]:
    """Type text into foreground window or a labeled field."""
    target = Target(text_label=text_label or kwargs.get("label")) if text_label or kwargs.get("label") else None
    result = _controller.type_text(target, text)
    return {"status": "ok" if result.success else "error", "message": result.message}


def _press_key(key: str) -> dict[str, Any]:
    """Press a key (e.g. 'enter', 'tab', 'esc', 'ctrl+c')."""
    result = _controller.press(key)
    return {"status": "ok" if result.success else "error", "message": result.message}


def _scroll(clicks: int = -3) -> dict[str, Any]:
    """Scroll mouse wheel (negative = down, positive = up)."""
    result = _controller.scroll(clicks)
    return {"status": "ok" if result.success else "error", "message": result.message}


def _wait(seconds: float = 1.0) -> dict[str, Any]:
    """Wait for specified seconds."""
    time.sleep(max(0.0, float(seconds)))
    return {"status": "ok", "waited_seconds": seconds}


def _active_window() -> dict[str, Any]:
    """Get active foreground window details."""
    info = _controller.active_window()
    return {
        "status": "ok",
        "title": info.title,
        "process": info.process_name,
        "rect": info.rect,
    }


def _control_window(action: str) -> dict[str, Any]:
    """Control foreground window: maximize, minimize, restore, or close."""
    action = action.strip().lower()
    if action == "maximize":
        _window_mgr.maximize()
    elif action == "minimize":
        _window_mgr.minimize()
    elif action == "restore":
        _window_mgr.restore()
    elif action == "close":
        _window_mgr.close()
    else:
        return {"status": "error", "message": f"Unknown window action: {action}"}
    return {"status": "ok", "action": action}


def register_all_tools(registry) -> None:
    registry.register(Tool(
        name="computer.capture",
        description="Capture screenshot and save to workspace.",
        tier="GREEN",
        capability_scope="windows.observe",
        input_schema=build_schema({"filename": {"type": "string"}}, []),
        handler=_capture_screen,
    ))
    registry.register(Tool(
        name="computer.describe_screen",
        description="Ask local Ollama vision model (llava/gemma3) to describe what is displayed on screen.",
        tier="GREEN",
        capability_scope="windows.observe",
        input_schema=build_schema({"question": {"type": "string"}}, []),
        handler=_describe,
    ))
    registry.register(Tool(
        name="computer.read_screen_text",
        description="Read verbatim text on screen using OCR (for documents, code, errors).",
        tier="GREEN",
        capability_scope="windows.observe",
        input_schema=build_schema({}),
        handler=_read_text,
    ))
    registry.register(Tool(
        name="computer.click",
        description="Click at screen coordinates (x, y) or on a button by visible label.",
        tier="YELLOW",
        capability_scope="windows.interact",
        input_schema=build_schema({
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "text_label": {"type": "string"},
        }, []),
        handler=_click,
    ))
    registry.register(Tool(
        name="computer.type",
        description="Type text into the active window or a labeled field.",
        tier="YELLOW",
        capability_scope="windows.interact",
        input_schema=build_schema({
            "text": {"type": "string"},
            "text_label": {"type": "string"},
        }, ["text"]),
        handler=_type_text,
    ))
    registry.register(Tool(
        name="computer.press",
        description="Press a keyboard key or hotkey (enter, tab, esc, f5).",
        tier="YELLOW",
        capability_scope="windows.interact",
        input_schema=build_schema({"key": {"type": "string"}}, ["key"]),
        handler=_press_key,
    ))
    registry.register(Tool(
        name="computer.scroll",
        description="Scroll mouse wheel (negative = down, positive = up).",
        tier="YELLOW",
        capability_scope="windows.interact",
        input_schema=build_schema({"clicks": {"type": "integer"}}, []),
        handler=_scroll,
    ))
    registry.register(Tool(
        name="computer.wait",
        description="Pause execution for a given number of seconds.",
        tier="GREEN",
        capability_scope="system.read",
        input_schema=build_schema({"seconds": {"type": "number"}}, ["seconds"]),
        handler=_wait,
    ))
    registry.register(Tool(
        name="computer.active_window",
        description="Get title, process name, and coordinates of the active window.",
        tier="GREEN",
        capability_scope="windows.observe",
        input_schema=build_schema({}),
        handler=_active_window,
    ))
    registry.register(Tool(
        name="computer.control_window",
        description="Control active window (maximize, minimize, restore, close).",
        tier="YELLOW",
        capability_scope="system.control",
        input_schema=build_schema({"action": {"type": "string"}}, ["action"]),
        handler=_control_window,
    ))
