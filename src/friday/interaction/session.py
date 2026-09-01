"""Live, interruptible voice-session state machine."""
from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    IDLE = "idle"
    LISTENING_FOR_WAKE = "listening_for_wake"
    WAKE_DETECTED = "wake_detected"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    FOLLOWUP_LISTENING = "followup_listening"
    ERROR = "error"


class VoiceSession:
    """Connect wake word, STT, agent, and TTS while preserving turn context."""

    CONTROL_COMMANDS = {
        "stop": "stop",
        "pause": "pause",
        "go offline": "offline",
        "go online": "online",
        "use fast mode": "fast",
        "use deep reasoning": "deep",
        "use the safer mode": "safer",
        "explain what you're doing": "explain",
    }

    def __init__(
        self,
        stt: Any,
        tts: Any,
        wakeword: Any,
        agent: Callable[[str], Any],
        followup_window_seconds: float = 5.0,
        controls: dict[str, Callable[[], Any]] | None = None,
        on_state_change: Callable[[SessionState], None] | None = None,
    ) -> None:
        self.stt = stt
        self.tts = tts
        self.wakeword = wakeword
        self.agent = agent
        self.followup_window_seconds = followup_window_seconds
        self.controls = controls or {}
        self.on_state_change = on_state_change
        self.state = SessionState.IDLE
        self.cancelled = False
        self._turn_generation = 0

    def set_state(self, state: SessionState) -> None:
        self.state = state
        if self.on_state_change:
            self.on_state_change(state)

    def cancel(self) -> None:
        """Invalidate the active turn and stop current speech."""
        self.cancelled = True
        self._turn_generation += 1
        if hasattr(self.tts, "cancel"):
            self.tts.cancel()
        self.set_state(SessionState.INTERRUPTED)

    def run_once(self, require_wake: bool = True) -> str | None:
        """Run one wake plus conversational exchange, including bounded follow-ups."""
        self.cancelled = False
        try:
            if require_wake:
                self.set_state(SessionState.LISTENING_FOR_WAKE)
                self.wakeword.listen_for_wakeword()
                self.set_state(SessionState.WAKE_DETECTED)
            self.set_state(SessionState.LISTENING)
            audio_path = self.stt.record_until_silence()
            return self._process_audio(audio_path)
        except Exception:
            self.set_state(SessionState.ERROR)
            raise
        finally:
            if self.state not in {SessionState.ERROR, SessionState.INTERRUPTED}:
                self.set_state(SessionState.IDLE)

    def run_loop(self) -> None:
        while True:
            self.run_once(require_wake=True)

    def _process_audio(self, audio_path: str) -> str | None:
        current_path: str | None = audio_path
        last_response: str | None = None
        while current_path and not self.cancelled:
            generation = self._turn_generation
            self.set_state(SessionState.TRANSCRIBING)
            transcript = self.stt.transcribe(current_path).strip()
            if not transcript:
                return last_response
            if self._run_control(transcript):
                return last_response

            self.set_state(SessionState.THINKING)
            response = self.agent(transcript)
            response_text = self._response_text(response)
            if generation != self._turn_generation or self.cancelled:
                return last_response

            self.set_state(SessionState.SPEAKING)
            result = self.tts.speak_interruptible(
                response_text,
                self.wakeword,
                on_interrupt=self.cancel,
            )
            if bool(getattr(result, "interrupted", result if isinstance(result, bool) else False)):
                self.set_state(SessionState.INTERRUPTED)
                return last_response
            last_response = response_text

            self.set_state(SessionState.FOLLOWUP_LISTENING)
            current_path = self.stt.listen_for_followup(timeout_seconds=self.followup_window_seconds)
        return last_response

    def _run_control(self, transcript: str) -> bool:
        command = transcript.lower().strip().rstrip(".!?")
        control = self.CONTROL_COMMANDS.get(command)
        if control is None:
            return False
        if control == "stop":
            self.cancel()
            return True
        callback = self.controls.get(control)
        if callback:
            callback()
        return True

    @staticmethod
    def _response_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        message = getattr(response, "last_message", None)
        if message:
            return str(message)
        return str(response)


__all__ = ["SessionState", "VoiceSession"]
