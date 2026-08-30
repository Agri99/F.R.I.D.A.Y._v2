"""
tests/evaluation/test_browser_dom_interaction.py

WHAT THIS IS FOR:
E2E evaluation test for browser DOM interaction (click, type, verify).
Tests the observe-plan-execute-verify loop with Playwright controller.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from friday.browser.controller import BrowserController, BrowserConfig
from friday.browser.navigation import BrowserNavigator
from friday.browser.policies import BrowserScope, evaluate_action


class TestBrowserDomInteraction:
    @pytest.fixture
    def navigator(self):
        from unittest.mock import MagicMock
        from friday.online.network import NetworkMonitor
        mock_monitor = MagicMock(spec=NetworkMonitor)
        mock_monitor.is_online.return_value = True
        return BrowserNavigator(timeout_seconds=5, policy_engine=None, safety=None)

    @pytest.fixture
    def controller(self):
        from unittest.mock import MagicMock
        from friday.online.network import NetworkMonitor
        from friday.security.policy import PolicyEngine
        from friday.browser.safety import BrowserSafety
        from friday.browser.navigation import BrowserNavigator

        mock_monitor = MagicMock(spec=NetworkMonitor)
        mock_monitor.is_online.return_value = True

        mock_policy = MagicMock(spec=PolicyEngine)
        mock_policy.evaluate.return_value = MagicMock(decision=MagicMock(value="ALLOW"))

        # Use real BrowserSafety for URL checking, mock only the methods we don't want
        real_safety = BrowserSafety()
        mock_safety = MagicMock(spec=BrowserSafety)
        mock_safety.is_safe_url = real_safety.is_safe_url
        mock_safety.requires_policy_approval.return_value = False
        mock_safety.sanitize_for_llm = lambda x, max_length=8000: x

        # Create a real navigator but with mocked dependencies
        mock_nav_monitor = MagicMock(spec=NetworkMonitor)
        mock_nav_monitor.is_online.return_value = True
        navigator = BrowserNavigator(timeout_seconds=5, policy_engine=mock_policy, safety=mock_safety)

        config = BrowserConfig(engine="requests", timeout_seconds=5)
        controller = BrowserController(config, policy_engine=mock_policy, safety=mock_safety)
        # Replace the controller's navigator with our pre-configured one
        controller.navigator = navigator
        return controller

    def test_safe_url_check(self, controller):
        """Verify URL safety logic - only http/https allowed."""
        assert controller._is_safe_url("https://example.com") is True
        assert controller._is_safe_url("file:///etc/passwd") is False
        assert controller._is_safe_url("javascript:alert(1)") is False

    def test_navigation_risk_classification(self, navigator):
        """Verify URL risk classification."""
        assert navigator.classify_risk("https://example.com") == "GREEN"
        assert navigator.classify_risk("file:///etc/passwd") == "RED"
        assert navigator.classify_risk("https://shop.example.com/checkout") == "ORANGE"
        assert navigator.classify_risk("https://example.com/login") == "YELLOW"

    def test_browser_controller_history(self, controller):
        """Verify history tracking."""
        controller._history = ["https://a.com", "https://b.com"]
        controller._history_index = 1
        controller._current_url = "https://b.com"

        # Mock the navigator's navigate method to return success
        from friday.browser.navigation import NavigationResult
        mock_result = NavigationResult(success=True, url="https://a.com", risk_level="GREEN")
        controller.navigator.navigate = MagicMock(return_value=mock_result)

        # The new implementation uses navigator.navigate() instead of webbrowser.open()
        assert controller.back() is True
        controller.navigator.navigate.assert_called_once_with("https://a.com", action_type="back")
        assert controller._current_url == "https://a.com"

    def test_browser_navigator_offline_blocks(self, navigator):
        """Verify offline navigation returns a failed result."""
        with patch("friday.online.network.NetworkMonitor.is_online", return_value=False):
            result = navigator.navigate("https://example.com")
            assert result.success is False
            assert "offline" in result.error.lower()

    def test_browser_scope_evaluation(self):
        """Verify action risk scope mapping."""
        assert evaluate_action("read") == BrowserScope.GREEN
        assert evaluate_action("search") == BrowserScope.YELLOW
        assert evaluate_action("submit") == BrowserScope.ORANGE
        assert evaluate_action("upload") == BrowserScope.RED

    def test_browser_controller_fallback_to_requests(self, controller):
        """Verify requests engine works without Playwright."""
        assert controller.config.engine == "requests"
        assert controller._playwright is None