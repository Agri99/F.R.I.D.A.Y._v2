"""
tests/computer/test_verification.py

WHAT THIS IS FOR:
Prove the M1 verification invariants — that no verifier returns success
when there is no real evidence. These tests are platform-portable: they patch
out win32gui / Playwright so they execute on any OS, but they exercise the
real control flow that Windows CI will also cover.

Blueprint references: §3.1 Remove false verification, §70 Security invariants,
M1 acceptance criteria.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from friday.computer.verification import (
    ApplicationStateExpected,
    ApplicationStateVerifier,
    ControlVerifier,
    FileContentVerifier,
    ProcessVerifier,
    TextEntryExpected,
    TextEntryVerifier,
    URLVerifier,
    VerificationResult,
    WindowVerifier,
)


# ---------------------------------------------------------------------------
# Helpers: fake a minimal win32gui surface so these tests run on Linux/macOS.
# ---------------------------------------------------------------------------
class _FakeWin32Gui:
    """Minimal stand-in for win32gui used by the verifiers, fully controllable."""

    def __init__(self, windows=None, foreground_hwnd=0):
        # windows: dict[int, dict(title=..., visible=True, children=...)]
        self._windows = windows or {}
        self._foreground = foreground_hwnd
        self.EnumWindows_calls = []
        self.EnumChildWindows_calls = []

    # The verifiers call FindWindow(None, title). Implement it as a substring
    # scan over the registered window titles (matches how EnumWindows does it
    # in the verifier itself).
    def FindWindow(self, _class, title):
        if not title:
            return 0
        for hwnd, info in self._windows.items():
            win_title = info.get("title", "")
            if title.lower() in win_title.lower():
                return hwnd
        return 0

    def EnumWindows(self, callback, _):
        self.EnumWindows_calls.append(callback)
        for hwnd, info in self._windows.items():
            callback(hwnd, _)

    def EnumChildWindows(self, parent, callback, _):
        self.EnumChildWindows_calls.append((parent, callback))
        for hwnd, info in self._windows.get(parent, {}).get("children", {}).items():
            callback(hwnd, _)

    def GetWindowText(self, hwnd):
        # Look up the window directly OR as a child of some parent.
        if hwnd in self._windows:
            return self._windows[hwnd].get("title", "")
        for parent_info in self._windows.values():
            children = parent_info.get("children", {})
            if hwnd in children:
                return children[hwnd].get("title", "")
        return ""

    def GetForegroundWindow(self):
        return self._foreground

    def IsWindowVisible(self, hwnd):
        if hwnd in self._windows:
            return self._windows[hwnd].get("visible", False)
        for parent_info in self._windows.values():
            children = parent_info.get("children", {})
            if hwnd in children:
                return children[hwnd].get("visible", True)
        return False

    def GetWindowThreadProcessId(self, hwnd):
        return (0, 0)


@pytest.fixture
def fake_no_gw_gui(monkeypatch):
    """win32gui that finds nothing -> every 'no evidence' path."""
    fake = _FakeWin32Gui(windows={})
    import sys
    monkeypatch.setitem(sys.modules, "win32gui", fake)
    return fake


# ---------------------------------------------------------------------------
# WindowVerifier: must not return True when the window is missing.
# ---------------------------------------------------------------------------
class TestWindowVerifier:
    def test_no_window_found_returns_false(self, fake_no_gw_gui):
        """The single most important M1 rule: no evidence, not success."""
        verifier = WindowVerifier()
        result = verifier.verify("definitely_does_not_exist_xyz")
        assert result.success is False
        assert "not found" in result.message.lower()

    def test_found_window_is_visible(self, monkeypatch):
        windows = {
            1001: {"title": "Untitled - Notepad", "visible": True, "children": {}},
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=1001)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        result = WindowVerifier().verify("Untitled - Notepad")
        assert result.success is True

    def test_found_window_not_visible_returns_false(self, monkeypatch):
        windows = {
            1002: {"title": "Hidden Window", "visible": False, "children": {}},
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=1002)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        result = WindowVerifier().verify("Hidden Window")
        assert result.success is False
        assert "not visible" in result.message.lower()


# ---------------------------------------------------------------------------
# ControlVerifier: must not succeed without real UI evidence.
# ---------------------------------------------------------------------------
class TestControlVerifier:
    def test_no_window_returns_false(self, fake_no_gw_gui):
        verifier = ControlVerifier()
        result = verifier.verify(("no_such_window", "no_such_control"))
        assert result.success is False

    def test_window_found_control_missing_returns_false(self, monkeypatch):
        windows = {
            2001: {"title": "App Window", "visible": True, "children": {}},
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=2001)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        result = ControlVerifier().verify(("App Window", "missing_button"))
        assert result.success is False
        assert "not found" in result.message.lower()

    def test_control_found_text_matches_returns_true(self, monkeypatch):
        windows = {
            2001: {
                "title": "App Window", "visible": True,
                "children": {
                    2002: {"title": "Save Changes", "visible": True},
                },
            },
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=2001)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        result = ControlVerifier().verify(("App Window", "Save"))
        assert result.success is True


# ---------------------------------------------------------------------------
# URLVerifier: must not succeed without a real browser state source.
# ---------------------------------------------------------------------------
class TestURLVerifier:
    def test_no_browser_source_returns_false(self):
        verifier = URLVerifier(browser=None, url_provider=None)
        result = verifier.verify("https://example.com")
        assert result.success is False
        assert "no browser state" in result.message.lower()

    def test_browser_url_match_returns_true(self):
        browser = SimpleNamespace(current_url="https://example.com/dashboard?q=1")
        result = URLVerifier(browser=browser).verify("example.com")
        assert result.success is True

    def test_browser_url_mismatch_returns_false(self):
        browser = SimpleNamespace(current_url="https://attacker.com")
        result = URLVerifier(browser=browser).verify("https://example.com")
        assert result.success is False

    def test_browser_url_none_returns_false(self):
        """Browser object exists but never navigated."""
        browser = SimpleNamespace(current_url=None)
        result = URLVerifier(browser=browser).verify("https://example.com")
        assert result.success is False
        assert "not navigated" in result.message.lower()

    def test_url_provider_callable(self):
        result = URLVerifier(url_provider=lambda: "https://safe.example/page").verify("safe.example")
        assert result.success is True

    def test_url_provider_returns_none(self):
        result = URLVerifier(url_provider=lambda: None).verify("https://example.com")
        assert result.success is False


# ---------------------------------------------------------------------------
# TextEntryVerifier
# ---------------------------------------------------------------------------
class TestTextEntryVerifier:
    def test_missing_window_returns_false(self, fake_no_gw_gui):
        expected = TextEntryExpected("no_win", "no_ctrl", "hello")
        result = TextEntryVerifier(expected).verify(post_value="hello")
        assert result.success is False

    def test_successful_entry(self, monkeypatch):
        windows = {
            3001: {
                "title": "Untitled - Notepad", "visible": True,
                "children": {3002: {"title": "Hello world"}},
            },
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=3001)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        expected = TextEntryExpected("Untitled - Notepad", "Hello", "Hello", sensitive=False)
        result = TextEntryVerifier(expected).verify(post_value="Hello world")
        assert result.success is True

    def test_foreground_mismatch_returns_false(self, monkeypatch):
        windows = {
            3001: {
                "title": "Untitled - Notepad", "visible": True,
                "children": {3002: {"title": "Hello"}},
            },
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=9999)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        expected = TextEntryExpected("Untitled - Notepad", "Hello", "Hello")
        result = TextEntryVerifier(expected).verify(post_value="Hello")
        assert result.success is False
        assert "foreground" in result.message.lower()

    def test_sensitive_field_never_logs_plaintext(self, monkeypatch):
        windows = {
            4001: {
                "title": "Login", "visible": True,
                "children": {4002: {"title": "Password"}},
            },
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=4001)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        expected = TextEntryExpected("Login", "password", "supersecret", sensitive=True)
        result = TextEntryVerifier(expected).verify(post_value="********")
        assert result.success is True
        assert "supersecret" not in result.message.lower()
        assert "supersecret" not in repr(result)

    def test_sensitive_empty_returns_false(self, monkeypatch):
        windows = {
            4001: {"title": "Login", "visible": True, "children": {}},
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=4001)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        expected = TextEntryExpected("Login", "password", "supersecret", sensitive=True)
        result = TextEntryVerifier(expected).verify(post_value="")
        assert result.success is False


# ---------------------------------------------------------------------------
# ApplicationStateVerifier: process alone must NOT be enough.
# ---------------------------------------------------------------------------
class TestApplicationStateVerifier:
    def test_process_not_running_returns_false(self, fake_no_gw_gui):
        expected = ApplicationStateExpected(
            process_name="nonexistent_app.exe",
            window_title_substring="Some Window",
        )
        result = ApplicationStateVerifier().verify(expected)
        assert result.success is False

    def test_process_running_no_window_with_title_returns_false(self, monkeypatch):
        """The M1 core: process is running but no matching visible window -> fail."""
        windows = {
            5001: {"title": "Some other app", "visible": True, "children": {}},
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=5001)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        with patch("friday.computer.verification.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = iter([
                MagicMock(info={"name": "target.exe"})
            ])

            expected = ApplicationStateExpected(
                process_name="target.exe",
                window_title_substring="Window we expect",
            )
            result = ApplicationStateVerifier().verify(expected)
            assert result.success is False
            assert "window" in result.message.lower()

    def test_process_and_window_match_returns_true(self, monkeypatch):
        windows = {
            5001: {"title": "Target app — document.txt", "visible": True, "children": {}},
        }
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=5001)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)

        with patch("friday.computer.verification.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = iter([
                MagicMock(info={"name": "target.exe"})
            ])

            expected = ApplicationStateExpected(
                process_name="target.exe",
                window_title_substring="Target app",
            )
            result = ApplicationStateVerifier().verify(expected)
            assert result.success is True


# ---------------------------------------------------------------------------
# FileContentVerifier: negative cases (file missing / content absent).
# ---------------------------------------------------------------------------
class TestFileContentVerifier:
    def test_missing_file_returns_false(self):
        result = FileContentVerifier().verify(("/no/such/file.txt", "content"))
        assert result.success is False

    def test_content_absent_returns_false(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("nothing here")
        result = FileContentVerifier().verify((str(f), "expected"))
        assert result.success is False


# ---------------------------------------------------------------------------
# Security-invariant smoke: a verifier returning True must correlate with
# real evidence in the mock state.
# ---------------------------------------------------------------------------
class TestSecurityInvariants:
    def test_verifier_success_implies_evidence(self, monkeypatch):
        """If a WindowVerifier returns True, it must have found a visible window."""
        # No windows exist in this fake — success is impossible.
        windows = {}
        fake = _FakeWin32Gui(windows=windows, foreground_hwnd=0)
        import sys
        monkeypatch.setitem(sys.modules, "win32gui", fake)
        result = WindowVerifier().verify("anything")
        assert not result.success

    def test_url_verifier_success_implies_state(self):
        browser = SimpleNamespace(current_url="https://real.example.com/path")
        result = URLVerifier(browser=browser).verify("real.example")
        assert result.success
