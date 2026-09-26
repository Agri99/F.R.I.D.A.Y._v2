"""
src/friday/interaction/audio_input.py

WHAT THIS IS FOR:
Bounded audio capture pipeline for live conversation.

Runbook §18:
    sounddevice callback -> bounded asyncio/thread queue -> ring buffer
        -> VAD -> incremental STT -> PartialTranscript events

The implementation here is dependency-free of asyncio so it runs in any
Python context (including the worker thread used by ``sounddevice``). A
producer thread pushes int16 chunks; consumers (VAD, ring buffer) drain
through ``get_chunk``/``iter_chunks``.

Memory is bounded by ``max_queue_size`` and the ring buffer length; no
unbounded audio queue is permitted.
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterator

import numpy as np


@dataclass
class AudioChunk:
    """A single chunk of int16 mono PCM plus the wall-clock timestamp."""
    data: np.ndarray
    timestamp: float
    sample_rate: int


class BoundedAudioQueue:
    """Thread-safe bounded queue of ``AudioChunk``.

    Backpressure: when the queue is full, the producer drops the *oldest*
    chunk (the live conversation pipeline cares more about now than about
    history — older frames will be re-fed by the ring buffer if needed).
    """

    def __init__(self, max_size: int = 64) -> None:
        if max_size < 2:
            raise ValueError("max_size must be >= 2 to keep producer and consumer from deadlocking")
        self._q: queue.Queue[AudioChunk] = queue.Queue(maxsize=max_size)
        self.dropped = 0

    def put(self, chunk: AudioChunk) -> None:
        try:
            self._q.put_nowait(chunk)
        except queue.Full:
            # Drop oldest to make room.
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(chunk)
            except queue.Full:
                self.dropped += 1

    def get(self, timeout: float | None = None) -> AudioChunk:
        return self._q.get(timeout=timeout)

    def qsize(self) -> int:
        return self._q.qsize()


class RingAudioBuffer:
    """Bounded ring buffer that retains the last ``maxlen`` chunks.

    Used so the STT layer can prepend a short pre-roll before the moment
    speech started (avoids clipping the first syllable).
    """

    def __init__(self, maxlen: int = 8) -> None:
        self._buf: deque[AudioChunk] = deque(maxlen=maxlen)

    def push(self, chunk: AudioChunk) -> None:
        self._buf.append(chunk)

    def drain(self) -> list[AudioChunk]:
        out = list(self._buf)
        self._buf.clear()
        return out

    def snapshot(self) -> list[AudioChunk]:
        return list(self._buf)

    def __len__(self) -> int:
        return len(self._buf)


class AudioInputStream:
    """Capture from ``sounddevice.InputStream`` and feed the bounded queue.

    The stream callback is invoked on a sounddevice-internal thread; we must
    not block. ``on_chunk`` is called for every chunk before it is queued,
    which lets the VAD consume in near-real-time without blocking on the
    queue.

    When ``on_chunk`` returns False, the stream is stopped (used by tests and
    graceful shutdown).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        block_ms: int = 20,
        on_chunk: Callable[[AudioChunk], bool] | None = None,
        device: int | str | None = None,
        queue_max_size: int = 64,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = max(1, int(sample_rate * block_ms / 1000))
        self.on_chunk = on_chunk
        self.device = device
        self.queue = BoundedAudioQueue(max_size=queue_max_size)
        self._stream = None  # sd.InputStream when running
        self._running = False
        self._lost_device = False

    def _callback(self, indata, _frames, _time_info, _status):
        if not self._running:
            return
        if _status:
            # sounddevice flags underflow/overflow/input overflow here.
            # We treat persistent overflow as a signal that the consumer is
            # too slow; just keep going and let the bounded queue absorb.
            pass
        # Always copy out of the sounddevice buffer; it is reused.
        chunk = AudioChunk(
            data=np.array(indata, copy=True).reshape(-1).astype(np.int16, copy=False),
            timestamp=time.time(),
            sample_rate=self.sample_rate,
        )
        keep_going = True
        if self.on_chunk is not None:
            try:
                keep_going = self.on_chunk(chunk)
            except Exception:
                # Defensive: a buggy callback must not stop audio capture.
                keep_going = True
        self.queue.put(chunk)
        if not keep_going:
            self._running = False
            try:
                self._stream.stop()
            except Exception:
                self._lost_device = True

    def start(self, retries: int = 3, retry_delay_s: float = 0.25) -> None:
        """Open the sounddevice input stream.

        Retries with backoff because on Windows WASAPI a second stream on
        the same device can fail with "device busy" immediately after the
        wake-word listener's stream closes. Each retry gives PortAudio a
        moment to release the device.
        """
        if self._running:
            return
        # Drain any residual chunks from previous turns
        while not self.queue._q.empty():
            try:
                self.queue._q.get_nowait()
            except Exception:
                break
        try:
            import sounddevice as sd
        except Exception as e:
            self._lost_device = True
            raise RuntimeError(f"sounddevice not available: {e}")

        # Brief settling delay on Windows WASAPI so any previously closed stream releases cleanly
        time.sleep(0.1)

        last_error: Exception | None = None
        for attempt in range(max(1, retries)):
            self._running = True
            self._lost_device = False
            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype="int16",
                    blocksize=self.block_size,
                    device=self.device,
                    callback=self._callback,
                )
                self._stream.start()
                return
            except Exception as e:
                last_error = e
                self._running = False
                self._lost_device = True
                self._stream = None
                if attempt < retries - 1:
                    time.sleep(retry_delay_s * (attempt + 1))
        raise RuntimeError(f"could not open audio input after {retries} attempts: {last_error}")

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                self._lost_device = True
            self._stream = None

    def iter_chunks(self, timeout: float | None = None) -> Iterator[AudioChunk]:
        while self._running:
            try:
                yield self.queue.get(timeout=timeout)
            except queue.Empty:
                continue

    def is_running(self) -> bool:
        return self._running

    def device_lost(self) -> bool:
        return self._lost_device


__all__ = [
    "AudioChunk",
    "BoundedAudioQueue",
    "RingAudioBuffer",
    "AudioInputStream",
]
