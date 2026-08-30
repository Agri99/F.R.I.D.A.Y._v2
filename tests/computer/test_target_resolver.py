"""
tests/computer/test_target_resolver.py

WHAT THIS IS FOR:
Unit tests for the TargetResolver with all priority tiers.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from friday.computer.target_resolver import TargetResolver, ResolutionMethod
from friday.computer.accessibility import UIElement


class MockUIElement(UIElement):
    def __init__(self, name, control_type, automation_id, bounding_rect=None, is_enabled=True):
        self.name = name
        self.control_type = control_type
        self.automation_id = automation_id
        self.bounding_rect = bounding_rect
        self.is_enabled = is_enabled


class MockAccessibilityProvider:
    def __init__(self, elements=None):
        self._elements = elements or []

    def find_allowlisted_window(self):
        return "test_app", 12345, None

    def get_all_elements(self, hwnd):
        return self._elements


class TestTargetResolver:
    @pytest.fixture
    def elements(self):
        return [
            MockUIElement("Save", "Button", "btn_save"),
            MockUIElement("Cancel", "Button", "btn_cancel"),
            MockUIElement("File name:", "Edit", "edit_filename"),
        ]

    @pytest.fixture
    def resolver(self, elements):
        provider = MockAccessibilityProvider(elements)
        return TargetResolver(accessibility=provider)

    def test_automation_id_resolution(self, resolver):
        result = resolver.resolve("btn_save")
        assert result is not None
        assert result.method == ResolutionMethod.AUTOMATION_ID
        assert result.confidence == 0.95

    def test_accessibility_label_resolution(self, resolver):
        result = resolver.resolve("Save")
        assert result is not None
        assert result.method == ResolutionMethod.ACCESSIBILITY_LABEL
        assert result.confidence == 0.90

    def test_role_and_label_resolution(self, resolver):
        result = resolver.resolve("save button")
        assert result is not None
        assert result.method == ResolutionMethod.ROLE_AND_LABEL

    def test_browser_locator_resolution(self, resolver):
        context = {"is_browser": True, "selector": "#submit-btn"}
        result = resolver.resolve("submit button", context)
        assert result is not None
        assert result.method == ResolutionMethod.BROWSER_LOCATOR
        assert result.confidence == 0.80

    def test_coordinate_fallback(self, resolver):
        result = resolver.resolve("100, 200")
        assert result is not None
        assert result.method == ResolutionMethod.COORDINATE_FALLBACK
        assert result.element == (100, 200)

    def test_default_resolution(self, resolver):
        """Unmatched description should fall back to accessibility/ visual query."""
        result = resolver.resolve("some unknown element", {})
        assert result is not None
        # Could be visual match fallback or default accessibility
        assert result.confidence > 0