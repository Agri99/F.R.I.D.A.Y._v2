"""
src/friday/interaction/streaming_tts.py

WHAT THIS IS FOR:
Sentence-level streaming TTS.

Runbook §23:
    LLM stream
        -> text segmenter
        -> sentence/clause queue
        -> Piper synthesis
        -> audio playback queue

The wrapper accepts streamed text deltas, accumulates them, and emits
synthesized audio chunks to a sink (e.g. ``sounddevice.OutputStream``)
as soon as a sentence boundary is detected. Cancellation is generation-
aware: when ``cancel()`` is called, in-flight work is dropped and the
playback queue is flushed.

This module is independent of the legacy ``SpeechSynthesizer`` and can
co-exist with it; the legacy class is kept for backward compatibility
while new code wires through ``StreamingTts``.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Protocol

from friday.interaction.segmenter import segment


@dataclass
class TtsAudioChunk:
    """A synthesized PCM chunk ready for playback."""
    audio: bytes
    sample_rate: int
    sentence_index: int
    turn_id: str


class AudioSink(Protocol):
    """Anything that can consume synthesized PCM bytes."""

    def play(self, audio: bytes, sample_rate: int) -> None: ...
    def stop(self) -> None: ...
    def drain(self) -> list: ...


class QueuedAudioSink:
    """Default sink: queues chunks for a consumer thread (or test consumer).

    ``drain()`` is non-blocking and returns whatever is currently queued.
    ``reset()`` clears the stopped flag so the sink can be reused after
    cancellation — required by the persistent-mic pipeline where the same
    sink survives across multiple turns.
    """

    def __init__(self) -> None:
        self._q: queue.Queue[TtsAudioChunk] = queue.Queue()
        self._stopped = False

    def play(self, audio: bytes, sample_rate: int) -> None:
        if self._stopped:
            return
        # Wrapping in a TtsAudioChunk requires turn/sentence context; the
        # higher-level ``StreamingTts`` puts the chunks on the queue itself
        # via ``enqueue``.
        self._q.put(TtsAudioChunk(audio=audio, sample_rate=sample_rate, sentence_index=-1, turn_id=""))

    def enqueue(self, chunk: TtsAudioChunk) -> None:
        if self._stopped:
            return
        self._q.put(chunk)

    def stop(self) -> None:
        self._stopped = True
        # Drain so any consumer wakes up.
        try:
            while not self._q.empty():
                self._q.get_nowait()
        except queue.Empty:
            pass

    def reset(self) -> None:
        """Make the sink reusable after a cancellation.

        Clears the stopped flag and drains any residual chunks so the next
        turn starts with a clean queue.
        """
        self._stopped = False
        try:
            while not self._q.empty():
                self._q.get_nowait()
        except queue.Empty:
            pass

    def drain(self) -> list[TtsAudioChunk]:
        out: list[TtsAudioChunk] = []
        try:
            while True:
                out.append(self._q.get_nowait())
        except queue.Empty:
            pass
        return out

    def qsize(self) -> int:
        return self._q.qsize()


class StreamingAudioConsumer:
    """Consumes audio chunks from a QueuedAudioSink and plays them via sounddevice."""

    def __init__(self, sink: QueuedAudioSink):
        self._sink = sink
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._consume_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _consume_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._sink._q.get(timeout=0.1)
                import sounddevice as sd
                import numpy as np
                audio_int16 = np.frombuffer(chunk.audio, dtype=np.int16)
                sd.play(audio_int16, samplerate=chunk.sample_rate)
                sd.wait()
            except queue.Empty:
                continue
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Audio playback error: %s", e)


class StreamingTts:
    """Streaming text-to-speech with sentence-level granularity.

    Accepts streamed text deltas via ``feed()`` and emits synthesized audio
    through ``sink``. A new ``start()`` call resets internal state and
    bumps the generation ID so stale results from a previous generation
    can be discarded.
    """

    def __init__(
        self,
        synth: Callable[[str], tuple[bytes, int] | None],
        sink: AudioSink | None = None,
    ) -> None:
        self._synth = synth
        self._sink: AudioSink = sink or QueuedAudioSink()
        self._generation = 0
        self._buffer = ""
        self._cancelled = False
        self._sentence_index = 0
        self._first_audio_at: float | None = None
        self._started_at: float | None = None
        self._lock = threading.Lock()
        self._turn_id = ""

    def start(self, turn_id: str | None = None) -> int:
        """Begin a new generation; returns the new generation ID."""
        with self._lock:
            self._generation += 1
            self._buffer = ""
            self._cancelled = False
            self._sentence_index = 0
            self._first_audio_at = None
            self._started_at = time.time()
            self._turn_id = turn_id or f"tts-{int(time.time() * 1000)}"
            # Reset the sink so it accepts new chunks after a prior cancellation.
            if hasattr(self._sink, "reset"):
                self._sink.reset()
            return self._generation

    def feed(self, text_delta: str) -> int:
        """Append a text delta; returns the sentence index of any newly
        emitted audio (0 if none)."""
        if not text_delta:
            return self._sentence_index
        gen_at_entry = self._generation
        with self._lock:
            self._buffer += text_delta
            sentences = segment(self._buffer)
            if not sentences:
                return self._sentence_index
            # Keep the last (possibly incomplete) sentence in the buffer.
            *ready, leftover = sentences
            self._buffer = leftover

        for s in ready:
            if self._generation != gen_at_entry or self._cancelled:
                break
            self._synthesize_and_emit(s)

        return self._sentence_index

    def finish(self) -> int:
        """Flush the buffer; returns the final sentence index."""
        gen_at_entry = self._generation
        with self._lock:
            leftover = self._buffer.strip()
            self._buffer = ""
        if leftover and not self._cancelled and self._generation == gen_at_entry:
            self._synthesize_and_emit(leftover)
        return self._sentence_index

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            self._buffer = ""
            self._generation += 1
        try:
            self._sink.stop()
        except Exception:
            pass

    def generation_id(self) -> int:
        with self._lock:
            return self._generation

    def time_to_first_audio(self) -> float | None:
        with self._lock:
            if self._first_audio_at is None or self._started_at is None:
                return None
            return self._first_audio_at - self._started_at

    @property
    def first_audio_timestamp(self) -> float | None:
        """Absolute wall-clock time when the first audio chunk was emitted."""
        with self._lock:
            return self._first_audio_at

    def _synthesize_and_emit(self, text: str) -> None:
        try:
            result = self._synth(text)
        except Exception:
            return
        if not result:
            return
        audio, sample_rate = result
        if not audio:
            return
        with self._lock:
            if self._cancelled:
                return
            self._sentence_index += 1
            if self._first_audio_at is None:
                self._first_audio_at = time.time()
            sentence_index = self._sentence_index
            turn_id = self._turn_id
        chunk = TtsAudioChunk(
            audio=audio,
            sample_rate=sample_rate,
            sentence_index=sentence_index,
            turn_id=turn_id,
        )
        try:
            if isinstance(self._sink, QueuedAudioSink):
                self._sink.enqueue(chunk)
            else:
                self._sink.play(audio, sample_rate)
        except Exception:
            pass


def iter_llm_deltas_to_text(llm_stream: Iterator) -> Iterator[str]:
    """Adapter that extracts ``text`` from ``ModelDelta``-like objects
    yielded by ``ModelProvider.stream``. Falls back to plain strings.
    """
    for delta in llm_stream:
        if isinstance(delta, str):
            if delta:
                yield delta
            continue
        text = getattr(delta, "text", None)
        if text:
            yield text


__all__ = [
    "StreamingTts",
    "TtsAudioChunk",
    "AudioSink",
    "QueuedAudioSink",
    "StreamingAudioConsumer",
    "iter_llm_deltas_to_text",
]
