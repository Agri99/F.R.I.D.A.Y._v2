"""
tests/computer/test_visual_target.py

WHAT THIS IS FOR:
Unit tests for visual fallback target resolution using OCR and VLM.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from friday.computer.target_resolver import TargetResolver, ResolutionMethod


class MockUIElement:
    def __init__(self, name, control_type, automation_id, bounding_rect=None, is_enabled=True):
        self.name = name
        self.control_type = control_type
        self.automation_id = automation_id
        self.bounding_rect = bounding_rect
        self.is_enabled = is_enabled


class MockAccessibilityProvider:
    def __init__(self):
        pass

    def find_allowlisted_window(self):
        return None, None, "No allowlisted window"

    def get_all_elements(self, hwnd):
        return []


class TestTargetResolverVisualFallback:
    @pytest.fixture
    def resolver(self):
        return TargetResolver(accessibility=MockAccessibilityProvider())

    def test_resolve_visual_match_with_bbox_in_context(self, resolver):
        """Test that visual match works when bbox is provided in context."""
        context = {
            "visual_bbox": (100, 100, 200, 200),
            "visual_confidence": 0.85,
        }
        result = resolver.resolve("Save button", context)
        assert result is not None
        assert result.method == ResolutionMethod.VISUAL_MATCH
        assert result.confidence == 0.85
        assert result.bounding_box == (100, 100, 200, 200)

    @patch("friday.computer.screen.capture_screen")
    @patch("friday.computer.screen.ocr", return_value="Click the Save button to continue")
    @patch("friday.computer.screen.describe_screen", return_value={"status": "error"})
    def test_ocr_match_confidence(self, mock_describe, mock_ocr, mock_capture, resolver):
        """OCR match should return reasonable confidence."""
        mock_capture.return_value = MagicMock()
        result = resolver.resolve("Save button", {})
        assert result is not None
        assert result.method == ResolutionMethod.VISUAL_MATCH
        assert result.confidence >= 0.7

    @patch("friday.computer.screen.capture_screen")
    @patch("friday.computer.screen.ocr", return_value="Unrelated text")
    @patch("friday.computer.screen.describe_screen",
           return_value={"status": "ok", "description": "Save button found at center"})
    def test_vlm_fallback_confidence(self, mock_describe, mock_ocr, mock_capture, resolver):
        """VLM fallback should return moderate confidence."""
        mock_capture.return_value = MagicMock()
        result = resolver.resolve("Save button", {})
        assert result is not None
        assert result.method == ResolutionMethod.VISUAL_MATCH
        # VLM fallback has lower confidence
        assert result.confidence >= 0.5


class TestTargetResolverIntegration:
    """Integration tests combining all resolution tiers."""

    @pytest.fixture
    def resolver(self):
        return TargetResolver(accessibility=MockAccessibilityProvider())

    def test_coordinate_fallback_last_resort(self, resolver):
        """Verify coordinate parsing works as last resort."""
        result = resolver.resolve("at (100, 200)", {})
        assert result is not None
        assert result.method == ResolutionMethod.COORDINATE_FALLBACK
        assert result.element == (100, 200)