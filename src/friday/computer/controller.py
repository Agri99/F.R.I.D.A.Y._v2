"""
src/friday/computer/controller.py

WHAT THIS IS FOR:
Unified ComputerController protocol and WindowsComputerController implementation
following the three-layer interaction architecture (API -> Accessibility -> Visual fallback)
and canonical observe -> act -> verify loop (blueprint §10).

Adds post-action verification and change detection for reliable computer use.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from .accessibility import AccessibilityProvider, UIElement
from .screen import (grab_screen_bytes, save_screenshot, ScreenObserver, Observation,
                     compute_screen_hash, compare_screens)
from .windows import WindowInfo, WindowManager
from .target_resolver import TargetResolver, ResolvedTarget, ResolutionMethod
from . import mouse
from . import keyboard


@dataclass
class ControllerObservation:
    """Represents the state of the system observed at a specific time."""
    screenshot_path: str | None
    accessibility_tree: list[UIElement]
    screen_hash: str
    active_window: str
    timestamp: float
    ocr_text: str = ""
    vlm_description: str = ""
    dialog_detected: bool = False
    popup_detected: bool = False
    error_state_detected: bool = False


@dataclass
class Target:
    """A target for an interaction."""
    element_id: str | None = None
    coordinates: tuple[int, int] | None = None
    text_label: str | None = None


@dataclass
class ActionResult:
    """Result of an interaction with verification."""
    success: bool
    message: str
    observation_before: ControllerObservation | None = None
    observation_after: ControllerObservation | None = None
    verification_passed: bool = False
    verification_reason: str = ""
    expected_change: str = ""
    actual_change: str = ""


class ComputerController(Protocol):
    """Protocol for computer control with observe-act-verify."""

    def capture(self, app: str | None = None) -> ControllerObservation:
        """Capture the current state of the computer."""
        ...

    def click(self, target: Target, expected_change: str = "") -> ActionResult:
        """Click on the given target with post-action verification."""
        ...

    def double_click(self, target: Target, expected_change: str = "") -> ActionResult:
        """Double click on the given target with post-action verification."""
        ...

    def type_text(self, target: Target | None, text: str, expected_change: str = "") -> ActionResult:
        """Type text into the given target with post-action verification."""
        ...

    def press(self, key: str, expected_change: str = "") -> ActionResult:
        """Press a keyboard key with post-action verification."""
        ...

    def scroll(self, amount: int, expected_change: str = "") -> ActionResult:
        """Scroll the mouse wheel with post-action verification."""
        ...

    def drag(self, source: Target, destination: Target, expected_change: str = "") -> ActionResult:
        """Drag from source to destination with post-action verification."""
        ...

    def wait(self, seconds: float) -> ActionResult:
        """Wait for a specific duration."""
        ...

    def active_window(self) -> WindowInfo:
        """Get information about the currently active window."""
        ...

    def verify_action(self, before: ControllerObservation, after: ControllerObservation,
                      expected_change: str) -> tuple[bool, str]:
        """Verify that an action produced the expected change."""
        ...


class WindowsComputerController:
    """Full implementation of ComputerController for Windows with observe-act-verify."""

    def __init__(self):
        self.accessibility = AccessibilityProvider()
        self.window_manager = WindowManager()
        self.target_resolver = TargetResolver(self.accessibility)
        self.screen_observer = ScreenObserver()
        self._last_observation: ControllerObservation | None = None

    def _capture_observation(self) -> ControllerObservation:
        """Capture current state with screen hash and accessibility tree."""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd) if hwnd else "Unknown"
        except Exception:
            title = "Unknown"

        img = grab_screen_bytes()
        screen_hash = ""
        ocr_text = ""
        vlm_desc = ""
        dialog = False
        popup = False
        error = False

        try:
            from PIL import Image
            import io
            if img:
                pil_img = Image.open(io.BytesIO(img))
                screen_hash = compute_screen_hash(pil_img)
                from friday.computer.screen import ocr
                ocr_text = ocr(pil_img)
        except Exception:
            pass

        screenshot_path = save_screenshot()
        controls = self.accessibility.get_controls()

        return ControllerObservation(
            screenshot_path=screenshot_path,
            accessibility_tree=controls,
            screen_hash=screen_hash,
            active_window=title,
            timestamp=time.time(),
            ocr_text=ocr_text,
            vlm_description=vlm_desc,
            dialog_detected=dialog,
            popup_detected=popup,
            error_state_detected=error,
        )

    def capture(self, app: str | None = None) -> ControllerObservation:
        """Capture current screen and accessibility tree."""
        obs = self._capture_observation()
        self._last_observation = obs
        return obs

    def _execute_and_verify(self, action_func, expected_change: str = "") -> ActionResult:
        """Execute an action with observe-act-verify loop."""
        # Observe before
        before = self._capture_observation()

        # Act
        result = action_func()

        # Small delay for UI to update
        time.sleep(0.3)

        # Observe after
        after = self._capture_observation()

        # Verify
        verified, reason = self.verify_action(before, after, expected_change)

        return ActionResult(
            success=result[0] if isinstance(result, tuple) else result.success,
            message=result[1] if isinstance(result, tuple) else result.message,
            observation_before=before,
            observation_after=after,
            verification_passed=verified,
            verification_reason=reason,
            expected_change=expected_change,
            actual_change=reason,
        )

    def click(self, target: Target, expected_change: str = "") -> ActionResult:
        """Click by semantic text label or by screen coordinates with verification."""

        def do_click():
            if target.text_label:
                element = self.accessibility.find_element_by_label(target.text_label)
                if element and self.accessibility.click_element(element):
                    return (True, f"Clicked control '{target.text_label}'")

            if target.coordinates:
                x, y = target.coordinates
                mouse.click(x, y)
                return (True, f"Clicked coordinates ({x}, {y})")

            return (False, f"Target '{target.text_label or target.coordinates}' could not be resolved or clicked")

        return self._execute_and_verify(do_click, expected_change)

    def double_click(self, target: Target, expected_change: str = "") -> ActionResult:
        """Double-click on coordinates with verification."""

        def do_double_click():
            if target.coordinates:
                x, y = target.coordinates
                mouse.double_click(x, y)
                return (True, f"Double-clicked coordinates ({x}, {y})")
            return (False, "Coordinates required for double-click")

        return self._execute_and_verify(do_double_click, expected_change)

    def type_text(self, target: Target | None, text: str, expected_change: str = "") -> ActionResult:
        """Type text into semantic control or directly to focused window with verification."""

        def do_type():
            # Focus the named field first if a label was given
            if target and target.text_label:
                element = self.accessibility.find_element_by_label(target.text_label)
                if element and self.accessibility.type_into_element(element, text):
                    return (True, f"Typed text into '{target.text_label}'")

            # Verify that a foreground window actually exists before sending keys
            win = self.window_manager.get_active_window()
            if not win or not win.title:
                return (False, "No foreground window found to type into")

            keyboard.type_text(text)
            return (True, f"Typed {len(text)} characters into '{win.title}'")

        return self._execute_and_verify(do_type, expected_change)

    def press(self, key: str, expected_change: str = "") -> ActionResult:
        """Press a keyboard key with verification."""

        def do_press():
            try:
                keyboard.press(key)
                return (True, f"Pressed key '{key}'")
            except Exception as exc:
                return (False, f"Failed to press key '{key}': {exc}")

        return self._execute_and_verify(do_press, expected_change)

    def scroll(self, amount: int, expected_change: str = "") -> ActionResult:
        """Scroll mouse wheel with verification."""

        def do_scroll():
            try:
                mouse.scroll(amount)
                return (True, f"Scrolled {amount} clicks")
            except Exception as exc:
                return (False, f"Scroll failed: {exc}")

        return self._execute_and_verify(do_scroll, expected_change)

    def drag(self, source: Target, destination: Target, expected_change: str = "") -> ActionResult:
        """Drag from source to destination coordinates with verification."""

        def do_drag():
            if source.coordinates and destination.coordinates:
                sx, sy = source.coordinates
                dx, dy = destination.coordinates
                mouse.drag(sx, sy, dx, dy)
                return (True, f"Dragged from ({sx}, {sy}) to ({dx}, {dy})")
            return (False, "Coordinates required for source and destination drag")

        return self._execute_and_verify(do_drag, expected_change)

    def wait(self, seconds: float) -> ActionResult:
        """Wait for duration."""
        time.sleep(max(0.0, seconds))
        return ActionResult(success=True, message=f"Waited {seconds} seconds")

    def active_window(self) -> WindowInfo:
        """Get active foreground window."""
        return self.window_manager.get_active_window()

    def execute_tool(self, tool_name: str, arguments: dict) -> ActionResult:
        """Execute a tool by name with given arguments."""
        # Get the tool from the registry
        tool = self._get_tool_from_registry(tool_name)
        if not tool:
            return ActionResult(
                success=False,
                message=f"Tool '{tool_name}' not found",
                verification_passed=False,
                verification_reason=f"Tool '{tool_name}' not found"
            )

        # Execute the tool
        try:
            if hasattr(tool, 'run'):
                result = tool.run(**arguments)
            elif hasattr(tool, 'handler'):
                result = tool.handler(**arguments)
            else:
                result = tool(**arguments)

            # Convert result to ActionResult
            if isinstance(result, dict):
                success = result.get('status') == 'ok'
                return ActionResult(
                    success=success,
                    message=result.get('message', str(result)),
                    verification_passed=success,
                    verification_reason="Tool executed successfully" if success else result.get('message', 'Unknown error')
                )
            else:
                return ActionResult(
                    success=True,
                    message=str(result),
                    verification_passed=True,
                    verification_reason="Tool executed successfully"
                )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Tool execution failed: {str(e)}",
                verification_passed=False,
                verification_reason=f"Exception: {str(e)}"
            )

    def _get_tool_from_registry(self, tool_name: str):
        """Get a tool from the global tool registry."""
        try:
            from friday.tools.registry import ToolRegistry
            from friday.tools.system import register_all_tools as reg_sys
            from friday.tools.filesystem import register_all_tools as reg_fs
            from friday.tools.applications import register_all_tools as reg_app
            from friday.tools.computer import register_all_tools as reg_comp
            from friday.tools.browser import register_all_tools as reg_browser
            from friday.tools.gmail import register_all_tools as reg_gmail
            from friday.tools.calendar import register_all_tools as reg_cal
            from friday.tools.scheduling import register_all_tools as reg_sched
            from friday.tools.audio import register_all_tools as reg_audio
            from friday.tools.terminal import register_all_tools as reg_term
            from friday.tools.online import register_all_tools as reg_online

            registry = ToolRegistry()
            reg_sys(registry)
            reg_fs(registry)
            reg_app(registry)
            reg_comp(registry)
            reg_browser(registry)
            reg_gmail(registry)
            reg_cal(registry)
            reg_sched(registry)
            reg_audio(registry)
            reg_term(registry)
            reg_online(registry)

            return registry.get(tool_name)
        except Exception:
            return None

    def verify_action(self, before: ControllerObservation, after: ControllerObservation,
                      expected_change: str) -> tuple[bool, str]:
        """Verify that an action produced the expected change.

        Returns (verified, reason)
        """
        if not expected_change:
            # No specific expectation - check for any significant change
            if before.screen_hash and after.screen_hash:
                cmp = compare_screens(before.screen_hash, after.screen_hash)
                if cmp["changed"]:
                    return True, f"Screen changed ({cmp['change_ratio']:.1%})"
            return True, "No specific expectation; action executed"

        expected_lower = expected_change.lower()

        # Check for specific expected changes
        # Window change
        if "window" in expected_lower or "app" in expected_lower:
            if before.active_window != after.active_window:
                return True, f"Window changed: {before.active_window} -> {after.active_window}"

        # Dialog/popup appearance
        if "dialog" in expected_lower or "popup" in expected_lower or "menu" in expected_lower:
            if after.dialog_detected and not before.dialog_detected:
                return True, "Dialog appeared"
            if after.popup_detected and not before.popup_detected:
                return True, "Popup/menu appeared"

        # Text appearance (for typing, search results, etc.)
        if "text" in expected_lower or "type" in expected_lower or "search" in expected_lower:
            # Check if new text appeared in OCR
            if after.ocr_text and expected_lower in after.ocr_text.lower():
                return True, f"Expected text found in OCR: {expected_change}"

        # Error state
        if "error" in expected_lower or "fail" in expected_lower:
            if after.error_state_detected:
                return True, "Error state detected"

        # Generic screen change
        if before.screen_hash and after.screen_hash:
            cmp = compare_screens(before.screen_hash, after.screen_hash)
            if cmp["changed"]:
                return True, f"Screen changed ({cmp['change_ratio']:.1%}) - may match expectation"

        return False, f"Expected change '{expected_change}' not verified. Screen: {before.active_window} -> {after.active_window}"

    def resolve_target(self, description: str, context: dict | None = None) -> ResolvedTarget | None:
        """Resolve a natural language target description using the target resolver."""
        return self.target_resolver.resolve(description, context)

    def get_last_observation(self) -> ControllerObservation | None:
        """Get the last captured observation."""
        return self._last_observation
