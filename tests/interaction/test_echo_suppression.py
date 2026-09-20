"""
tests/interaction/test_echo_suppression.py

Tests for echo suppression during barge-in (Runbook §24).
"""

from __future__ import annotations

import time
import numpy as np
import pytest

from friday.interaction.echo_suppression import (
    EchoSuppressionConfig,
    SimpleSpectrumMatcher,
    EchoSuppressingBargeInDetector,
)
from friday.interaction.vad import RmsVoiceActivityDetector


class TestSimpleSpectrumMatcher:
    """Tests for spectrum matcher."""

    def test_identical_audio_detected_as_echo(self):
        """Identical audio should be detected as echo."""
        matcher = SimpleSpectrumMatcher()

        # Create simulated output audio
        audio = np.random.randint(-1000, 1000, 1600, dtype=np.int16)

        # Add as reference
        matcher.add_reference_audio(audio)

        # Test same audio
        assert matcher.is_likely_echo(audio)

    def test_different_audio_not_echo(self):
        """Different audio should not be detected as echo."""
        matcher = SimpleSpectrumMatcher()

        # Create output audio (low frequency)
        t = np.linspace(0, 0.1, 1600)
        output_audio = (np.sin(2 * np.pi * 200 * t) * 1000).astype(np.int16)

        # Create input audio (high frequency)
        input_audio = (np.sin(2 * np.pi * 2000 * t) * 1000).astype(np.int16)

        matcher.add_reference_audio(output_audio)

        # High frequency should not be considered echo of low frequency
        assert not matcher.is_likely_echo(input_audio)

    def test_no_reference_returns_false(self):
        """No reference audio means not echo."""
        matcher = SimpleSpectrumMatcher()

        audio = np.random.randint(-1000, 1000, 1600, dtype=np.int16)

        assert not matcher.is_likely_echo(audio)

    def test_clear_reference(self):
        """Clearing reference resets state."""
        matcher = SimpleSpectrumMatcher()

        audio = np.random.randint(-1000, 1000, 1600, dtype=np.int16)
        matcher.add_reference_audio(audio)

        assert matcher.is_likely_echo(audio)

        matcher.clear_reference()

        assert not matcher.is_likely_echo(audio)


class TestEchoSuppressingBargeInDetector:
    """Tests for echo-suppressing barge-in detector."""

    @pytest.fixture
    def mock_vad(self):
        """Create a mock VAD that always detects speech for non-silent audio."""
        vad = RmsVoiceActivityDetector(rms_threshold=50.0, speech_chunks_to_start=1)
        return vad

    def test_speech_detected_without_echo(self, mock_vad):
        """Real speech without output audio should trigger barge-in."""
        detector = EchoSuppressingBargeInDetector(mock_vad)

        # Speech audio
        speech = np.random.randint(-1000, 1000, 1600, dtype=np.int16)

        # Should detect barge-in (no reference audio)
        assert detector.is_speech_barge_in(speech, time.time())

    def test_echo_suppressed(self, mock_vad):
        """Echo of output should NOT trigger barge-in."""
        detector = EchoSuppressingBargeInDetector(mock_vad)

        # Output audio
        output_audio = np.random.randint(-1000, 1000, 1600, dtype=np.int16)
        detector.add_output_audio(output_audio)

        # Same audio returned as microphone input (pure echo)
        assert not detector.is_speech_barge_in(output_audio, time.time())

    def test_silence_not_barge_in(self, mock_vad):
        """Silence should never trigger barge-in."""
        detector = EchoSuppressingBargeInDetector(mock_vad)

        # Silence
        silence = np.zeros(1600, dtype=np.int16)

        assert not detector.is_speech_barge_in(silence, time.time())

    def test_reset_clears_state(self, mock_vad):
        """Reset clears both VAD and echo detector state."""
        detector = EchoSuppressingBargeInDetector(mock_vad)

        audio = np.random.randint(-1000, 1000, 1600, dtype=np.int16)
        detector.add_output_audio(audio)

        detector.reset()

        # After reset, reference is gone, so same audio is treated as new speech
        assert detector.is_speech_barge_in(audio, time.time())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
