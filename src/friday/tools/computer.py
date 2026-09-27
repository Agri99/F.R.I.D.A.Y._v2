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
from friday.computer import mouse
from friday.computer.controller import WindowsComputerController, Target
from friday.computer.screen import describe_screen, ocr, save_screenshot
from friday.computer.windows import WindowManager

_controller = WindowsComputerController()
_window_mgr = WindowManager()


def _mouse_move(x: int, y: int) -> dict[str, Any]:
    """Move cursor to screen coordinates (x, y)."""
    try:
        mouse.move(int(x), int(y))
        return {"status": "ok", "message": f"Moved mouse to ({x}, {y}).", "x": int(x), "y": int(y)}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        return {"status": "error", "message": f"Mouse move failed: {exc}"}


def _mouse_click(
    button: str = "left",
    x: int | None = None,
    y: int | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Click mouse button ('left', 'right', 'double') at coordinates (x, y) or current cursor position."""
    btn = (button or "left").lower().strip()
    cx = int(x) if x is not None else None
    cy = int(y) if y is not None else None
    try:
        if btn in ("right", "secondary", "rclick"):
            mouse.right_click(cx, cy)
            action = "Right-clicked"
        elif btn in ("double", "double_click", "dbl"):
            mouse.double_click(cx, cy)
            action = "Double-clicked"
        else:
            mouse.click(cx, cy)
            action = "Left-clicked"
        pos_str = f" at ({cx}, {cy})" if cx is not None and cy is not None else " at current position"
        return {"status": "ok", "message": f"{action}{pos_str}."}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        return {"status": "error", "message": f"Mouse click failed: {exc}"}


def _mouse_scroll(
    direction: str = "down",
    amount: int = 3,
    clicks: int | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Scroll mouse wheel up or down by amount (or direct clicks)."""
    try:
        if clicks is not None:
            n_clicks = int(clicks)
        else:
            dir_clean = (direction or "down").lower().strip()
            amt = abs(int(amount)) if amount else 3
            n_clicks = amt if "up" in dir_clean else -amt
        mouse.scroll(n_clicks)
        dir_desc = "up" if n_clicks > 0 else "down"
        return {"status": "ok", "message": f"Scrolled mouse wheel {dir_desc} by {abs(n_clicks)} clicks.", "clicks": n_clicks}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        return {"status": "error", "message": f"Mouse scroll failed: {exc}"}


def _mouse_drag(from_x: int, from_y: int, to_x: int, to_y: int) -> dict[str, Any]:
    """Drag mouse cursor from (from_x, from_y) to (to_x, to_y)."""
    try:
        mouse.drag(int(from_x), int(from_y), int(to_x), int(to_y))
        return {
            "status": "ok",
            "message": f"Dragged mouse from ({from_x}, {from_y}) to ({to_x}, {to_y}).",
        }
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        return {"status": "error", "message": f"Mouse drag failed: {exc}"}


def _capture_screen(filename: str = "screenshot.png") -> dict[str, Any]:
    """Capture current screen and save to workspace."""
    try:
        path = save_screenshot(filename)
        return {"status": "ok", "path": path, "message": "Screenshot captured successfully."}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
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
    label = text_label or kwargs.get("label")
    target = Target(coordinates=coords, text_label=label)
    result = _controller.click(target)
    if result.success:
        return {"status": "ok", "message": f"Clicked {label or f'coordinates ({x}, {y})' if coords else 'target'}."}
    return {"status": "error", "message": result.message}


def _type_text(text: str, text_label: str | None = None, **kwargs) -> dict[str, Any]:
    """Type text into foreground window or a labeled field."""
    try:
        # Small delay to ensure target window has focus
        time.sleep(0.5)
        target = Target(text_label=text_label or kwargs.get("label")) if text_label or kwargs.get("label") else None
        result = _controller.type_text(target, text)
        return {"status": "ok" if result.success else "error", "message": result.message}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        return {"status": "error", "message": f"Typing failed: {exc}"}


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

    # Get the active window name for natural responses
    active = _window_mgr.get_active_window()
    app_name = active.title.split(" - ")[-1] if active.title else "the window"

    if action in ("maximize", "maximise", "maximizr", "max"):
        success, msg = _window_mgr.maximize()
        action = "maximize"
    elif action in ("minimize", "minimise", "min"):
        success, msg = _window_mgr.minimize()
        action = "minimize"
    elif action in ("restore", "unmaximize", "unminimize"):
        success, msg = _window_mgr.restore()
        action = "restore"
    elif action in ("close", "exit", "quit"):
        success, msg = _window_mgr.close()
        action = "close"
    else:
        return {"status": "error", "message": f"Unknown window action: {action}"}

    if not success:
        return {"status": "error", "message": msg}
    return {"status": "ok", "action": action, "app_name": app_name, "message": msg}


def _minimize_all_windows() -> dict[str, Any]:
    """Minimize every visible top-level window (show desktop).

    Iterates all top-level windows via ``EnumWindows`` and sends
    ``SW_MINIMIZE`` to each visible window whose title is non-empty.
    Skips the FRIDAY orb and console window so the assistant stays usable.
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        SW_MINIMIZE = 6
        minimized: list[int] = []
        skipped: list[int] = []

        def _should_skip(title: str) -> bool:
            t = title.lower()
            return any(
                needle in t
                for needle in (
                    "friday",
                    "orb",
                    "windows input experience",
                    "windows shell experience",
                    "msctfime",
                    "default ime",
                )
            )

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            # Skip windows that don't belong to the user's foreground desktop
            ex_style = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            if ex_style & 0x80:  # WS_EX_TOOLWINDOW
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if _should_skip(title):
                skipped.append(hwnd)
                return True
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            minimized.append(hwnd)
            return True

        user32.EnumWindows(_enum, 0)
        return {
            "status": "ok",
            "minimized": len(minimized),
            "skipped": len(skipped),
            "message": f"Minimized {len(minimized)} window(s).",
        }
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        return {"status": "error", "message": str(exc)}


def _verify_minimize_all(args: dict, result: dict) -> VerificationResult:
    """Verify at least one window was minimized and none errored."""
    if result.get("status") != "ok":
        return VerificationResult(False, result.get("message", "Minimize-all failed."))
    if int(result.get("minimized", 0)) <= 0:
        return VerificationResult(False, "No windows were minimized.")
    return VerificationResult(True, f"Minimized {result.get('minimized')} window(s).")


def _verify_control_window(args: dict, result: dict) -> VerificationResult:
    if isinstance(result, dict) and result.get("status") == "ok":
        return VerificationResult(True, f"Window {result.get('action', 'controlled')} successfully")
    return VerificationResult(False, result.get("message", "Failed to control window"))


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
        name="computer.mouse_move",
        description="Move mouse cursor to screen coordinates (x, y).",
        tier="YELLOW",
        capability_scope="windows.interact",
        input_schema=build_schema({"x": {"type": "integer"}, "y": {"type": "integer"}}, ["x", "y"]),
        handler=_mouse_move,
    ))
    registry.register(Tool(
        name="computer.mouse_click",
        description="Click mouse button ('left', 'right', 'double') at coordinates (x, y) or current cursor position.",
        tier="YELLOW",
        capability_scope="windows.interact",
        input_schema=build_schema({
            "button": {"type": "string", "enum": ["left", "right", "double"]},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        }, []),
        handler=_mouse_click,
    ))
    registry.register(Tool(
        name="computer.mouse_scroll",
        description="Scroll mouse wheel up or down by amount (or direct clicks, positive = up, negative = down).",
        tier="YELLOW",
        capability_scope="windows.interact",
        input_schema=build_schema({
            "direction": {"type": "string", "enum": ["up", "down"]},
            "amount": {"type": "integer"},
            "clicks": {"type": "integer"},
        }, []),
        handler=_mouse_scroll,
    ))
    registry.register(Tool(
        name="computer.mouse_drag",
        description="Drag mouse from (from_x, from_y) to (to_x, to_y).",
        tier="YELLOW",
        capability_scope="windows.interact",
        input_schema=build_schema({
            "from_x": {"type": "integer"},
            "from_y": {"type": "integer"},
            "to_x": {"type": "integer"},
            "to_y": {"type": "integer"},
        }, ["from_x", "from_y", "to_x", "to_y"]),
        handler=_mouse_drag,
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
        verify=_verify_control_window,
    ))
    registry.register(Tool(
        name="computer.minimize_all_windows",
        description=(
            "Minimize every visible top-level window (show desktop). "
            "Skips the FRIDAY orb and IME/tool windows so the assistant "
            "stays reachable."
        ),
        tier="YELLOW",
        capability_scope="system.control",
        input_schema=build_schema({}),
        handler=_minimize_all_windows,
        verify=_verify_minimize_all,
    ))
