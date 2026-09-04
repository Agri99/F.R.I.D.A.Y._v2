"""
src/friday/computer/foreground_verifier.py

WHAT THIS IS FOR:
Foreground window verification (blueprint M3).

Confirms that the window FRIDAY interacted with is actually the foreground
window, not merely a visible window. This is the difference between "the
window exists" and "the user is looking at it".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from friday.computer.verification import VerificationResult


@dataclass
class ForegroundExpectation:
    """Expected foreground state."""
    window_title_substring: str | None = None
    process_name: str | None = None
    require_foreground: bool = True


class ForegroundVerifier:
    """Verify that a window is the foreground window.

    Returns success only when the foreground window's title/process matches
    the expectation. If no foreground window exists or the title doesn't
    match, returns failure so recovery is invoked instead of a false success.
    """

    def verify(self, expected: ForegroundExpectation) -> VerificationResult:
        try:
            import win32gui
        except Exception as e:
            return VerificationResult(False, f"win32gui not available: {e}")

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return VerificationResult(
                False,
                "No foreground window available to verify.",
            )

        title = win32gui.GetWindowText(hwnd) or ""
        process_name = self._process_name(hwnd)

        if expected.process_name is not None:
            if process_name and expected.process_name.lower() in process_name.lower():
                return VerificationResult(
                    True,
                    f"Foreground process is '{process_name}'.",
                )
            return VerificationResult(
                False,
                f"Foreground process is '{process_name}', "
                f"expected '{expected.process_name}'.",
            )

        if expected.window_title_substring is not None:
            if expected.window_title_substring.lower() in title.lower():
                return VerificationResult(
                    True,
                    f"Foreground window is '{title}'.",
                )
            return VerificationResult(
                False,
                f"Foreground window is '{title}', "
                f"expected '{expected.window_title_substring}'.",
            )

        # No specific expectation — the foreground window exists.
        return VerificationResult(
            True,
            f"Foreground window is '{title}' ({process_name}).",
        )

    @staticmethod
    def _process_name(hwnd: int) -> str:
        try:
            import win32process
            import psutil
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return psutil.Process(pid).name()
        except Exception:
            return ""


__all__ = ["ForegroundExpectation", "ForegroundVerifier"]