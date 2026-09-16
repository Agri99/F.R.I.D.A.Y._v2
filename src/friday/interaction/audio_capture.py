"""
src/friday/interaction/audio_capture.py

Unified audio capture service (Live Conversation Solution - Phase 1).

Instead of each subsystem (wake word, recording, follow-up, barge-in) independently
opening its own sounddevice.InputStream, this module owns the microphone and distributes
audio frames internally.

Architecture:

    Microphone ──────┬──────── WakeWordDetector
                     │
                     ├──────── VAD
                     │
                     ├──────── STT
                     │
                     └──────── BargeInDetector

One persistent audio capture layer owns the microphone, then distributes audio frames
internally via a FrameQueue.

This avoids the "multiple InputStream" problem and gives a single source of truth
for microphone state.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterator

import numpy as np

from friday.interaction.audio_input import AudioChunk, BoundedAudioQueue, RingAudioBuffer

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False


@dataclass
class AudioCaptureConfig:
    """Configuration for the unified audio capture service."""
    sample_rate: int = 16000
    channels: int = 1
    block_ms: int = 20
    device: int | str | None = None
    queue_max_size: int = 128
    ring_buffer_maxlen: int = 64


class FrameQueue:
    """Thread-safe queue that distributes audio frames to multiple consumers.

    Each consumer (wake word, VAD, STT, barge-in) reads from the same queue.
    Consumers that need to preserve order should use their own internal buffers.
    """

    def __init__(self, max_size: int = 128) -> None:
        self._q: queue.Queue[AudioChunk] = queue.Queue(maxsize=max_size)
        self.dropped = 0

    def put(self, chunk: AudioChunk) -> None:
        try:
            self._q.put_nowait(chunk)
        except queue.Full:
            # Drop oldest to make room
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

    def get_nowait(self) -> AudioChunk:
        return self._q.get_nowait()

    def qsize(self) -> int:
        return self._q.qsize()

    def empty(self) -> bool:
        return self._q.empty()


class AudioCapture:
    """Unified audio capture service.

    Single persistent InputStream that distributes audio frames to all consumers
    (wake word, VAD, STT, barge-in) via a shared FrameQueue.
    """

    def __init__(self, config: AudioCaptureConfig | None = None) -> None:
        self.config = config or AudioCaptureConfig()
        self._stream = None
        self._running = False
        self._lost_device = False
        self._frame_queue = FrameQueue(max_size=self.config.queue_max_size)
        self._ring_buffer = RingAudioBuffer(maxlen=self.config.ring_buffer_maxlen)
        self._listeners: list[Callable[[AudioChunk], None]] = []
        self._lock = threading.Lock()

    @property
    def frame_queue(self) -> FrameQueue:
        """Access the shared frame queue."""
        return self._frame_queue

    @property
    def ring_buffer(self) -> RingAudioBuffer:
        """Access the ring buffer (pre-roll for STT)."""
        return self._ring_buffer

    def add_listener(self, callback: Callable[[AudioChunk], None]) -> None:
        """Add a listener that gets called for every audio frame."""
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[AudioChunk], None]) -> None:
        """Remove a listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _callback(self, indata, _frames, _time_info, _status) -> None:
        """sounddevice callback - runs on a separate thread."""
        if not self._running:
            return
        # Copy out of sounddevice buffer (it's reused)
        chunk = AudioChunk(
            data=np.array(indata, copy=True).reshape(-1).astype(np.int16, copy=False),
            timestamp=time.time(),
            sample_rate=self.config.sample_rate,
        )
        # Distribute to all listeners
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(chunk)
            except Exception:
                pass  # Defensive: a buggy listener must not stop capture
        # Push to queue and ring buffer
        self._frame_queue.put(chunk)
        self._ring_buffer.push(chunk)

    def start(self, retries: int = 3, retry_delay_s: float = 0.25) -> None:
        """Start the unified audio capture."""
        if self._running:
            return
        if not SOUNDDEVICE_AVAILABLE:
            self._lost_device = True
            raise RuntimeError("sounddevice not available")

        # Drain any residual chunks from previous turns
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except Exception:
                break

        last_error: Exception | None = None
        for attempt in range(max(1, retries)):
            self._running = True
            self._lost_device = False
            try:
                self._stream = sd.InputStream(
                    samplerate=self.config.sample_rate,
                    channels=self.config.channels,
                    dtype="int16",
                    blocksize=max(1, int(self.config.sample_rate * self.config.block_ms / 1000)),
                    device=self.config.device,
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
        raise RuntimeError(f"could not open audio capture after {retries} attempts: {last_error}")

    def stop(self) -> None:
        """Stop the audio capture."""
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                self._lost_device = True
            self._stream = None

    def is_running(self) -> bool:
        return self._running

    def device_lost(self) -> bool:
        return self._lost_device

    def iter_chunks(self, timeout: float | None = None) -> Iterator[AudioChunk]:
        """Yield audio chunks from the queue."""
        while self._running:
            try:
                yield self._frame_queue.get(timeout=timeout)
            except queue.Empty:
                continue

    def drain_queue(self) -> list[AudioChunk]:
        """Drain all chunks from the queue."""
        chunks = []
        while True:
            try:
                chunks.append(self._frame_queue.get_nowait())
            except queue.Empty:
                break
        return chunks


# Global audio capture instance
_global_capture: AudioCapture | None = None


def get_audio_capture(config: AudioCaptureConfig | None = None) -> AudioCapture:
    """Get the global audio capture instance (singleton)."""
    global _global_capture
    if _global_capture is None:
        _global_capture = AudioCapture(config)
    return _global_capture


__all__ = [
    "AudioCapture",
    "AudioCaptureConfig",
    "FrameQueue",
    "get_audio_capture",
]