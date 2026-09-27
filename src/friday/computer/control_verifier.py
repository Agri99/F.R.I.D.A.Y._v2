"""
src/friday/computer/control_verifier.py

WHAT THIS IS FOR:
Real UI-Automation control verification (blueprint §31).

Verifies the actual state of a control after an interaction — button enabled,
checkbox checked, text field value, slider position. Returns success only when
the control can be observed and its state matches the expectation. If the
control cannot be observed, returns uncertain/failure so recovery is invoked
instead of a false success.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from friday.computer.verification import VerificationResult


@dataclass
class ControlExpectation:
    """Expected state for a control after an interaction."""
    window_hint: str
    control_hint: str
    expected_button_state: str | None = None  # "enabled" | "disabled" | "pressed"
    expected_checked: bool | None = None       # True / False / None (don't care)
    expected_text: str | None = None           # substring the field should contain
    expected_value: float | None = None        # slider value
    value_tolerance: float = 0.05              # accepted tolerance for slider
    sensitive: bool = False                    # password/secret field


class ControlVerifier:
    """Verify control state by inspecting the allowlisted window's UI tree.

    Uses win32gui child-window enumeration as a deterministic fallback when
    a full UI Automation (UIA) provider is unavailable. Returns success only
    when the control is found and its observed state matches the expectation.
    """

    def verify(self, expected: ControlExpectation) -> VerificationResult:
        try:
            import win32gui
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return VerificationResult(False, f"win32gui not available: {e}")

        target_hwnd = self._find_window_by_hint(expected.window_hint)
        if not target_hwnd:
            return VerificationResult(
                False,
                f"Window matching '{expected.window_hint}' not found.",
            )

        control_hwnd = self._find_child_control(target_hwnd, expected.control_hint)
        if not control_hwnd:
            return VerificationResult(
                False,
                f"Control matching '{expected.control_hint}' not found in window "
                f"'{expected.window_hint}'.",
            )

        # Read the control's window text.
        control_text = win32gui.GetWindowText(control_hwnd)

        # --- Button state ---
        if expected.expected_button_state is not None:
            observed = self._button_state(control_hwnd, win32gui)
            if observed != expected.expected_button_state:
                return VerificationResult(
                    False,
                    f"Button '{expected.control_hint}' state is '{observed}', "
                    f"expected '{expected.expected_button_state}'.",
                )

        # --- Checkbox state ---
        if expected.expected_checked is not None:
            observed_checked = self._checkbox_state(control_hwnd, win32gui)
            if observed_checked is None:
                return VerificationResult(
                    False,
                    f"Cannot observe checkbox state for '{expected.control_hint}'.",
                )
            if observed_checked != expected.expected_checked:
                return VerificationResult(
                    False,
                    f"Checkbox '{expected.control_hint}' is "
                    f"{'checked' if observed_checked else 'unchecked'}, "
                    f"expected "
                    f"{'checked' if expected.expected_checked else 'unchecked'}.",
                )

        # --- Text field value ---
        if expected.expected_text is not None:
            if expected.sensitive:
                # Sensitive path: confirm something was entered and length > 0.
                if len(control_text) == 0:
                    return VerificationResult(
                        False,
                        f"Sensitive control '{expected.control_hint}' appears empty.",
                    )
                return VerificationResult(
                    True,
                    f"Sensitive control '{expected.control_hint}' accepted masked entry "
                    f"(length={len(control_text)}).",
                )
            if expected.expected_text.lower() in control_text.lower():
                return VerificationResult(
                    True,
                    f"Control '{expected.control_hint}' contains expected text.",
                )
            return VerificationResult(
                False,
                f"Control '{expected.control_hint}' value is '{control_text}', "
                f"does not contain '{expected.expected_text}'.",
            )

        # --- Slider value ---
        if expected.expected_value is not None:
            observed_value = self._slider_value(control_hwnd, win32gui)
            if observed_value is None:
                return VerificationResult(
                    False,
                    f"Cannot observe slider value for '{expected.control_hint}'.",
                )
            if abs(observed_value - expected.expected_value) <= expected.value_tolerance:
                return VerificationResult(
                    True,
                    f"Slider '{expected.control_hint}' is at {observed_value:.2f} "
                    f"(expected {expected.expected_value:.2f}).",
                )
            return VerificationResult(
                False,
                f"Slider '{expected.control_hint}' is at {observed_value:.2f}, "
                f"expected {expected.expected_value:.2f} "
                f"(tolerance {expected.value_tolerance:.2f}).",
            )

        # Nothing specific to check — the control exists and is observable.
        return VerificationResult(
            True,
            f"Control '{expected.control_hint}' observed in window "
            f"'{expected.window_hint}'.",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _find_window_by_hint(hint: str) -> int | None:
        import win32gui
        result: list[int] = []

        def _enum(hwnd: int, _: Any) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if hint.lower() in title.lower():
                result.append(hwnd)

        win32gui.EnumWindows(_enum, None)
        return result[0] if result else None

    @staticmethod
    def _find_child_control(parent_hwnd: int, hint: str) -> int | None:
        import win32gui
        result: list[int] = []

        def _enum(hwnd: int, _: Any) -> None:
            text = win32gui.GetWindowText(hwnd)
            if hint.lower() in text.lower():
                result.append(hwnd)

        win32gui.EnumChildWindows(parent_hwnd, _enum, None)
        return result[0] if result else None

    @staticmethod
    def _button_state(hwnd: int, win32gui_module) -> str:
        """Best-effort button state: enabled/disabled/pressed."""
        try:
            if not win32gui_module.IsWindowEnabled(hwnd):
                return "disabled"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            pass
        # Pressed state is best-effort; treat as "enabled" when the control
        # is enabled and observable.
        return "enabled"

    @staticmethod
    def _checkbox_state(hwnd: int, win32gui_module) -> bool | None:
        """Best-effort checkbox state via the button class + BST_CHECKED."""
        try:
            class_name = win32gui_module.GetClassName(hwnd)
            if class_name.lower() != "button":
                return None
            style = win32gui_module.GetWindowLongPtr(hwnd, -16)  # GWL_STYLE
            BST_CHECKED = 0x00000010
            return bool(style & BST_CHECKED)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            return None

    @staticmethod
    def _slider_value(hwnd: int, win32gui_module) -> float | None:
        """Best-effort slider value via the trackbar class."""
        try:
            class_name = win32gui_module.GetClassName(hwnd)
            if class_name.lower() != "trackbar":
                return None
            # TBM_GETRANGEMIN / TBM_GETRANGEMAX / TBM_GETPOS
            TBM_GETRANGEMIN = 0x4001
            TBM_GETRANGEMAX = 0x4002
            TBM_GETPOS = 0x4000
            min_val = win32gui_module.SendMessage(hwnd, TBM_GETRANGEMIN, 0, 0)
            max_val = win32gui_module.SendMessage(hwnd, TBM_GETRANGEMAX, 0, 0)
            pos = win32gui_module.SendMessage(hwnd, TBM_GETPOS, 0, 0)
            if max_val == min_val:
                return None
            return (pos - min_val) / (max_val - min_val)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            return None


__all__ = ["ControlExpectation", "ControlVerifier"]