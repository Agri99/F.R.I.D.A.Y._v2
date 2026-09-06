"""Live, interruptible voice-session state machine."""
from __future__ import annotations

import time
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
    """Connect wake word, STT, agent, and TTS while preserving turn context.

    Two transport paths are supported:

      * **Legacy** (default): STT records to file, transcribes whole-utterance,
        TTS speaks with barge-in. Used when ``voice_pipeline`` is None.

      * **Event-driven** (Runbook M2): when ``voice_pipeline`` is supplied,
        audio flows through ``AudioInputStream`` -> VAD -> ``StreamingTranscriber``
        -> ``TurnDetector`` -> ``ConversationManager`` -> ``StreamingTts``.
        Stale results are filtered out by ``InterruptionManager`` generation IDs.

    Both paths share the same state machine, control-command set, and
    authorization follow-up handling.
    """

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
        resume_agent: Callable[[str, str], Any] | None = None,
        announce: Callable[[str], Any] | None = None,
        voice_pipeline: Any | None = None,
    ) -> None:
        self.stt = stt
        self.tts = tts
        self.wakeword = wakeword
        self.agent = agent
        self.resume_agent = resume_agent
        self.announce = announce
        self.followup_window_seconds = followup_window_seconds
        self.controls = controls or {}
        self.on_state_change = on_state_change
        self.voice_pipeline = voice_pipeline
        self.state = SessionState.IDLE
        self.cancelled = False
        self._turn_generation = 0
        self._pending_task_id: str | None = None
        self._stop_requested = False

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
        if self.voice_pipeline is not None:
            try:
                interruption = getattr(self.voice_pipeline, "interruption", None)
                if interruption is not None:
                    interruption.interrupt(reason="voice_session_cancel")
                streaming_tts = getattr(self.voice_pipeline, "streaming_tts", None)
                if streaming_tts is not None:
                    streaming_tts.cancel()
            except Exception:
                pass
        self.set_state(SessionState.INTERRUPTED)

    def request_shutdown(self) -> None:
        """Ask ``run_loop`` to exit after the current turn."""
        self._stop_requested = True
        self.cancel()

    def run_once(self, require_wake: bool = True) -> str | None:
        """Run one wake plus conversational exchange, including bounded follow-ups."""
        self.cancelled = False
        try:
            if self.voice_pipeline is not None:
                return self._run_once_event_driven(require_wake=require_wake)
            return self._run_once_legacy(require_wake=require_wake)
        except Exception:
            self.set_state(SessionState.ERROR)
            raise
        finally:
            if self.state not in {SessionState.ERROR, SessionState.INTERRUPTED}:
                self.set_state(SessionState.IDLE)

    def _run_once_legacy(self, require_wake: bool) -> str | None:
        if require_wake:
            self.set_state(SessionState.LISTENING_FOR_WAKE)
            self.wakeword.listen_for_wakeword()
            self.set_state(SessionState.WAKE_DETECTED)
        self.set_state(SessionState.LISTENING)
        audio_path = self.stt.record_until_silence()
        return self._process_audio(audio_path)

    def _run_once_event_driven(self, require_wake: bool) -> str | None:
        pipeline = self.voice_pipeline
        last_response: str | None = None
        while not self.cancelled:
            if require_wake:
                self.set_state(SessionState.LISTENING_FOR_WAKE)
                self.wakeword.listen_for_wakeword()
                self.set_state(SessionState.WAKE_DETECTED)

            self.set_state(SessionState.LISTENING)
            transcript = self._capture_turn_event_driven(pipeline)
            if self.cancelled:
                return last_response
            if transcript is None:
                if self._pending_task_id is not None and last_response:
                    self.set_state(SessionState.SPEAKING)
                    self._speak_event_driven(pipeline, last_response)
                return last_response
            if self._run_control(transcript):
                return last_response

            self.set_state(SessionState.THINKING)
            if self._pending_task_id and self.resume_agent is not None:
                response = self.resume_agent(self._pending_task_id, transcript)
                self._pending_task_id = None
            else:
                response = self.agent(transcript)
            response_text = self._response_text(response)
            if self.cancelled:
                return last_response

            if self.resume_agent is not None and self._is_awaiting_auth(response):
                self._pending_task_id = getattr(response, "id", None)

            self.set_state(SessionState.SPEAKING)
            interrupted = self._speak_event_driven(pipeline, response_text)
            if interrupted:
                self.set_state(SessionState.INTERRUPTED)
                return last_response
            last_response = response_text

            if self._stop_requested:
                break

            self.set_state(SessionState.FOLLOWUP_LISTENING)
            require_wake = False
            if not self._wait_for_followup_event_driven(pipeline):
                return last_response
        return last_response

    def _capture_turn_event_driven(
        self, pipeline: Any, _pre_speech_exit: bool = False
    ) -> str | None:
        """Capture audio via the event-driven pipeline until TurnDetector says END_TURN.

        The wake listener closes its stream before returning, so this method
        opens its own ``AudioInputStream`` on the same device. ``start()``
        retries with backoff to handle the Windows WASAPI "device busy"
        case that occurs immediately after the wake stream closes.
        """
        from friday.interaction.audio_input import AudioInputStream
        from friday.interaction.vad import VadEventKind
        from friday.interaction.stt import TranscriptEvent

        audio_in: AudioInputStream = pipeline.audio_input
        vad = pipeline.vad
        transcriber = pipeline.transcriber
        turn_detector = pipeline.turn_detector
        interruption = pipeline.interruption
        conversation = pipeline.conversation

        turn_id = conversation.begin_turn()
        captured_generation = interruption.generation()
        transcriber.start_streaming(callback=None, turn_id=turn_id)
        turn_detector.reset()
        turn_detector.set_system_speaking(conversation.snapshot().speaking)

        max_idle_seconds = 5.0
        max_capture_seconds = 30.0  # Maximum total capture duration
        last_chunk_at = time.time()
        capture_started_at = time.time()

        try:
            audio_in.start()
        except Exception as exc:
            print(f"FRIDAY [Voice]: audio input unavailable: {exc}")
            self.set_state(SessionState.ERROR)
            return None

        final_text: str | None = None
        current_partial: str = ""
        last_heartbeat = time.time()
        last_logged_state: str | None = None
        try:
            while not self.cancelled:
                if interruption.is_stale(captured_generation):
                    return None
                # State heartbeat so the user sees FRIDAY is alive. Prints
                # only when the state changes or every 3s of silence.
                current_state = self.state.value if hasattr(self.state, "value") else str(self.state)
                now = time.time()
                if turn_detector._turn_started_at is None:
                    if now - last_heartbeat > 3.0:
                        print(f"FRIDAY [Voice]: state={current_state} still listening...")
                        last_heartbeat = now
                    # Overall capture timeout - give up if no speech detected
                    if now - capture_started_at > max_capture_seconds:
                        print(f"FRIDAY [Voice]: capture timeout after {max_capture_seconds}s")
                        break
                elif last_logged_state != "transcribing":
                    print(f"FRIDAY [Voice]: state=transcribing")
                    last_logged_state = "transcribing"
                    last_heartbeat = now
                # Pull chunks with a short timeout so we re-check interruption.
                try:
                    chunk = audio_in.queue.get(timeout=0.05)
                except Exception:
                    # Idle watchdog. Only fires AFTER speech has started so we
                    # don't return to the wake listener while the user is just
                    # quiet. Without a ``turn_started_at``, the user hasn't said
                    # anything yet - keep listening indefinitely.
                    idle = time.time() - last_chunk_at
                    if turn_detector._turn_started_at is not None and idle > max_idle_seconds:
                        break
                    if _pre_speech_exit and turn_detector._turn_started_at is None and idle > 0.5:
                        break
                    continue
                last_chunk_at = time.time()
                vad_event = vad.process(chunk.data, chunk.timestamp)
                turn_detector.observe_vad(vad_event)
                if vad_event.kind == VadEventKind.SPEECH_STARTED:
                    self.set_state(SessionState.TRANSCRIBING)
                transcriber.submit_chunk(chunk.data, timestamp=chunk.timestamp)
                for ev in transcriber.drain_events():
                    if isinstance(ev, TranscriptEvent):
                        turn_detector.observe_partial(ev)
                        if ev.text:
                            current_partial = ev.text
                decision = turn_detector.decide(now=time.time(), transcript=current_partial)
                if decision.action.value == "wake_detected":
                    self.set_state(SessionState.WAKE_DETECTED)
                    continue
                if decision.action.value == "interrupt":
                    interruption.interrupt(reason="turn_detector_interrupt")
                    return None
                if decision.action.value == "end_turn":
                    break
        finally:
            try:
                audio_in.stop()
            except Exception:
                pass
            events = transcriber.finalize()
            if events:
                final_text = events[-1].text
            else:
                final_text = current_partial or None
        return (final_text or "").strip() or None

    @staticmethod
    def _collect_final_transcript(transcriber: Any) -> str | None:
        events = transcriber.drain_events()
        if not events:
            return None
        return events[-1].text

    def _speak_event_driven(self, pipeline: Any, text: str) -> bool:
        """Stream text through StreamingTts. Return True if interrupted."""
        from friday.interaction.streaming_tts import iter_llm_deltas_to_text
        from friday.models.base import ModelDelta

        streaming_tts = pipeline.streaming_tts
        interruption = pipeline.interruption
        conversation = pipeline.conversation
        turn_detector = pipeline.turn_detector

        # Start TTS first; this bumps the generation. The capture point for
        # staleness checks is the generation produced by start().
        streaming_tts.start(turn_id=conversation.active_turn_id or "")
        captured = interruption.generation()
        turn_detector.set_system_speaking(True)
        conversation.set_speaking(True)

        def on_interrupt(prev_gen: int, new_gen: int) -> None:
            streaming_tts.cancel()
            conversation.set_speaking(False)
            turn_detector.set_system_speaking(False)

        interruption.register("voice_session_speak", on_interrupt)
        try:
            # Build a tiny ModelDelta generator from the static text. For real
            # streaming, callers wire a ModelProvider.stream(); this fallback
            # makes the path testable without an LLM.
            deltas = [ModelDelta(text=text)]
            for delta in iter_llm_deltas_to_text(deltas):
                streaming_tts.feed(delta)
                if interruption.is_stale(captured):
                    return True
            streaming_tts.finish()
            # Chunks land on the sink; the audio consumer (sounddevice
            # OutputStream in production, test consumer in CI) drains them.
            return interruption.is_stale(captured)
        finally:
            conversation.set_speaking(False)
            turn_detector.set_system_speaking(False)
            interruption.unregister("voice_session_speak")

    def _wait_for_followup_event_driven(self, pipeline: Any) -> bool:
        """Wait briefly for follow-up audio. Return True if user spoke, False on timeout.

        Drains any leftover audio from the previous capture first so that
        stale chunks don't falsely look like fresh user input.
        """
        from friday.interaction.audio_input import AudioInputStream
        from friday.interaction.vad import VadEventKind

        audio_in: AudioInputStream = pipeline.audio_input
        vad = pipeline.vad
        # Drain any leftover audio from the capture loop. Anything queued
        # after this point is genuinely new user input.
        try:
            while True:
                audio_in.queue.get_nowait()
        except Exception:
            pass
        # Reset VAD so stale internal state doesn't bias the next decision.
        if hasattr(vad, "reset"):
            try:
                vad.reset()
            except Exception:
                pass

        deadline = time.time() + self.followup_window_seconds
        audio_in.start()
        try:
            while time.time() < deadline and not self.cancelled:
                try:
                    chunk = audio_in.queue.get(timeout=0.05)
                except Exception:
                    continue
                vad_event = vad.process(chunk.data, chunk.timestamp)
                if vad_event.kind == VadEventKind.SPEECH_STARTED:
                    return True
        finally:
            try:
                audio_in.stop()
            except Exception:
                pass
        return False

    def run_loop(self) -> None:
        while not self._stop_requested:
            try:
                self.run_once(require_wake=True)
            except Exception:
                if self._stop_requested:
                    break
                raise
        self.set_state(SessionState.IDLE)

    def _process_audio(self, audio_path: str) -> str | None:
        current_path: str | None = audio_path
        last_response: str | None = None
        while current_path and not self.cancelled:
            generation = self._turn_generation
            self.set_state(SessionState.TRANSCRIBING)
            transcript = self.stt.transcribe(current_path).strip()
            if not transcript:
                # No speech detected.  If we are awaiting authorization,
                # re-prompt the user instead of silently dropping the task.
                if self._pending_task_id is not None and last_response:
                    self.set_state(SessionState.SPEAKING)
                    self.tts.speak_interruptible(last_response, self.wakeword, on_interrupt=self.cancel)
                return last_response
            if self._run_control(transcript):
                return last_response

            self.set_state(SessionState.THINKING)
            if self._pending_task_id and self.resume_agent is not None:
                response = self.resume_agent(self._pending_task_id, transcript)
                self._pending_task_id = None
            else:
                response = self.agent(transcript)
            response_text = self._response_text(response)
            if generation != self._turn_generation or self.cancelled:
                return last_response

            # Keep an authorization task alive for the next follow-up turn.
            if self.resume_agent is not None and self._is_awaiting_auth(response):
                self._pending_task_id = getattr(response, "id", None)

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

            if self._stop_requested:
                break

            self.set_state(SessionState.FOLLOWUP_LISTENING)
            current_path = self.stt.listen_for_followup(timeout_seconds=self.followup_window_seconds)
        return last_response

    def _run_control(self, transcript: str) -> bool:
        command = transcript.lower().strip().rstrip(".!?")
        control = self.CONTROL_COMMANDS.get(command)
        if control is None:
            return False
        if control == "stop":
            self.request_shutdown()
            return True
        callback = self.controls.get(control)
        if callback:
            callback()
        return True

    @staticmethod
    def _is_awaiting_auth(response: Any) -> bool:
        status = getattr(response, "status", None)
        if status is None:
            return False
        return getattr(status, "value", str(status)) == "AWAITING_AUTHORIZATION"

    @staticmethod
    def _response_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        message = getattr(response, "last_message", None)
        if message:
            return str(message)
        return str(response)


__all__ = ["SessionState", "VoiceSession"]
