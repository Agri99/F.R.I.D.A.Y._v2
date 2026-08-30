"""
tests/unit/test_browser_form_security.py

WHAT THIS IS FOR:
Proves a real, confirmed security bug is fixed: BrowserNavigator.submit_form()
only checked policy approval when self.policy_engine was truthy. With no
policy_engine configured - which is the actual real-world default, since
tools/browser.py builds BrowserController() with no policy_engine argument
at all - the entire policy check was silently skipped and a form would
submit with ZERO approval, despite "submit" being a HIGH_IMPACT_ACTION.
navigate() already failed closed in this scenario; submit_form() didn't.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from friday.browser.navigation import BrowserNavigator


def test_submit_form_fails_closed_with_no_policy_engine():
    """The core bug: no policy_engine at all used to mean the check was
    skipped entirely and the form would actually submit. Now it must
    refuse instead."""
    nav = BrowserNavigator(policy_engine=None)
    result = nav.submit_form("https://example.com/submit", {"field": "value"})

    assert result.success is False
    assert result.requires_approval is True
    assert result.policy_approved is False


def test_submit_form_respects_policy_denial():
    class _DenyingPolicy:
        def evaluate(self, action, tier):
            class _Decision:
                class decision:
                    value = "DENY"
                reason = "test denial"
            return _Decision()

    nav = BrowserNavigator(policy_engine=_DenyingPolicy())
    result = nav.submit_form("https://example.com/submit", {"field": "value"})

    assert result.success is False
    assert result.policy_approved is False


def test_navigate_still_fails_closed_with_no_policy_engine_unaffected():
    """Regression guard: navigate() already had this protection - confirm
    the submit_form fix didn't accidentally change navigate()'s behavior."""
    nav = BrowserNavigator(policy_engine=None)
    result = nav.navigate("https://example.com/checkout")

    assert result.success is False
    assert result.requires_approval is True
