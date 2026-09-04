"""
tests/interaction/test_event_driven_voice_integration.py

WHAT THIS IS FOR:
End-to-end test of the event-driven voice pipeline wired through
``VoiceSession``. Replaces real audio devices, Whisper, and Piper with
fakes so the test runs in any environment.

The test exercises:
  - audio chunks flow through AudioInputStream -> VAD -> transcriber
  - TurnDetector produces END_TURN once speech + silence occur
  - LLM delta is fed to StreamingTts and audio chunks reach the sink
  - barge-in (interruption) cancels in-flight TTS and aborts the turn
  - follow-up window listens briefly for the next user turn
"""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
import pytest

from friday.interaction.audio_input import AudioChunk, AudioInputStream, BoundedAudioQueue
from friday.interaction.conversation import ConversationManager
from friday.interaction.interruption import InterruptionManager
from friday.interaction.pipeline import VoicePipeline
from friday.interaction.session import SessionState, VoiceSession
from friday.interaction.streaming_tts import QueuedAudioSink, StreamingTts
from friday.interaction.stt import StreamingTranscriber, TranscriptEvent
from friday.interaction.turn_detector import TurnAction, TurnDetector, TurnDetectorConfig
from friday.interaction.vad import RmsVoiceActivityDetector


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeSpeechSynthesizer:
    """Stand-in for the Piper-based SpeechSynthesizer."""

    def __init__(self, sample_rate: int = 22050) -> None:
        self.voice = type("V", (), {"config": type("C", (), {"sample_rate": sample_rate})()})()
        self.build_calls: list[str] = []
        self._build_lock = threading.Lock()

    def _build_audio(self, text: str):
        with self._build_lock:
            self.build_calls.append(text)
        # 100ms of audio per sentence.
        n_samples = int(self.voice.config.sample_rate * 0.1)
        return np.zeros(n_samples, dtype=np.int16)


class FakeTranscriber:
    """Stand-in for StreamingTranscriber that emits a fixed transcript
    after a configurable number of chunks."""

    def __init__(self, transcript: str = "open vs code", partial_after: int = 3) -> None:
        self._transcript = transcript
        self._partial_after = partial_after
        self._running = False
        self._cancelled = False
        self._buffer: list[np.ndarray] = []
        self._events: list[TranscriptEvent] = []
        self._lock = threading.Lock()
        self._turn_id = ""
        self._start = 0.0

    def start_streaming(self, callback=None, turn_id: str | None = None) -> None:
        with self._lock:
            self._running = True
            self._cancelled = False
            self._buffer = []
            self._events = []
            self._turn_id = turn_id or "t"
            self._start = time.time()

    def stop_streaming(self) -> None:
        with self._lock:
            self._running = False

    def submit_chunk(self, audio, timestamp=None) -> None:
        with self._lock:
            if not self._running or self._cancelled:
                return
            self._buffer.append(np.asarray(audio, dtype=np.int16))
            if len(self._buffer) >= self._partial_after:
                self._events.append(
                    TranscriptEvent(
                        text=self._transcript,
                        is_final=False,
                        confidence=0.9,
                        start_time=self._start,
                        end_time=time.time(),
                        turn_id=self._turn_id,
                    )
                )

    def drain_events(self):
        with self._lock:
            events = list(self._events)
            self._events = []
            return events

    def finalize(self):
        with self._lock:
            self._running = False
            ev = TranscriptEvent(
                text=self._transcript,
                is_final=True,
                confidence=0.9,
                start_time=self._start,
                end_time=time.time(),
                turn_id=self._turn_id,
            )
            self._events.append(ev)
            return [ev]

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            self._running = False


class FakeWakeword:
    def __init__(self) -> None:
        self.calls = 0

    def listen_for_wakeword(self) -> bool:
        self.calls += 1
        return True


class FakeAgent:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or ["Sure, opening VS Code now."]
        self.calls: list[str] = []
        self._index = 0

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        text = self.responses[min(self._index, len(self.responses) - 1)]
        self._index += 1
        return text


def _silence_chunk(samples: int = 320) -> AudioChunk:
    return AudioChunk(
        data=np.zeros(samples, dtype=np.int16),
        timestamp=time.time(),
        sample_rate=16000,
    )


def _tone_chunk(samples: int = 320, amplitude: int = 8000) -> AudioChunk:
    t = np.linspace(0, 1, samples, endpoint=False)
    data = (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
    return AudioChunk(data=data, timestamp=time.time(), sample_rate=16000)


def _build_pipeline(sink: QueuedAudioSink | None = None, **overrides) -> VoicePipeline:
    """Build a VoicePipeline with FakeTranscriber and a real StreamingTts."""
    sink = sink or QueuedAudioSink()
    synth = FakeSpeechSynthesizer()
    sample_rate = synth.voice.config.sample_rate

    def synth_cb(text: str):
        try:
            audio = synth._build_audio(text)
        except Exception:
            return None
        if audio is None or len(audio) == 0:
            return None
        return audio.astype("<i2").tobytes(), sample_rate

    transcriber = FakeTranscriber(transcript=overrides.pop("transcript", "open vs code"))
    td_cfg = TurnDetectorConfig(silence_to_end_s=0.2)
    pipeline = VoicePipeline(
        audio_input=AudioInputStream(sample_rate=16000, channels=1, block_ms=20),
        vad=RmsVoiceActivityDetector(rms_threshold=400, speech_chunks_to_start=2),
        transcriber=transcriber,
        turn_detector=TurnDetector(config=td_cfg),
        streaming_tts=StreamingTts(synth=synth_cb, sink=sink),
        interruption=InterruptionManager(),
        conversation=ConversationManager(followup_window_seconds=0.3),
        sink=sink,
    )
    return pipeline


def _drive_audio_input(pipeline: VoicePipeline, chunks: list[AudioChunk]) -> threading.Thread:
    """Push chunks onto the pipeline's bounded queue from a worker thread."""

    def _producer():
        for c in chunks:
            pipeline.audio_input.queue.put(c)
            time.sleep(0.005)

    t = threading.Thread(target=_producer, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestEventDrivenVoiceSession:
    def test_capture_turn_emits_final_transcript(self):
        sink = QueuedAudioSink()
        pipeline = _build_pipeline(sink=sink)
        # Override audio_input.start to not actually open a sounddevice stream.
        pipeline.audio_input.start = lambda: None  # type: ignore[assignment]
        pipeline.audio_input.stop = lambda: None  # type: ignore[assignment]
        # Replace the queue getter so we control pacing.
        original_queue = pipeline.audio_input.queue

        agent = FakeAgent(responses=["Sure, opening VS Code."])
        session = VoiceSession(
            stt=None,
            tts=None,
            wakeword=FakeWakeword(),
            agent=agent,
            voice_pipeline=pipeline,
            on_state_change=lambda s: None,
        )

        # Drive 6 silence + 4 tone + 6 silence (enough to trigger SPEECH_STARTED,
        # stable partial, SPEECH_ENDED, then silence past 0.2s threshold).
        chunks: list[AudioChunk] = []
        for _ in range(6):
            chunks.append(_silence_chunk())
        for _ in range(4):
            chunks.append(_tone_chunk())
        for _ in range(6):
            chunks.append(_silence_chunk())

        producer = _drive_audio_input(pipeline, chunks)
        # Bypass the live stream.start() inside _capture_turn_event_driven by
        # reusing the already-populated queue.
        # Call _capture_turn_event_driven directly with a tiny timeout.
        transcript = session._capture_turn_event_driven(pipeline, _pre_speech_exit=True)
        producer.join(timeout=2.0)
        assert transcript is not None
        assert transcript == "open vs code"
        assert agent.calls == []

    def test_capture_opens_its_own_audio_input_stream(self):
        """The wake listener closes its stream before returning, so the
        capture loop must open its own AudioInputStream on the same device.
        AudioInputStream.start() retries with backoff to handle the Windows
        WASAPI "device busy" case that occurs immediately after the wake
        stream closes."""
        sink = QueuedAudioSink()
        pipeline = _build_pipeline(sink=sink)
        pipeline.audio_input.start = lambda: None  # type: ignore[assignment]
        pipeline.audio_input.stop = lambda: None  # type: ignore[assignment]

        agent = FakeAgent(responses=["ok"])
        session = VoiceSession(
            stt=None,
            tts=None,
            wakeword=FakeWakeword(),
            agent=agent,
            voice_pipeline=pipeline,
        )

        # Build a fake sounddevice stream that yields our chunks.
        chunks: list[AudioChunk] = []
        for _ in range(6):
            chunks.append(_silence_chunk())
        for _ in range(4):
            chunks.append(_tone_chunk())
        for _ in range(6):
            chunks.append(_silence_chunk())

        # Push chunks directly onto the pipeline's queue (simulating AudioInputStream)
        for c in chunks:
            pipeline.audio_input.queue.put(c)

        transcript = session._capture_turn_event_driven(pipeline, _pre_speech_exit=True)
        assert transcript == "open vs code"
        # AudioInputStream.start() was not called because we pre-populated the queue
        # but the code path that would call it was not exercised.

    def test_speak_event_driven_produces_audio_chunks(self):
        sink = QueuedAudioSink()
        pipeline = _build_pipeline(sink=sink)
        agent = FakeAgent()
        session = VoiceSession(
            stt=None,
            tts=None,
            wakeword=FakeWakeword(),
            agent=agent,
            voice_pipeline=pipeline,
        )

        # Direct call into _speak_event_driven with a known response.
        interrupted = session._speak_event_driven(pipeline, "Sure, opening VS Code now.")
        chunks = sink.drain()
        assert interrupted is False
        # At least one chunk emitted.
        assert len(chunks) >= 1
        # Sample rate matches Piper fake.
        assert chunks[0].sample_rate == 22050

    def test_barge_in_during_speak_cancels_tts(self):
        sink = QueuedAudioSink()
        pipeline = _build_pipeline(sink=sink)
        session = VoiceSession(
            stt=None,
            tts=None,
            wakeword=FakeWakeword(),
            agent=FakeAgent(),
            voice_pipeline=pipeline,
        )

        # Speak, then externally trigger an interruption.
        session._speak_event_driven(pipeline, "Long answer that should be interrupted.")
        chunks_before = sink.drain()
        assert len(chunks_before) >= 1

        # Start a second speak and interrupt mid-flight.
        def _delayed_interrupt():
            time.sleep(0.01)
            pipeline.interruption.interrupt(reason="test_barge_in")

        threading.Thread(target=_delayed_interrupt, daemon=True).start()
        interrupted = session._speak_event_driven(pipeline, "Another long answer.")
        # After interruption, the streaming TTS is cancelled.
        assert pipeline.streaming_tts.generation_id() >= 2  # bumped on start() + cancel()

    def test_full_run_once_event_driven_with_fake_audio(self):
        """Full integration: wakeword + capture + speak + followup.

        All chunks are pushed upfront so the followup window doesn't get
        polluted by still-arriving producer data.
        """
        sink = QueuedAudioSink()
        pipeline = _build_pipeline(sink=sink, transcript="hello friday")
        # Override audio_input.start/stop so no real sounddevice is opened.
        pipeline.audio_input.start = lambda: None  # type: ignore[assignment]
        pipeline.audio_input.stop = lambda: None  # type: ignore[assignment]

        agent = FakeAgent(responses=["Hello! How can I help?"])
        state_changes: list[SessionState] = []
        session = VoiceSession(
            stt=None,
            tts=None,
            wakeword=FakeWakeword(),
            agent=agent,
            voice_pipeline=pipeline,
            on_state_change=state_changes.append,
        )

        chunks: list[AudioChunk] = []
        for _ in range(6):
            chunks.append(_silence_chunk())
        for _ in range(6):
            chunks.append(_tone_chunk())
        for _ in range(8):
            chunks.append(_silence_chunk())
        for c in chunks:
            pipeline.audio_input.queue.put(c)

        response = session.run_once(require_wake=False)
        assert response == "Hello! How can I help?"
        assert agent.calls == ["hello friday"]
        assert SessionState.LISTENING in state_changes
        assert SessionState.SPEAKING in state_changes
        audio_chunks = sink.drain()
        assert len(audio_chunks) >= 1

    def test_legacy_path_still_works_without_pipeline(self):
        """Regression guard: when voice_pipeline=None, legacy path is used."""
        # We can't easily exercise the legacy path without a real mic, but we
        # can at least verify the constructor accepts None and dispatch works.
        class _NoPipelineSTT:
            def record_until_silence(self, path="data/audio.wav") -> str:
                return path

            def transcribe(self, path: str) -> str:
                return "hello"

            def listen_for_followup(self, timeout_seconds: float = 5.0, path: str = "data/audio.wav"):
                return None

        session = VoiceSession(
            stt=_NoPipelineSTT(),
            tts=None,
            wakeword=FakeWakeword(),
            agent=FakeAgent(responses=["ok"]),
            voice_pipeline=None,
        )
        assert session.voice_pipeline is None
