"""Live, interruptible voice-session state machine.

Live Conversation v1 — True Duplex:
  • One persistent microphone stream across the entire conversation
  • Ring-buffered audio across turns (no speech loss)
  • Cancelable playback via sd.OutputStream (not blocking sd.play)
  • Continuous barge-in detection during playback
  • Sentence-level streaming TTS from full response text
  • Latency metrics: speech-end→transcript, →first-LLM, →first-audio, interruption→stop
"""
from __future__ import annotations

import logging
import time
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


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


@dataclass
class TurnLatency:
    """Latency metrics for a single conversational turn."""
    speech_end_at: float | None = None
    first_transcript_at: float | None = None
    first_llm_token_at: float | None = None
    first_audio_at: float | None = None
    interruption_at: float | None = None
    audio_stop_at: float | None = None

    def report(self) -> dict[str, float | None]:
        def _delta(start: float | None, end: float | None) -> float | None:
            if start is None or end is None:
                return None
            return round(end - start, 3)
        return {
            "speech_end_to_first_transcript": _delta(self.speech_end_at, self.first_transcript_at),
            "speech_end_to_first_llm_token": _delta(self.speech_end_at, self.first_llm_token_at),
            "speech_end_to_first_audio": _delta(self.speech_end_at, self.first_audio_at),
            "interruption_to_audio_stop": _delta(self.interruption_at, self.audio_stop_at),
        }

    def log(self) -> None:
        metrics = self.report()
        parts = [f"{k}={v:.3f}s" for k, v in metrics.items() if v is not None]
        if parts:
            print(f"FRIDAY [Latency]: {', '.join(parts)}")


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
        followup_window_seconds: float = 10.0,
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
        # Playback cancellation
        self._playback_stop = threading.Event()
        from friday.agent.fastpath import FastPathRouter
        self._fastpath = FastPathRouter()

    def set_state(self, state: SessionState) -> None:
        self.state = state
        if self.on_state_change:
            self.on_state_change(state)

    def cancel(self) -> None:
        """Invalidate the active turn and stop current speech."""
        self.cancelled = True
        self._turn_generation += 1
        self._playback_stop.set()
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

    # ------------------------------------------------------------------
    # Event-driven path — Live Conversation v1
    # ------------------------------------------------------------------

    def _run_once_event_driven(self, require_wake: bool) -> str | None:
        """Full duplex conversation loop with persistent mic."""
        from friday.interaction.audio_input import AudioInputStream

        pipeline = self.voice_pipeline
        audio_in: AudioInputStream = pipeline.audio_input
        last_response: str | None = None

        print(f"FRIDAY [Voice]: Event-driven pipeline started (require_wake={require_wake})")

        # --- Persistent microphone: open once, close in finally ---
        try:
            audio_in.start()
        except Exception as exc:
            print(f"FRIDAY [Voice]: audio input unavailable: {exc}")
            self.set_state(SessionState.ERROR)
            return None

        try:
            while not self.cancelled:
                if require_wake:
                    # Stop the persistent mic while the wake-word listener
                    # uses its own stream, then restart after detection.
                    try:
                        audio_in.stop()
                    except Exception:
                        pass
                    self.set_state(SessionState.LISTENING_FOR_WAKE)
                    print("FRIDAY [Voice]: Listening for wake word...")
                    self.wakeword.listen_for_wakeword()
                    self.set_state(SessionState.WAKE_DETECTED)
                    print("FRIDAY [Voice]: Wake word detected!")
                    # Re-open mic after wake-word listener releases its stream
                    try:
                        audio_in.start()
                    except Exception as exc:
                        print(f"FRIDAY [Voice]: audio input unavailable after wake: {exc}")
                        self.set_state(SessionState.ERROR)
                        return None
                    require_wake = False
                    self.set_state(SessionState.LISTENING)
                    print("FRIDAY [Voice]: Listening for speech...")
                    max_wait = 10.0
                else:
                    self.set_state(SessionState.FOLLOWUP_LISTENING)
                    self.set_state(SessionState.LISTENING)
                    max_wait = self.followup_window_seconds
                    print(f"FRIDAY [Voice]: Listening for follow-up ({max_wait:.0f}s)...")

                latency = TurnLatency()
                transcript = self._capture_turn_event_driven(pipeline, latency=latency, max_wait_for_speech=max_wait)

                if self.cancelled:
                    print("FRIDAY [Voice]: Cancelled during capture")
                    return last_response
                if transcript is None:
                    print("FRIDAY [Voice]: No speech detected")
                    if self._pending_task_id is not None and last_response:
                        self.set_state(SessionState.SPEAKING)
                        self._speak_event_driven(pipeline, last_response, latency=latency)
                    return last_response
                if self._run_control(transcript):
                    return last_response

                self.set_state(SessionState.THINKING)
                print(f"\nUSER: {transcript}")

                llm_start = time.time()
                fastpath_match = getattr(self, "_fastpath", None).match(transcript) if getattr(self, "_fastpath", None) else None
                if fastpath_match:
                    # FastPath intent (time, apps, window control, volume, orb, shutdown).
                    # These execute locally in milliseconds — NEVER start speculative ack!
                    response = self.agent(transcript)
                    latency.first_llm_token_at = time.time()
                    response_text = self._response_text(response)
                elif self._pending_task_id and self.resume_agent is not None:
                    response = self.resume_agent(self._pending_task_id, transcript)
                    self._pending_task_id = None
                    latency.first_llm_token_at = time.time()
                    response_text = self._response_text(response)
                else:
                    ack_event = threading.Event()
                    ack_speaking = threading.Event()

                    def _maybe_speculative_ack():
                        # Delay before acknowledging (1.8s). If task completes quickly (FastPath/simple query), abort.
                        if ack_event.wait(timeout=1.8):
                            return
                        if self.cancelled or self._stop_requested:
                            return
                        ack_speaking.set()
                        try:
                            print("FRIDAY [Voice]: Long task detected, providing acknowledgment...")
                            self.tts.speak_interruptible("On it, working on that now.", self.wakeword)
                        except Exception as e:
                            print(f"FRIDAY [Voice]: speculative ack failed: {e}")
                        finally:
                            ack_speaking.clear()

                    ack_thread = threading.Thread(target=_maybe_speculative_ack, daemon=True)
                    ack_thread.start()

                    try:
                        response = self.agent(transcript)
                    finally:
                        ack_event.set()

                    # If ack is currently speaking, wait for it to finish before main response playback
                    if ack_speaking.is_set():
                        ack_thread.join(timeout=2.0)

                    latency.first_llm_token_at = time.time()
                    response_text = self._response_text(response)

                print(f"FRIDAY: {response_text}\n")
                if self.cancelled:
                    return last_response

                if self.resume_agent is not None and self._is_awaiting_auth(response):
                    self._pending_task_id = getattr(response, "id", None)

                self.set_state(SessionState.SPEAKING)
                interrupted = self._speak_event_driven(
                    pipeline, response_text, latency=latency
                )
                if interrupted:
                    self.set_state(SessionState.INTERRUPTED)
                    print("FRIDAY [Voice]: Speech interrupted by user")
                    latency.log()
                    # After barge-in, go straight back to listening
                    # (mic is still open, audio is ring-buffered)
                    require_wake = False
                    continue

                last_response = response_text
                print("FRIDAY [Voice]: Response delivered successfully")
                latency.log()

                import friday.tools.system as sys_tools
                if self._stop_requested or sys_tools.SHUTDOWN_REQUESTED:
                    break

                # Prepare for follow-up turn (mic stays open, wake word not required)
                require_wake = False
                continue
        finally:
            try:
                audio_in.stop()
            except Exception:
                pass

        return last_response

    def _capture_turn_event_driven(
        self,
        pipeline: Any,
        _pre_speech_exit: bool = False,
        latency: TurnLatency | None = None,
        max_wait_for_speech: float = 8.0,
    ) -> str | None:
        """Capture audio via the event-driven pipeline until TurnDetector says END_TURN.

        The persistent mic is already open; this method just reads from
        the queue without opening/closing the stream.
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
        # Reset VAD for fresh turn
        if hasattr(vad, "reset"):
            vad.reset()

        max_idle_seconds = 0.5
        max_capture_seconds = 30.0
        max_wait_for_speech = float(max_wait_for_speech)
        last_chunk_at = time.time()
        capture_started_at = time.time()


        final_text: str | None = None
        current_partial: str = ""
        last_heartbeat = time.time()
        last_logged_state: str | None = None
        first_transcript_recorded = False

        while not self.cancelled:
            if interruption.is_stale(captured_generation):
                return None
            now = time.time()

            # State heartbeat
            if turn_detector._turn_started_at is None:
                if now - last_heartbeat > 3.0:
                    print(f"FRIDAY [Voice]: state={self.state.value} still listening...")
                    last_heartbeat = now
                if now - capture_started_at > max_wait_for_speech:
                    print(f"FRIDAY [Voice]: capture timeout after {max_wait_for_speech}s waiting for speech")
                    break
            elif last_logged_state != "transcribing":
                print("FRIDAY [Voice]: state=transcribing")
                last_logged_state = "transcribing"
                last_heartbeat = now

            # Pull chunks with a short timeout
            try:
                chunk = audio_in.queue.get(timeout=0.05)
            except Exception:
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
            elif vad_event.kind == VadEventKind.SPEECH_ENDED:
                if latency and latency.speech_end_at is None:
                    latency.speech_end_at = time.time()

            transcriber.submit_chunk(chunk.data, timestamp=chunk.timestamp)
            for ev in transcriber.drain_events():
                if isinstance(ev, TranscriptEvent):
                    turn_detector.observe_partial(ev)
                    if ev.text:
                        current_partial = ev.text
                        if latency and not first_transcript_recorded:
                            latency.first_transcript_at = time.time()
                            first_transcript_recorded = True

            decision = turn_detector.decide(now=time.time(), transcript=current_partial)
            if decision.action.value == "wake_detected":
                self.set_state(SessionState.WAKE_DETECTED)
                continue
            if decision.action.value == "interrupt":
                interruption.interrupt(reason="turn_detector_interrupt")
                return None
            if decision.action.value == "end_turn":
                if latency and latency.speech_end_at is None:
                    latency.speech_end_at = time.time()
                break

        if turn_detector._turn_started_at is None:
            try:
                transcriber.finalize()
            except Exception:
                pass
            return None

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

    def _speak_event_driven(
        self,
        pipeline: Any,
        text: str,
        latency: TurnLatency | None = None,
    ) -> bool:
        """Stream text through sentence-level TTS with cancelable playback.

        Plays audio via sd.OutputStream while monitoring the persistent
        mic for barge-in. Returns True if interrupted, False if completed.
        """

        streaming_tts = pipeline.streaming_tts
        interruption = pipeline.interruption
        conversation = pipeline.conversation
        turn_detector = pipeline.turn_detector
        sink = pipeline.sink
        audio_in = pipeline.audio_input
        vad = pipeline.vad

        # Reset VAD so playback-volume audio doesn't count as "speech"
        if hasattr(vad, "reset"):
            vad.reset()

        # Start TTS and capture generation
        streaming_tts.start(turn_id=conversation.active_turn_id or "")
        captured = interruption.generation()
        turn_detector.set_system_speaking(True)
        conversation.set_speaking(True)

        self._playback_stop.clear()

        def on_interrupt(prev_gen: int, new_gen: int) -> None:
            streaming_tts.cancel()
            self._playback_stop.set()
            conversation.set_speaking(False)
            turn_detector.set_system_speaking(False)

        interruption.register("voice_session_speak", on_interrupt)
        interrupted = False

        try:
            # Feed the text (or iterator) through StreamingTts via the bridge
            # If we have a raw string, wrap it in an accumulating adapter to simulate streaming
            from friday.interaction.llm_streaming import LlmStreamToTts, AccumulatingAdapter
            bridge = LlmStreamToTts(streaming_tts, interruption)
            if isinstance(text, str):
                stream = AccumulatingAdapter(text)
            else:
                # Assume an iterator of ModelDelta already
                stream = text
            # Run the bridge – it will feed StreamingTts and handle cancellation
            bridge.stream(stream, generation_id=captured)
            if interruption.is_stale(captured):
                interrupted = True
                return True
            streaming_tts.finish()

            # Record first-audio time
            if latency and streaming_tts.first_audio_timestamp:
                latency.first_audio_at = streaming_tts.first_audio_timestamp

            # Play each chunk with barge-in monitoring
            chunks = sink.drain()
            for chunk in chunks:
                if interruption.is_stale(captured) or self._playback_stop.is_set():
                    interrupted = True
                    if latency:
                        latency.audio_stop_at = time.time()
                    return True

                barge_in = self._play_chunk_with_bargein(
                    chunk.audio, chunk.sample_rate, audio_in, vad,
                    interruption, captured, latency,
                )
                if barge_in:
                    interrupted = True
                    return True

            return None  # Completed successfully (falsy, not interrupted)

        except Exception as exc:
            logger.error("TTS failed during streaming: %s", exc)
            return None
        finally:
            conversation.set_speaking(False)
            turn_detector.set_system_speaking(False)
            interruption.unregister("voice_session_speak")

    def _play_chunk_with_bargein(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        audio_in: Any,
        vad: Any,
        interruption: Any,
        captured_generation: int,
        latency: TurnLatency | None,
    ) -> bool:
        """Play one audio chunk while monitoring the mic for barge-in.

        Uses sd.OutputStream in callback mode for non-blocking, cancelable
        playback. Returns True if barge-in was detected.
        """
        import numpy as np
        try:
            import sounddevice as sd
        except Exception:
            return False

        from friday.interaction.vad import VadEventKind

        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        if audio_int16.size == 0:
            return False

        # Prepare playback state
        play_pos = [0]
        playback_done = threading.Event()

        def output_callback(outdata, frames, time_info, status):
            start = play_pos[0]
            end = start + frames
            if end >= audio_int16.size:
                # Last chunk — pad with zeros
                valid = audio_int16.size - start
                if valid > 0:
                    outdata[:valid, 0] = audio_int16[start:start + valid]
                outdata[valid:, 0] = 0
                playback_done.set()
                raise sd.CallbackStop()
            else:
                outdata[:, 0] = audio_int16[start:end]
                play_pos[0] = end

        try:
            stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                callback=output_callback,
                blocksize=1024,
            )
            stream.start()
        except Exception:
            # Fallback: blocking play
            try:
                sd.play(audio_int16, samplerate=sample_rate)
                sd.wait()
            except Exception:
                pass
            return False

        try:
            # Monitor mic for barge-in while playing
            while not playback_done.is_set() and not self._playback_stop.is_set():
                if interruption.is_stale(captured_generation):
                    # External interruption
                    stream.stop()
                    if latency:
                        latency.audio_stop_at = time.time()
                    return True

                # Check mic for speech (barge-in)
                try:
                    mic_chunk = audio_in.queue.get(timeout=0.02)
                    vad_event = vad.process(mic_chunk.data, mic_chunk.timestamp)
                    if vad_event.kind == VadEventKind.SPEECH_STARTED:
                        # Barge-in detected!
                        stream.stop()
                        if latency:
                            latency.interruption_at = time.time()
                            latency.audio_stop_at = time.time()
                        interruption.interrupt(reason="user_barge_in")
                        print("FRIDAY [Voice]: Barge-in detected — stopping playback")
                        return True
                except Exception:
                    # No mic data ready — keep playing
                    pass

            return False
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _wait_for_followup_event_driven(self, pipeline: Any) -> bool:
        """Wait briefly for follow-up audio. Return True if user spoke, False on timeout.

        Mic stays open — just monitors the queue for VAD speech events.
        """
        from friday.interaction.vad import VadEventKind

        audio_in = pipeline.audio_input
        vad = pipeline.vad

        # Reset VAD so stale internal state doesn't bias the next decision.
        if hasattr(vad, "reset"):
            try:
                vad.reset()
            except Exception:
                pass

        # Drain any leftover audio from TTS playback
        try:
            while True:
                audio_in.queue.get(timeout=0.0)
        except Exception:
            pass

        deadline = time.time() + self.followup_window_seconds
        while time.time() < deadline and not self.cancelled:
            try:
                chunk = audio_in.queue.get(timeout=0.05)
            except Exception:
                continue
            vad_event = vad.process(chunk.data, chunk.timestamp)
            if vad_event.kind in (VadEventKind.SPEECH_STARTED, VadEventKind.SPEECH_CONTINUED):
                return True
        return False

    def run_loop(self) -> None:
        import friday.tools.system as sys_tools
        while not self._stop_requested and not sys_tools.SHUTDOWN_REQUESTED:
            try:
                self.run_once(require_wake=True)
            except Exception:
                if self._stop_requested or sys_tools.SHUTDOWN_REQUESTED:
                    break
                raise
        self.set_state(SessionState.IDLE)

    # ------------------------------------------------------------------
    # Legacy path (unchanged)
    # ------------------------------------------------------------------

    def _process_audio(self, audio_path: str) -> str | None:
        current_path: str | None = audio_path
        last_response: str | None = None
        while current_path and not self.cancelled:
            generation = self._turn_generation
            self.set_state(SessionState.TRANSCRIBING)
            transcript = self.stt.transcribe(current_path).strip()
            if not transcript:
                if self._pending_task_id is not None and last_response:
                    self.set_state(SessionState.SPEAKING)
                    result = self.tts.speak_interruptible(last_response, self.wakeword, on_interrupt=self.cancel)
                    if not result.success:
                        logger.error("TTS failed during re-prompt: %s", result.error)
                        self.set_state(SessionState.ERROR)
                        return last_response
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

            if self.resume_agent is not None and self._is_awaiting_auth(response):
                self._pending_task_id = getattr(response, "id", None)

            self.set_state(SessionState.SPEAKING)
            result = self.tts.speak_interruptible(
                response_text,
                self.wakeword,
                on_interrupt=self.cancel,
            )
            if not result.success:
                logger.error("TTS failed during response: %s", result.error)
                self.set_state(SessionState.ERROR)
                return last_response
            if getattr(result, "interrupted", False):
                self.set_state(SessionState.INTERRUPTED)
                return last_response
            last_response = response_text

            import friday.tools.system as sys_tools
            if self._stop_requested or sys_tools.SHUTDOWN_REQUESTED:
                break

            self.set_state(SessionState.FOLLOWUP_LISTENING)
            current_path = self.stt.listen_for_followup(timeout_seconds=self.followup_window_seconds)
        return last_response

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _run_control(self, transcript: str) -> bool:
        command = transcript.lower().strip().rstrip(".!?")
        control = self.CONTROL_COMMANDS.get(command)
        if control is None:
            return False
        if control == "stop":
            callback = self.controls.get("stop")
            if callback:
                try:
                    callback()
                except Exception:
                    pass
            else:
                farewell = "Shutting down. Goodbye, Boss."
                if self.announce:
                    self.announce(farewell)
                elif self.tts:
                    try:
                        self.tts.speak(farewell)
                    except Exception:
                        pass
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


__all__ = ["SessionState", "VoiceSession", "TurnLatency"]
