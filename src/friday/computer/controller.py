"""
src/friday/computer/controller.py

WHAT THIS IS FOR:
Unified ComputerController protocol and WindowsComputerController implementation
following the three-layer interaction architecture (API -> Accessibility -> Visual fallback)
and canonical observe -> act -> verify loop (blueprint §10).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from .accessibility import AccessibilityProvider, UIElement
from .screen import grab_screen_bytes, save_screenshot
from .windows import WindowInfo, WindowManager
from . import mouse
from . import keyboard


@dataclass
class Observation:
    """Represents the state of the system observed at a specific time."""
    screenshot_path: str | None
    accessibility_tree: list[UIElement]
    timestamp: float


@dataclass
class Target:
    """A target for an interaction."""
    element_id: str | None = None
    coordinates: tuple[int, int] | None = None
    text_label: str | None = None


@dataclass
class ActionResult:
    """Result of an interaction."""
    success: bool
    message: str
    observation_after: Observation | None = None


class ComputerController(Protocol):
    """Protocol for computer control."""

    def capture(self, app: str | None = None) -> Observation:
        """Capture the current state of the computer."""
        ...

    def click(self, target: Target) -> ActionResult:
        """Click on the given target."""
        ...

    def double_click(self, target: Target) -> ActionResult:
        """Double click on the given target."""
        ...

    def type_text(self, target: Target | None, text: str) -> ActionResult:
        """Type text into the given target."""
        ...

    def press(self, key: str) -> ActionResult:
        """Press a keyboard key."""
        ...

    def scroll(self, amount: int) -> ActionResult:
        """Scroll the mouse wheel."""
        ...

    def drag(self, source: Target, destination: Target) -> ActionResult:
        """Drag from source to destination."""
        ...

    def wait(self, seconds: float) -> ActionResult:
        """Wait for a specific duration."""
        ...

    def active_window(self) -> WindowInfo:
        """Get information about the currently active window."""
        ...


class WindowsComputerController:
    """Full implementation of ComputerController for Windows."""

    def __init__(self):
        self.accessibility = AccessibilityProvider()
        self.window_manager = WindowManager()

    def capture(self, app: str | None = None) -> Observation:
        """Capture current screen and accessibility tree."""
        screenshot_path = save_screenshot()
        controls = self.accessibility.get_controls()
        return Observation(
            screenshot_path=screenshot_path,
            accessibility_tree=controls,
            timestamp=time.time(),
        )

    def click(self, target: Target) -> ActionResult:
        """Click by semantic text label or by screen coordinates."""
        if target.text_label:
            element = self.accessibility.find_element_by_label(target.text_label)
            if element and self.accessibility.click_element(element):
                return ActionResult(success=True, message=f"Clicked control '{target.text_label}'")

        if target.coordinates:
            x, y = target.coordinates
            mouse.click(x, y)
            return ActionResult(success=True, message=f"Clicked coordinates ({x}, {y})")

        return ActionResult(
            success=False,
            message=f"Target '{target.text_label or target.coordinates}' could not be resolved or clicked",
        )

    def double_click(self, target: Target) -> ActionResult:
        """Double-click on coordinates."""
        if target.coordinates:
            x, y = target.coordinates
            mouse.double_click(x, y)
            return ActionResult(success=True, message=f"Double-clicked coordinates ({x}, {y})")
        return ActionResult(success=False, message="Coordinates required for double-click")

    def type_text(self, target: Target | None, text: str) -> ActionResult:
        """Type text into semantic control or directly to focused window."""
        if target and target.text_label:
            element = self.accessibility.find_element_by_label(target.text_label)
            if element and self.accessibility.type_into_element(element, text):
                return ActionResult(success=True, message=f"Typed text into '{target.text_label}'")

        keyboard.type_text(text)
        return ActionResult(success=True, message=f"Typed {len(text)} characters into foreground window")

    def press(self, key: str) -> ActionResult:
        """Press a keyboard key."""
        try:
            keyboard.press(key)
            return ActionResult(success=True, message=f"Pressed key '{key}'")
        except Exception as exc:
            return ActionResult(success=False, message=f"Failed to press key '{key}': {exc}")

    def scroll(self, amount: int) -> ActionResult:
        """Scroll mouse wheel."""
        try:
            mouse.scroll(amount)
            return ActionResult(success=True, message=f"Scrolled {amount} clicks")
        except Exception as exc:
            return ActionResult(success=False, message=f"Scroll failed: {exc}")

    def drag(self, source: Target, destination: Target) -> ActionResult:
        """Drag from source to destination coordinates."""
        if source.coordinates and destination.coordinates:
            sx, sy = source.coordinates
            dx, dy = destination.coordinates
            mouse.drag(sx, sy, dx, dy)
            return ActionResult(success=True, message=f"Dragged from ({sx}, {sy}) to ({dx}, {dy})")
        return ActionResult(success=False, message="Coordinates required for source and destination drag")

    def wait(self, seconds: float) -> ActionResult:
        """Wait for duration."""
        time.sleep(max(0.0, seconds))
        return ActionResult(success=True, message=f"Waited {seconds} seconds")

    def active_window(self) -> WindowInfo:
        """Get active foreground window."""
        return self.window_manager.get_active_window()
