"""
src/friday/computer/accessibility.py

WHAT THIS IS FOR:
Windows UI Automation (Layer 2 of computer interaction, blueprint §10.1).
Resolves and interacts with buttons, menu items, tabs, and edit fields in
allowlisted applications (notepad, calculator, vscode) without guessing coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psutil
import win32gui
import win32process

AUTOMATION_ALLOWLIST: dict[str, set[str]] = {
    "notepad": {"notepad.exe"},
    "calculator": {"calculatorapp.exe", "calc.exe"},
    "vscode": {"code.exe"},
}

_TYPE_PRIORITY = {"Button": 0, "MenuItem": 1, "TabItem": 2, "Edit": 3}


@dataclass
class UIElement:
    name: str
    control_type: str
    automation_id: str
    bounding_rect: tuple[int, int, int, int] | None
    is_enabled: bool
    _raw_element: Any = None


class AccessibilityProvider:
    """Provides access to Windows UI Automation controls within allowlisted apps."""

    def find_allowlisted_window(self) -> tuple[str | None, int | None, str | None]:
        """Find the active or single allowlisted application window."""
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                exe_name = psutil.Process(pid).name().lower()
                for app_id, exe_names in AUTOMATION_ALLOWLIST.items():
                    if exe_name in exe_names:
                        return app_id, hwnd, None
            except Exception:
                pass

        candidates: list[tuple[str, int]] = []

        def _enum_handler(candidate_hwnd: int, _: Any) -> None:
            if not win32gui.IsWindowVisible(candidate_hwnd) or not win32gui.GetWindowText(candidate_hwnd):
                return
            try:
                _, pid = win32process.GetWindowThreadProcessId(candidate_hwnd)
                exe_name = psutil.Process(pid).name().lower()
            except Exception:
                return
            for app_id, exe_names in AUTOMATION_ALLOWLIST.items():
                if exe_name in exe_names:
                    candidates.append((app_id, candidate_hwnd))

        win32gui.EnumWindows(_enum_handler, None)

        if len(candidates) == 1:
            return candidates[0][0], candidates[0][1], None
        if len(candidates) > 1:
            names = ", ".join(sorted({c[0] for c in candidates}))
            return None, None, f"Multiple allowlisted windows are open ({names}) — focus one first."
        return None, None, "No allowlisted application window is open (notepad, calculator, vscode)."

    def get_controls(self, hwnd: int | None = None) -> list[UIElement]:
        """Get interactable UI elements for an allowlisted window."""
        if hwnd is None:
            _, hwnd, err = self.find_allowlisted_window()
            if not hwnd or err:
                return []

        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(handle=hwnd)
            window = app.window(handle=hwnd)
            descendants = window.descendants()

            elements: list[UIElement] = []
            for elem in descendants:
                try:
                    c_type = elem.element_info.control_type or ""
                    name = elem.element_info.name or ""
                    if not name and c_type not in ("Edit", "Document"):
                        continue
                    elements.append(UIElement(
                        name=name,
                        control_type=c_type,
                        automation_id=elem.element_info.automation_id or "",
                        bounding_rect=elem.rectangle(),
                        is_enabled=elem.is_enabled(),
                        _raw_element=elem,
                    ))
                except Exception:
                    continue
            return elements
        except Exception:
            return []

    def find_element_by_label(self, label: str, hwnd: int | None = None) -> UIElement | None:
        """Find a UI element matching visible label text."""
        controls = self.get_controls(hwnd)
        label_lower = label.strip().lower()

        # Exact match
        for elem in controls:
            if elem.name.strip().lower() == label_lower:
                return elem

        # Substring match
        for elem in controls:
            if label_lower in elem.name.strip().lower():
                return elem

        return None

    def click_element(self, element: UIElement) -> bool:
        """Click on a UI element."""
        if element._raw_element:
            try:
                element._raw_element.click_input()
                return True
            except Exception:
                try:
                    element._raw_element.click()
                    return True
                except Exception:
                    return False
        return False

    def type_into_element(self, element: UIElement, text: str) -> bool:
        """Type text into a UI element."""
        if element._raw_element:
            try:
                element._raw_element.set_focus()
                element._raw_element.type_keys(text, with_spaces=True)
                return True
            except Exception:
                return False
        return False
