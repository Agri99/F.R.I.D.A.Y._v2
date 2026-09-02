"""WindowManager result contracts and verified typing."""
from __future__ import annotations

import pytest


def _fake_wm(success: bool = True):
    class FakeWindowManager:
        def get_active_window(self):
            class Win:
                title = "Notepad - test.txt"
                process_name = "notepad.exe"
                rect = (0, 0, 100, 100)
                is_foreground = True
            return Win()

        def maximize(self):
            if success:
                return (True, "Maximized 'Notepad - test.txt'")
            return (False, "Maximize failed: access denied")

        def minimize(self):
            if success:
                return (True, "Minimized 'Notepad - test.txt'")
            return (False, "Minimize failed: access denied")

        def restore(self):
            if success:
                return (True, "Restored 'Notepad - test.txt'")
            return (False, "Restore failed: access denied")

        def close(self):
            if success:
                return (True, "Sent close to 'Notepad - test.txt'")
            return (False, "Close failed: access denied")

    return FakeWindowManager()


def test_window_actions_return_success():
    wm = _fake_wm(success=True)
    ok, msg = wm.maximize()
    assert ok and "Maximized" in msg


def test_window_actions_report_failure():
    wm = _fake_wm(success=False)
    ok, msg = wm.close()
    assert not ok and ("failed" in msg.lower() or "error" in msg.lower())


def test_control_window_tool_uses_verified_results(monkeypatch):
    import friday.tools.computer as computer

    monkeypatch.setattr(computer, "_window_mgr", _fake_wm(success=True))
    result = computer._control_window("maximize")
    assert result["status"] == "ok"
    assert result["action"] == "maximize"
    assert result["app_name"] == "test.txt"


def test_control_window_reports_failure(monkeypatch):
    import friday.tools.computer as computer

    monkeypatch.setattr(computer, "_window_mgr", _fake_wm(success=False))
    result = computer._control_window("close")
    assert result["status"] == "error"
