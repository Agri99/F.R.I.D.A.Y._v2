"""
tests/evaluation/test_visual_fallback.py

WHAT THIS IS FOR:
E2E evaluation test for visual fallback target resolution.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from friday.computer.target_resolver import TargetResolver, ResolutionMethod


class TestVisualFallbackEvaluation:
    @pytest.fixture
    def mock_accessibility(self):
        mock = MagicMock()
        mock.find_allowlisted_window.return_value = (None, None, "No allowlisted window")
        mock.get_all_elements.return_value = []
        return mock

    @pytest.fixture
    def resolver(self, mock_accessibility):
        return TargetResolver(accessibility=mock_accessibility)

    def test_visual_match_returns_resolved_target(self, resolver):
        """Visual fallback should produce a ResolvedTarget with confidence >= 0.7."""
        context = {"visual_bbox": (100, 100, 200, 200), "visual_confidence": 0.8}
        result = resolver.resolve("Save button", context)
        assert result is not None
        assert result.method == ResolutionMethod.VISUAL_MATCH
        assert result.confidence >= 0.7
        assert result.bounding_box is not None

    @patch("friday.computer.screen.capture_screen")
    @patch("friday.computer.screen.ocr", return_value="Click the Save button")
    @patch("friday.computer.screen.describe_screen", return_value={"status": "error"})
    def test_ocr_match_confidence(self, mock_describe, mock_ocr, mock_capture, resolver):
        """OCR match should return reasonable confidence."""
        from PIL import Image
        mock_capture.return_value = MagicMock(spec=Image.Image)
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
        from PIL import Image
        mock_capture.return_value = MagicMock(spec=Image.Image)
        result = resolver.resolve("Save button", {})
        assert result is not None
        assert result.method == ResolutionMethod.VISUAL_MATCH
        assert result.confidence >= 0.5