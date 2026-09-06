"""
tests/interaction/test_turn_detector.py

WHAT THIS IS FOR:
Unit tests for the TurnDetector (Runbook §20).

Cases:
  - silence_after_speech -> END_TURN
  - continuation_token    -> KEEP_LISTENING
  - interrupt_during_tts -> INTERRUPT
  - wake_word_in_text    -> WAKE_DETECTED
  - max_turn_seconds     -> END_TURN
"""

from __future__ import annotations

import pytest

from friday.interaction.turn_detector import (
    TurnAction,
    TurnDetector,
    TurnDetectorConfig,
)
from friday.interaction.stt import TranscriptEvent
from friday.interaction.vad import VadEvent, VadEventKind


def _vad(kind: VadEventKind, ts: float = 0.0) -> VadEvent:
    return VadEvent(kind=kind, confidence=0.9, timestamp=ts)


def _partial(text: str, ts: float = 0.0) -> TranscriptEvent:
    return TranscriptEvent(text=text, is_final=False, confidence=0.8, start_time=ts, end_time=ts, turn_id="t1")


class TestTurnDetector:
    def test_silence_after_speech_ends_turn(self):
        td = TurnDetector()
        td.observe_vad(_vad(VadEventKind.SPEECH_STARTED, 0.0))
        td.observe_partial(_partial("open VS code", 0.05))
        td.observe_partial(_partial("open VS code", 0.10))
        td.observe_vad(_vad(VadEventKind.SPEECH_ENDED, 0.2))
        decision = td.decide(now=1.5, transcript="open VS code")  # 1.3s of silence
        assert decision.action == TurnAction.END_TURN
        assert decision.transcript == "open VS code"

    def test_continuation_token_keeps_listening(self):
        td = TurnDetector()
        td.observe_vad(_vad(VadEventKind.SPEECH_STARTED, 0.0))
        td.observe_partial(_partial("open VS code and then", 0.1))
        decision = td.decide(now=0.5, transcript="open VS code and then")
        assert decision.action == TurnAction.KEEP_LISTENING

    def test_interrupt_during_tts(self):
        td = TurnDetector()
        td.set_system_speaking(True)
        td.observe_vad(_vad(VadEventKind.SPEECH_STARTED, 0.0))
        decision = td.decide(now=0.1, transcript="stop")
        assert decision.action == TurnAction.INTERRUPT

    def test_wake_word_returns_wake_detected(self):
        td = TurnDetector(wake_word="friday")
        decision = td.decide(now=0.0, transcript="friday open chrome")
        assert decision.action == TurnAction.WAKE_DETECTED

    def test_max_turn_seconds_exceeded(self):
        cfg = TurnDetectorConfig(max_turn_seconds=0.5)
        td = TurnDetector(config=cfg)
        # SPEECH_STARTED at ts=1.0; decide at ts=10.0 -> 9s > 0.5s cap.
        td.observe_vad(_vad(VadEventKind.SPEECH_STARTED, 1.0))
        decision = td.decide(now=10.0, transcript="still talking")
        assert decision.action == TurnAction.END_TURN
        assert decision.reason == "max_turn_seconds_exceeded"

    def test_reset(self):
        td = TurnDetector()
        td.observe_vad(_vad(VadEventKind.SPEECH_STARTED, 0.0))
        td.reset()
        decision = td.decide(now=0.0, transcript="hello")
        assert decision.action == TurnAction.WAKE_DETECTED or decision.action == TurnAction.KEEP_LISTENING

    def test_authorization_pending_shortens_silence_threshold(self):
        td = TurnDetector()
        td.observe_vad(_vad(VadEventKind.SPEECH_STARTED, 0.0))
        td.observe_partial(_partial("yes", 0.05))
        td.observe_partial(_partial("yes", 0.10))
        td.observe_vad(_vad(VadEventKind.SPEECH_ENDED, 0.2))
        # Silence = 0.5s, threshold under auth_pending = max(0.25, 0.7*0.6)=0.42.
        decision = td.decide(now=0.7, transcript="yes", authorization_pending=True)
        assert decision.action == TurnAction.END_TURN

    def test_silence_before_speech_does_not_end_turn(self):
        td = TurnDetector()
        td.observe_vad(_vad(VadEventKind.NO_SPEECH, 0.0))
        td.observe_vad(_vad(VadEventKind.NO_SPEECH, 0.5))
        decision = td.decide(now=1.5, transcript="")
        assert decision.action == TurnAction.KEEP_LISTENING
        assert decision.reason == "awaiting_input"
