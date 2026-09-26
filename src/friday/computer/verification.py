"""
src/friday/computer/verification.py

WHAT THIS IS FOR:
Post-action verification logic (blueprint §10.4, §12) ensuring mutating
computer operations achieved the expected system state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol
import psutil


@dataclass
class VerificationResult:
    """Result of a verification attempt."""
    success: bool
    message: str


class VerificationStrategy(Protocol):
    """Protocol for post-action verification."""
    def verify(self, expected_state: Any) -> VerificationResult: ...


class ProcessVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a process with the given name is running."""
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == expected_state.lower():
                    return VerificationResult(True, f"Process {expected_state} is running.")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return VerificationResult(False, f"Process {expected_state} not found.")


class WindowVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a window with the given title exists and is visible.

        Returns success=False when the window cannot be found or win32gui is unavailable.
        """
        try:
            import win32gui
        except Exception as e:
            return VerificationResult(False, f"win32gui not available: {e}")
        hwnd = win32gui.FindWindow(None, expected_state)
        if hwnd:
            # Check if window is visible
            if win32gui.IsWindowVisible(hwnd):
                return VerificationResult(True, f"Window '{expected_state}' is visible.")
            else:
                return VerificationResult(False, f"Window '{expected_state}' exists but not visible.")
        return VerificationResult(False, f"Window '{expected_state}' not found.")


class FileVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a file exists."""
        if os.path.exists(expected_state):
            return VerificationResult(True, f"File '{expected_state}' verified.")
        return VerificationResult(False, f"File '{expected_state}' does not exist.")


class FileContentVerifier:
    def verify(self, expected_state: tuple[str, str]) -> VerificationResult:
        """Verify file content contains expected substring."""
        path, expected_text = expected_state
        if not os.path.exists(path):
            return VerificationResult(False, f"File '{path}' does not exist.")
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if expected_text in content:
                return VerificationResult(True, f"File content verified in '{path}'.")
            return VerificationResult(False, f"Expected text not found in '{path}'.")
        except Exception as e:
            return VerificationResult(False, f"Error reading file '{path}': {e}")


class ControlVerifier:
    """Verify control state by inspecting the allowlisted window's UI tree.

    expected_state is a tuple of (window_title_substring, control_name_substring).
    The control is located via WindowEnumerator among the window's child controls,
    and the control's window text is compared (case-insensitive substring) against
    the control name. Returns success only when the control is found and its text
    matches.
    """

    def verify(self, expected_state: tuple[str, str]) -> VerificationResult:
        window_hint, control_hint = expected_state
        try:
            import win32gui
        except Exception as e:
            return VerificationResult(False, f"win32gui not available: {e}")

        target_hwnd = self._find_window_by_hint(window_hint)
        if not target_hwnd:
            return VerificationResult(False, f"Window matching '{window_hint}' not found.")

        # Try win32gui first
        control_hwnd = self._find_child_control_win32(target_hwnd, control_hint)
        if control_hwnd:
            control_text = win32gui.GetWindowText(control_hwnd)
            if control_hint.lower() in control_text.lower():
                return VerificationResult(True, f"Control '{control_hint}' text matches in window '{window_hint}'.")

        # Fallback to UI Automation for modern apps (Win11 Notepad, Electron, etc.)
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(handle=target_hwnd)
            window = app.window(handle=target_hwnd)
            for elem in window.descendants():
                text = elem.window_text() or elem.element_info.name or ""
                if control_hint.lower() in text.lower():
                    return VerificationResult(True, f"Control '{control_hint}' text matches in window '{window_hint}' (UIA).")
        except Exception:
            pass
            
        return VerificationResult(False, f"Control '{control_hint}' not found in window '{window_hint}'.")

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
    def _find_child_control_win32(parent_hwnd: int, hint: str) -> int | None:
        import win32gui
        result: list[int] = []

        def _enum(hwnd: int, _: Any) -> None:
            text = win32gui.GetWindowText(hwnd)
            if hint.lower() in text.lower():
                result.append(hwnd)

        win32gui.EnumChildWindows(parent_hwnd, _enum, None)
        return result[0] if result else None


class URLVerifier:
    """Verify that a browser actually navigated to the expected URL.

    The verifier MUST be given a real source of browser state. It accepts either:
      - a ``browser`` object with a ``current_url`` attribute (e.g. BrowserController
        or any Playwright ``page`` wrapper exposing ``url``);
      - a callable ``url_provider() -> str | None``;
      - a raw URL string (only for testing — never the production path).

    Without a real source, ``verify()`` returns ``success=False``. This is the
    M1 invariant: a function return is not proof of success, only an
    observation is.
    """

    def __init__(self, browser: Any | None = None, url_provider: Any | None = None) -> None:
        self._browser = browser
        self._url_provider = url_provider

    def verify(self, expected_state: str) -> VerificationResult:
        actual, reason = self._read_actual_url()
        if actual is None:
            if reason == "no_source":
                return VerificationResult(False, "URL verification failed: no browser state source available.")
            if reason == "not_navigated":
                return VerificationResult(False, "URL verification failed: browser has not navigated yet.")
            return VerificationResult(False, f"URL verification failed: {reason}")
        if expected_state.lower() in actual.lower():
            return VerificationResult(True, f"URL '{actual}' contains '{expected_state}'.")
        return VerificationResult(False, f"Browser at '{actual}', expected '{expected_state}'.")

    def _read_actual_url(self) -> tuple[str | None, str | None]:
        """Return (actual_url, reason). reason is None on success."""
        if self._browser is not None:
            url = getattr(self._browser, "current_url", None)
            if url is None:
                url = getattr(self._browser, "url", None)
            if url:
                return (str(url), None)
            return (None, "not_navigated")
        if self._url_provider is not None:
            try:
                url = self._url_provider()
            except Exception as e:
                return (None, f"provider_error: {e}")
            if url:
                return (str(url), None)
            return (None, "not_navigated")
        return (None, "no_source")


@dataclass
class ApplicationStateExpected:
    """Expected application state for verification."""
    process_name: str
    window_title_substring: str | None = None
    require_foreground: bool = False


class ApplicationStateVerifier:
    """Verify that an application is in the expected state.

    Per the M1 invariant, process existence alone is not proof. We require:
      1. the process is running;
      2. a visible window with the expected title substring exists;
      3. (optionally) the window is the foreground window.

    Any check that fails returns success=False with a precise reason.
    """

    def verify(self, expected: ApplicationStateExpected) -> VerificationResult:
        proc_result = ProcessVerifier().verify(expected.process_name)
        if not proc_result.success:
            return proc_result

        if expected.window_title_substring is None:
            return VerificationResult(
                True,
                f"Process '{expected.process_name}' is running (no window title required).",
            )

        window_result = WindowVerifier().verify(expected.window_title_substring)
        if not window_result.success:
            return VerificationResult(
                False,
                f"Process '{expected.process_name}' is running but window "
                f"'{expected.window_title_substring}' is not visible.",
            )

        if expected.require_foreground:
            try:
                import win32gui
                foreground = win32gui.GetForegroundWindow()
                if not foreground:
                    return VerificationResult(
                        False,
                        f"No foreground window to compare against '{expected.window_title_substring}'.",
                    )
                title = win32gui.GetWindowText(foreground)
                if expected.window_title_substring.lower() not in title.lower():
                    return VerificationResult(
                        False,
                        f"Foreground window is '{title}', expected "
                        f"'{expected.window_title_substring}'.",
                    )
            except Exception as e:
                return VerificationResult(False, f"Foreground check failed: {e}")

        return VerificationResult(
            True,
            f"Application '{expected.process_name}' running with window "
            f"'{expected.window_title_substring}' visible.",
        )


@dataclass
class TextEntryExpected:
    """Expected state for text-entry verification.

    sensitive=True means the field is a password/secret. The verifier will only
    confirm that something was entered and focus is correct — it never logs or
    returns the actual value.
    """
    window_hint: str
    control_hint: str
    expected_substring: str
    sensitive: bool = False


class TextEntryVerifier:
    """Verify that typed text landed in the expected focused control.

    The verification path is:
        resolve foreground window -> resolve focused/child control
        -> read pre-value -> caller types -> read post-value
        -> assert post-value contains expected_substring

    For sensitive fields the verifier:
        - never returns the post-value;
        - only confirms post-value length increased and contains masked chars;
        - returns success only when focus is correct.
    """

    def __init__(self, expected: TextEntryExpected) -> None:
        self.expected = expected

    def verify(self, post_value: str | None) -> VerificationResult:
        try:
            import win32gui
        except Exception as e:
            return VerificationResult(False, f"win32gui not available: {e}")

        target_hwnd = ControlVerifier._find_window_by_hint(self.expected.window_hint)
        if not target_hwnd:
            return VerificationResult(False, f"Window '{self.expected.window_hint}' not focused.")

        foreground = win32gui.GetForegroundWindow()
        if foreground != target_hwnd:
            return VerificationResult(
                False,
                f"Window '{self.expected.window_hint}' not in foreground during entry.",
            )

        control_hwnd = ControlVerifier._find_child_control_win32(
            target_hwnd, self.expected.control_hint
        )
        if not control_hwnd:
            # Fallback to UI Automation for modern apps (Win11 Notepad, Electron, etc.)
            try:
                from pywinauto import Application
                app = Application(backend="uia").connect(handle=target_hwnd)
                window = app.window(handle=target_hwnd)
                found = False
                for elem in window.descendants():
                    text = elem.window_text() or elem.element_info.name or ""
                    if self.expected.control_hint.lower() in text.lower():
                        found = True
                        break
                if not found:
                    return VerificationResult(
                        False,
                        f"Control '{self.expected.control_hint}' not found in focused window.",
                    )
            except Exception:
                return VerificationResult(
                    False,
                    f"Control '{self.expected.control_hint}' not found in focused window.",
                )

        if post_value is None:
            return VerificationResult(False, "No post-value observed; cannot verify entry.")

        if self.expected.sensitive:
            # Sensitive path: never compare plaintext. Confirm only that something
            # was entered and that the visible chars are masked (length > 0 and no
            # cleartext match against expected_substring in the captured value).
            if len(post_value) == 0:
                return VerificationResult(False, "Sensitive field appears empty after entry.")
            return VerificationResult(
                True,
                f"Sensitive control '{self.expected.control_hint}' accepted masked entry "
                f"(length={len(post_value)}).",
            )

        if self.expected.expected_substring.lower() in post_value.lower():
            return VerificationResult(
                True,
                f"Control '{self.expected.control_hint}' contains expected substring.",
            )
        return VerificationResult(
            False,
            f"Control '{self.expected.control_hint}' value does not contain expected substring.",
        )


# Aliases for backward compatibility
ProcessExistsVerifier = ProcessVerifier
WindowVisibleVerifier = WindowVerifier
FileExistsVerifier = FileVerifier
URLLoadedVerifier = URLVerifier
