"""Text-to-speech module using Piper with barge-in, streaming, and state management."""
from __future__ import annotations
import re
import time
import threading
import numpy as np
import sounddevice as sd
from typing import Any, Callable, Optional
from enum import Enum
from dataclasses import dataclass
from friday.interaction.stt import VoiceState


def _strip_markdown(text: str) -> str:
    """Removes common markdown formatting for TTS reading."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    return text


@dataclass
class TTSResult:
    """Result of TTS synthesis and playback."""
    success: bool
    interrupted: bool = False
    duration_seconds: float = 0.0
    error: str | None = None


class SpeechSynthesizer:
    """Synthesizes speech from text using Piper with barge-in and streaming support."""

    def __init__(self, model_path: str = "models/en_GB-jenny_dioco-medium.onnx"):
        from piper import PiperVoice
        self.voice = PiperVoice.load(model_path)
        self._state_callback: Callable[[VoiceState], None] | None = None
        self._interrupt_event = threading.Event()
        self._current_audio: np.ndarray | None = None

    def set_state_callback(self, callback: Callable[[VoiceState], None]):
        """Set callback for voice state changes."""
        self._state_callback = callback

    def _set_state(self, state: VoiceState):
        if self._state_callback:
            self._state_callback(state)

    def _build_audio(self, text: str) -> np.ndarray:
        text = _strip_markdown(text)
        audio_chunks = [np.frombuffer(c.audio_int16_bytes, dtype=np.int16) for c in self.voice.synthesize(text)]
        if not audio_chunks:
            return np.zeros(0, dtype=np.int16)
        audio = np.concatenate(audio_chunks)
        padding_start = np.zeros(int(0.15 * self.voice.config.sample_rate), dtype=np.int16)
        padding_end = np.zeros(int(0.60 * self.voice.config.sample_rate), dtype=np.int16)
        return np.concatenate([padding_start, audio, padding_end])

    def speak(self, text: str) -> TTSResult:
        """Speak text synchronously with state management. This is the reliable baseline."""
        self._interrupt_event.clear()
        audio = self._build_audio(text)
        if len(audio) == 0:
            return TTSResult(success=True, duration_seconds=0)

        self._set_state(VoiceState.SPEAKING)
        self._current_audio = audio

        try:
            sd.play(audio, samplerate=self.voice.config.sample_rate)
            start_time = time.time()
            sd.wait()
            duration = time.time() - start_time
            return TTSResult(success=True, duration_seconds=duration)
        except Exception as exc:
            # Log the error for debugging
            import logging
            logging.getLogger(__name__).exception("TTS playback failed")
            return TTSResult(success=False, error=str(exc))
        finally:
            self._current_audio = None
            self._set_state(VoiceState.IDLE)

    def speak_interruptible(self, text: str, wakeword_listener: Any = None,
                            playback_gain: float = 0.6, on_interrupt: Callable[[], None] | None = None) -> TTSResult:
        """Speak text with optional barge-in. Barge-in is best-effort and non-critical.

        If barge-in monitoring fails, we fall back to simple speak() to ensure
        the user hears the response. Barge-in is best-effort, not required.

        Returns:
            TTSResult with success=True if speech completed (interrupted or not),
            success=False only if TTS synthesis/playback completely failed.
        """
        self._interrupt_event.clear()
        audio = self._build_audio(text)
        if len(audio) == 0:
            return TTSResult(success=True, duration_seconds=0)

        self._set_state(VoiceState.SPEAKING)
        self._current_audio = audio

        # Apply gain
        audio = (audio.astype(np.float32) * playback_gain).astype(np.int16)
        duration = len(audio) / self.voice.config.sample_rate

        # Reset wakeword listener if provided
        if wakeword_listener and hasattr(wakeword_listener, 'model') and hasattr(wakeword_listener.model, 'reset'):
            wakeword_listener.model.reset()

        sd.play(audio, samplerate=self.voice.config.sample_rate)
        start_time = time.time()
        interrupted = False
        playback_failed = False

        # Try barge-in monitoring, but don't let it block the critical path
        barge_in_failed = False
        try:
            with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1280) as stream:
                warmup_frames = 5
                frame_count = 0

                while time.time() - start_time < duration:
                    # Check for external interrupt
                    if self._interrupt_event.is_set():
                        interrupted = True
                        break

                    frame_count += 1
                    if frame_count <= warmup_frames:
                        stream.read(1280)
                        continue

                    # Check for wake word barge-in (best effort)
                    if wakeword_listener and hasattr(wakeword_listener, 'check_frame'):
                        try:
                            if wakeword_listener.check_frame(stream, debug=False):
                                interrupted = True
                                break
                        except Exception:
                            # Barge-in monitoring failed - continue without it
                            pass

                    if not interrupted:
                        # Small sleep to prevent busy loop
                        time.sleep(0.01)

                if not interrupted:
                    # Wait for remaining playback
                    remaining = duration - (time.time() - start_time)
                    if remaining > 0:
                        time.sleep(remaining)

        except Exception as e:
            # Barge-in monitoring failed - fall back to simple playback
            import logging
            logging.getLogger(__name__).warning("Barge-in monitoring failed, falling back to simple playback: %s", e)
            # Wait for playback to complete
            remaining = duration - (time.time() - start_time)
            if remaining > 0:
                time.sleep(remaining)
            barge_in_failed = True

        finally:
            sd.stop()
            self._current_audio = None
            if interrupted:
                self._set_state(VoiceState.INTERRUPTED)
                if on_interrupt:
                    on_interrupt()
            else:
                self._set_state(VoiceState.IDLE)

        actual_duration = time.time() - start_time
        # Return success=True even if barge-in failed, as long as playback succeeded
        return TTSResult(success=True, interrupted=interrupted, duration_seconds=time.time() - start_time)

    def cancel(self):
        """Cancel current TTS playback immediately."""
        self._interrupt_event.set()
        if self._current_audio is not None:
            sd.stop()
            self._current_audio = None
            self._set_state(VoiceState.IDLE)

    def get_state(self) -> VoiceState:
        """Get current TTS state."""
        if self._current_audio is not None:
            return VoiceState.SPEAKING
        return VoiceState.IDLE
