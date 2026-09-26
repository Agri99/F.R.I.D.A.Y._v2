from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from friday.tools.computer import (
    _mouse_move,
    _mouse_click,
    _mouse_scroll,
    _mouse_drag,
    register_all_tools as register_computer_tools,
)
from friday.tools.applications import (
    _open_app,
    _list_installed_apps,
    _scan_installed_apps,
    _resolve_app,
    register_all_tools as register_app_tools,
)
from friday.tools.registry import ToolRegistry
from friday.security.policy import PolicyEngine, RiskTier, PolicyDecision
from friday.config import Settings


class TestMouseControls(unittest.TestCase):
    @patch("friday.computer.mouse.move")
    def test_mouse_move(self, mock_move):
        res = _mouse_move(100, 200)
        self.assertEqual(res["status"], "ok")
        mock_move.assert_called_once_with(100, 200)

    @patch("friday.computer.mouse.click")
    @patch("friday.computer.mouse.right_click")
    @patch("friday.computer.mouse.double_click")
    def test_mouse_click_variants(self, mock_dbl, mock_right, mock_left):
        # Default left click
        res_left = _mouse_click(button="left", x=50, y=50)
        self.assertEqual(res_left["status"], "ok")
        mock_left.assert_called_once_with(50, 50)

        # Right click
        res_right = _mouse_click(button="right", x=60, y=70)
        self.assertEqual(res_right["status"], "ok")
        mock_right.assert_called_once_with(60, 70)

        # Double click
        res_dbl = _mouse_click(button="double", x=80, y=90)
        self.assertEqual(res_dbl["status"], "ok")
        mock_dbl.assert_called_once_with(80, 90)

    @patch("friday.computer.mouse.scroll")
    def test_mouse_scroll_directions(self, mock_scroll):
        # Scroll down
        res_down = _mouse_scroll(direction="down", amount=5)
        self.assertEqual(res_down["status"], "ok")
        self.assertEqual(res_down["clicks"], -5)
        mock_scroll.assert_called_with(-5)

        # Scroll up
        res_up = _mouse_scroll(direction="up", amount=3)
        self.assertEqual(res_up["status"], "ok")
        self.assertEqual(res_up["clicks"], 3)
        mock_scroll.assert_called_with(3)

        # Direct clicks parameter
        res_direct = _mouse_scroll(clicks=10)
        self.assertEqual(res_direct["status"], "ok")
        self.assertEqual(res_direct["clicks"], 10)
        mock_scroll.assert_called_with(10)

    @patch("friday.computer.mouse.drag")
    def test_mouse_drag(self, mock_drag):
        res = _mouse_drag(10, 20, 100, 200)
        self.assertEqual(res["status"], "ok")
        mock_drag.assert_called_once_with(10, 20, 100, 200)

    def test_mouse_tools_registered(self):
        reg = ToolRegistry()
        register_computer_tools(reg)
        self.assertIsNotNone(reg.get("computer.mouse_move"))
        self.assertIsNotNone(reg.get("computer.mouse_click"))
        self.assertIsNotNone(reg.get("computer.mouse_scroll"))
        self.assertIsNotNone(reg.get("computer.mouse_drag"))


class TestApplicationToolsAndTiers(unittest.TestCase):
    def test_whitelist_app_is_green_tier(self):
        app_name, path, tier = _resolve_app("notepad")
        self.assertEqual(tier, "GREEN")
        self.assertEqual(app_name, "notepad")

        app_name, path, tier = _resolve_app("calculator")
        self.assertEqual(tier, "GREEN")

    @patch("friday.tools.applications.os.startfile", create=True)
    def test_open_whitelist_app_direct(self, mock_startfile):
        # Whitelisted app opens directly without requiring confirmation
        res = _open_app("notepad", force_new=True)
        self.assertEqual(res["status"], "opened")
        self.assertEqual(res["tier"], "GREEN")

    @patch("friday.tools.applications._scan_installed_apps")
    def test_arbitrary_installed_app_requires_orange_confirmation(self, mock_scan):
        mock_scan.return_value = {
            "spotify": r"C:\Users\test\AppData\Roaming\Spotify\Spotify.exe",
            "steam": r"C:\Program Files (x86)\Steam\steam.exe",
        }

        # Turn 1: Without confirmation -> requires confirmation (ORANGE tier)
        res = _open_app("spotify", confirmed=False)
        self.assertEqual(res["status"], "requires_confirmation")
        self.assertEqual(res["tier"], "ORANGE")
        self.assertIn("requiring confirmation", res["message"])

        # Turn 2: With confirmation -> opens app
        with patch("friday.tools.applications.os.startfile", create=True) as mock_startfile:
            res_confirmed = _open_app("spotify", confirmed=True, force_new=True)
            self.assertEqual(res_confirmed["status"], "opened")
            self.assertEqual(res_confirmed["tier"], "ORANGE")
            mock_startfile.assert_called_once_with(r"C:\Users\test\AppData\Roaming\Spotify\Spotify.exe")

    def test_unknown_app_error(self):
        res = _open_app("totally_nonexistent_application_xyz123")
        self.assertEqual(res["status"], "error")
        self.assertIn("No application found", res["message"])

    def test_list_installed_apps(self):
        res = _list_installed_apps()
        self.assertEqual(res["status"], "ok")
        self.assertIsInstance(res["apps"], list)

    def test_policy_engine_evaluates_mouse_tools(self):
        settings = Settings()
        policy = PolicyEngine(settings)
        result_move = policy.evaluate("computer.mouse_move")
        self.assertEqual(result_move.tier, RiskTier.YELLOW)
        self.assertEqual(result_move.decision, PolicyDecision.REQUIRE_CONFIRMATION)

        result_click = policy.evaluate("computer.mouse_click")
        self.assertEqual(result_click.tier, RiskTier.YELLOW)
        self.assertEqual(result_click.decision, PolicyDecision.REQUIRE_CONFIRMATION)

        result_scroll = policy.evaluate("computer.mouse_scroll")
        self.assertEqual(result_scroll.tier, RiskTier.YELLOW)
        self.assertEqual(result_scroll.decision, PolicyDecision.REQUIRE_CONFIRMATION)


if __name__ == "__main__":
    unittest.main()
