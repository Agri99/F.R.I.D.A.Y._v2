"""
src/friday/interaction/turn_detector.py

WHAT THIS IS FOR:
Turn detection distinct from VAD.

Runbook §20 — VAD says "someone is speaking"; turn detection decides
"the user has finished the request." Inputs:

    VAD state
    partial transcript stability
    pause duration
    current conversation state
    authorization state
    wake state

Outputs a TurnDecision that the ConversationManager consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from friday.interaction.stt import TranscriptEvent
from friday.interaction.vad import VadEvent, VadEventKind


class TurnAction(str, Enum):
    """Action to take after evaluating a turn boundary."""
    END_TURN = "end_turn"
    KEEP_LISTENING = "keep_listening"
    INTERRUPT = "interrupt"
    WAKE_DETECTED = "wake_detected"


@dataclass
class TurnDecision:
    action: TurnAction
    reason: str
    transcript: str = ""
    confidence: float = 0.0


# Substrings that strongly indicate the user is mid-sentence and wants the
# system to keep listening rather than act.
_CONTINUATION_TOKENS = (
    " and then",
    " and ",
    " then ",
    " after that",
    " plus ",
    " also ",
    " but ",
    " because ",
    ", and",
    ", then",
)

# Substrings that, when spoken mid-response, indicate interruption.
_INTERRUPT_TOKENS = (
    "stop",
    "cancel",
    "shut up",
    "wait",
    "pause",
    "hold on",
    "nevermind",
    "never mind",
    "actually",
)


@dataclass
class TurnDetectorConfig:
    """Configuration for the deterministic turn detector."""
    silence_to_end_s: float = 0.7        # silence required to END_TURN after speech
    max_turn_seconds: float = 30.0      # hard cap on a single turn
    partial_stability_window: int = 2   # # of equal partials to count as "stable"
    interrupt_window_s: float = 0.4     # interrupt considered when speaking + interrupt token
    continuation_window_s: float = 0.8  # continuation tokens considered after speech starts


class TurnDetector:
    """Decide END_TURN / KEEP_LISTENING / INTERRUPT / WAKE_DETECTED.

    The detector is deliberately deterministic (no LLM call) so that
    ConversationManager can rely on bounded latency. It consumes VAD events
    and partial TranscriptEvents.
    """

    def __init__(
        self,
        config: TurnDetectorConfig | None = None,
        wake_word: str = "friday",
    ) -> None:
        self.config = config or TurnDetectorConfig()
        self.wake_word = wake_word.lower()
        self._vad_state: VadEventKind | None = None
        self._last_vad_at: float | None = None
        self._last_speech_at: float | None = None
        self._last_silence_at: float | None = None
        self._turn_started_at: float | None = None
        self._partial_history: list[str] = []
        self._last_partial_text: str = ""
        self._stable_count: int = 0
        self._in_speech: bool = False
        self._system_speaking: bool = False

    def set_system_speaking(self, speaking: bool) -> None:
        """ConversationManager calls this when TTS is active."""
        self._system_speaking = bool(speaking)

    def observe_vad(self, event: VadEvent) -> None:
        self._vad_state = event.kind
        self._last_vad_at = event.timestamp
        if event.kind == VadEventKind.SPEECH_STARTED:
            self._in_speech = True
            self._last_speech_at = event.timestamp
            self._last_silence_at = None
            if self._turn_started_at is None:
                self._turn_started_at = event.timestamp
        elif event.kind == VadEventKind.SPEECH_CONTINUED:
            self._in_speech = True
            self._last_speech_at = event.timestamp
            self._last_silence_at = None
        elif event.kind == VadEventKind.SPEECH_ENDED:
            self._in_speech = False
            if self._last_silence_at is None:
                self._last_silence_at = event.timestamp
        else:
            # NO_SPEECH
            self._in_speech = False
            if self._turn_started_at is not None and self._last_silence_at is None:
                self._last_silence_at = event.timestamp

    def observe_partial(self, event: TranscriptEvent) -> None:
        """Track partial transcripts to detect stability / wake word / interrupts."""
        text = (event.text or "").strip()
        if not text:
            return
        self._partial_history.append(text)
        if text == self._last_partial_text:
            self._stable_count += 1
        else:
            self._stable_count = 0
            self._last_partial_text = text

    def decide(
        self,
        now: float,
        transcript: str = "",
        authorization_pending: bool = False,
    ) -> TurnDecision:
        text = transcript.strip()
        text_lower = text.lower()

        # Wake-word detection is handled before any END_TURN logic.
        if text and self._contains_wake_word(text_lower) and not self._in_speech:
            return TurnDecision(TurnAction.WAKE_DETECTED, "wake_word_in_transcript", transcript=text)

        # Interrupt handling: system is speaking and user said a stop word.
        if self._system_speaking and text_lower:
            elapsed = now - self._last_speech_at if self._last_speech_at is not None else 0.0
            if any(tok in text_lower for tok in _INTERRUPT_TOKENS) and elapsed < self.config.interrupt_window_s + 0.5:
                return TurnDecision(TurnAction.INTERRUPT, "interrupt_token_during_tts", transcript=text)

        # Hard cap on a single turn. ``_turn_started_at`` is None until the
        # first SPEECH_STARTED event; only check after that.
        if self._turn_started_at is not None and (now - self._turn_started_at) > self.config.max_turn_seconds:
            return TurnDecision(TurnAction.END_TURN, "max_turn_seconds_exceeded", transcript=text)

        # Awaiting authorization: shorter pause; user is likely answering yes/no.
        silence_threshold = self.config.silence_to_end_s
        if authorization_pending:
            silence_threshold = max(0.25, self.config.silence_to_end_s * 0.6)

        # KEEP_LISTENING if the user is clearly mid-sentence.
        if self._in_speech and any(tok in (" " + text_lower + " ") for tok in _CONTINUATION_TOKENS):
            return TurnDecision(TurnAction.KEEP_LISTENING, "continuation_token", transcript=text)

        # End the turn when speech has occurred, speech has ended, and silence has exceeded threshold.
        if self._turn_started_at is not None and not self._in_speech and self._last_silence_at is not None:
            silence_duration = now - self._last_silence_at
            if silence_duration >= silence_threshold:
                return TurnDecision(TurnAction.END_TURN, "silence_after_speech", transcript=text)

        # Mid-speech with no silence yet -> keep listening.
        if self._in_speech:
            return TurnDecision(TurnAction.KEEP_LISTENING, "speech_active", transcript=text)

        # Fallback: keep listening briefly to allow wake-word detection.
        return TurnDecision(TurnAction.KEEP_LISTENING, "awaiting_input", transcript=text)

    def reset(self) -> None:
        self._vad_state = None
        self._last_vad_at = None
        self._last_speech_at = None
        self._last_silence_at = None
        self._turn_started_at = None
        self._partial_history = []
        self._last_partial_text = ""
        self._stable_count = 0
        self._in_speech = False
        self._system_speaking = False

    def _contains_wake_word(self, text_lower: str) -> bool:
        if not self.wake_word:
            return False
        return self.wake_word in text_lower


__all__ = ["TurnAction", "TurnDecision", "TurnDetector", "TurnDetectorConfig"]
