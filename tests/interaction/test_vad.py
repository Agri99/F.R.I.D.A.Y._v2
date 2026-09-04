"""
tests/interaction/test_vad.py

WHAT THIS IS FOR:
Unit tests for the VoiceActivityDetector abstraction (Runbook §19).
Platform-independent: no sounddevice/PortAudio needed.
"""

from __future__ import annotations

import numpy as np
import pytest

from friday.interaction.vad import (
    CompositeVad,
    RmsVoiceActivityDetector,
    VadEventKind,
)


def _silence(duration_ms: int = 100, sample_rate: int = 16000) -> np.ndarray:
    return np.zeros(int(sample_rate * duration_ms / 1000), dtype=np.int16)


def _tone(duration_ms: int = 100, sample_rate: int = 16000, amplitude: int = 5000) -> np.ndarray:
    n = int(sample_rate * duration_ms / 1000)
    t = np.linspace(0, 1, n, endpoint=False)
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.int16)


class TestRmsVad:
    def test_silence_emits_no_speech(self):
        vad = RmsVoiceActivityDetector(rms_threshold=400, speech_chunks_to_start=1)
        events = [vad.process(_silence(20), i * 0.02) for i in range(5)]
        assert all(e.kind == VadEventKind.NO_SPEECH for e in events)

    def test_speech_then_silence_emits_start_then_end(self):
        vad = RmsVoiceActivityDetector(rms_threshold=400, speech_chunks_to_start=2, silence_chunks_to_end=3)
        events = []
        # 4 speech chunks -> SPEECH_STARTED after 2nd speech chunk, then continued
        for i in range(4):
            events.append(vad.process(_tone(20, amplitude=8000), i * 0.02))
        # 5 silence chunks -> SPEECH_ENDED after the 3rd silence chunk
        for i in range(5):
            events.append(vad.process(_silence(20), (4 + i) * 0.02))

        kinds = [e.kind for e in events]
        assert VadEventKind.SPEECH_STARTED in kinds
        assert VadEventKind.SPEECH_ENDED in kinds

    def test_reset_clears_state(self):
        vad = RmsVoiceActivityDetector()
        vad.process(_tone(20, amplitude=8000), 0.0)
        vad.reset()
        events = [vad.process(_silence(20), 0.02)]
        assert events[0].kind == VadEventKind.NO_SPEECH

    def test_validation(self):
        with pytest.raises(ValueError):
            RmsVoiceActivityDetector(rms_threshold=-1)
        with pytest.raises(ValueError):
            RmsVoiceActivityDetector(silence_chunks_to_end=0)


class TestCompositeVad:
    def test_requires_detector(self):
        with pytest.raises(ValueError):
            CompositeVad([])

    def test_majority_vote_speech(self):
        rms = RmsVoiceActivityDetector(rms_threshold=400, speech_chunks_to_start=1)
        rms2 = RmsVoiceActivityDetector(rms_threshold=400, speech_chunks_to_start=1)
        composite = CompositeVad([rms, rms2])
        event = composite.process(_tone(20, amplitude=8000), 0.0)
        assert event.kind in (VadEventKind.SPEECH_STARTED, VadEventKind.SPEECH_CONTINUED)

    def test_silence_vote(self):
        rms = RmsVoiceActivityDetector(rms_threshold=400)
        rms2 = RmsVoiceActivityDetector(rms_threshold=400)
        composite = CompositeVad([rms, rms2])
        event = composite.process(_silence(20), 0.0)
        assert event.kind == VadEventKind.NO_SPEECH
