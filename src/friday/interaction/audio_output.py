"""
src/friday/interaction/audio_output.py

WHAT THIS IS FOR:
Reusable audio output service (Runbook §12 — Phase V8).

A persistent audio sink that supports:
  - play(audio, sample_rate)
  - flush_generation() — cancel current generation only
  - stop() — full stop
  - pause() / resume()
  - device_info()

The sink survives across turns. Cancellation clears only the current
generation, not the entire service — the next response must still play.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False


@dataclass
class AudioOutputConfig:
    """Configuration for the audio output service."""
    sample_rate: int = 22050
    device: int | str | None = None
    queue_max_size: int = 64


@dataclass
class PlaybackChunk:
    """A chunk of audio to play."""
    audio: np.ndarray
    sample_rate: int
    generation: int
    on_done: Callable[[], None] | None = None


class AudioOutputService:
    """Reusable audio output service with generation-aware cancellation.

    The service owns a single OutputStream and plays audio from a bounded
    queue. Each chunk carries a generation ID; when flush_generation() is
    called, chunks from older generations are dropped without stopping
    the service itself.
    """

    def __init__(self, config: AudioOutputConfig | None = None) -> None:
        self.config = config or AudioOutputConfig()
        self._queue: queue.Queue[PlaybackChunk | None] = queue.Queue(
            maxsize=self.config.queue_max_size
        )
        self._stream = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._paused = False
        self._generation = 0
        self._current_generation = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._playback_done = threading.Event()
        self._device_lost = False

    def start(self) -> None:
        """Start the audio output service."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the audio output service completely."""
        self._running = False
        self._stop_event.set()
        # Send sentinel to wake up the thread
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._close_stream()

    def pause(self) -> None:
        """Pause playback."""
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        """Resume playback."""
        with self._lock:
            self._paused = False

    def play(
        self,
        audio: bytes | np.ndarray,
        sample_rate: int,
        generation: int | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> bool:
        """Queue audio for playback.

        Args:
            audio: PCM bytes (int16) or numpy array
            sample_rate: Sample rate of the audio
            generation: Generation ID for cancellation (default: current)
            on_done: Callback when playback completes

        Returns:
            True if queued successfully, False if queue is full
        """
        if isinstance(audio, bytes):
            audio_arr = np.frombuffer(audio, dtype=np.int16)
        else:
            audio_arr = np.asarray(audio, dtype=np.int16)

        if audio_arr.size == 0:
            return True

        gen = generation if generation is not None else self._generation

        chunk = PlaybackChunk(
            audio=audio_arr,
            sample_rate=sample_rate,
            generation=gen,
            on_done=on_done,
        )

        try:
            self._queue.put_nowait(chunk)
            return True
        except queue.Full:
            return False

    def flush_generation(self) -> None:
        """Cancel the current generation's audio.

        Removes all queued chunks from the current generation without
        stopping the service. The next generation's audio will still play.
        """
        with self._lock:
            self._generation += 1

        # Drain old chunks from queue
        new_queue: list[PlaybackChunk] = []
        while True:
            try:
                item = self._queue.get_nowait()
                if item is None:
                    new_queue.append(None)
                    break
                if item.generation > self._generation:
                    new_queue.append(item)
            except queue.Empty:
                break

        # Re-queue valid chunks
        for item in new_queue:
            if item is None:
                continue
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                pass

        # Stop current stream if playing old generation
        self._close_stream()

    def cancel(self) -> None:
        """Alias for flush_generation for API compatibility."""
        self.flush_generation()

    def generation_id(self) -> int:
        """Get the current generation ID."""
        with self._lock:
            return self._generation

    def device_info(self) -> dict[str, Any]:
        """Get information about the output device."""
        if not SOUNDDEVICE_AVAILABLE:
            return {"available": False, "error": "sounddevice not installed"}

        try:
            devices = sd.query_devices()
            default_output = sd.default.device[1] if sd.default.device else None

            if self.config.device is not None:
                dev = sd.query_devices(self.config.device)
                return {
                    "available": True,
                    "name": dev.get("name", "unknown"),
                    "default": False,
                    "channels": dev.get("max_output_channels", 0),
                    "sample_rate": dev.get("default_samplerate", 0),
                }

            if default_output is not None:
                dev = sd.query_devices(default_output)
                return {
                    "available": True,
                    "name": dev.get("name", "unknown"),
                    "default": True,
                    "channels": dev.get("max_output_channels", 0),
                    "sample_rate": dev.get("default_samplerate", 0),
                }

            return {"available": False, "error": "no output device found"}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def is_running(self) -> bool:
        return self._running

    def device_lost(self) -> bool:
        return self._device_lost

    def _playback_loop(self) -> None:
        """Main playback loop running in a background thread."""
        while self._running and not self._stop_event.is_set():
            try:
                chunk = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if chunk is None:
                continue

            # Check if chunk is from a stale generation
            with self._lock:
                if chunk.generation < self._generation:
                    continue
                self._current_generation = chunk.generation

            # Check for pause
            while self._paused and self._running:
                time.sleep(0.05)

            if not self._running:
                break

            # Play the chunk
            self._play_chunk_blocking(chunk)

            if chunk.on_done:
                try:
                    chunk.on_done()
                except Exception:
                    pass

    def _play_chunk_blocking(self, chunk: PlaybackChunk) -> None:
        """Play a single chunk, blocking until done."""
        if not SOUNDDEVICE_AVAILABLE:
            return

        try:
            sd.play(chunk.audio, samplerate=chunk.sample_rate, device=self.config.device)
            sd.wait()
        except Exception as e:
            self._device_lost = True

    def _close_stream(self) -> None:
        """Close any open output stream."""
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
        except Exception:
            self._device_lost = True


class AudioOutputAdapter:
    """Adapter that makes AudioOutputService compatible with AudioSink protocol."""

    def __init__(self, service: AudioOutputService) -> None:
        self._service = service

    def play(self, audio: bytes, sample_rate: int) -> None:
        gen = self._service.generation_id()
        self._service.play(audio, sample_rate, generation=gen)

    def stop(self) -> None:
        self._service.flush_generation()

    def drain(self) -> list:
        """Compatibility method — not used in streaming mode."""
        return []


__all__ = [
    "AudioOutputService",
    "AudioOutputConfig",
    "AudioOutputAdapter",
    "PlaybackChunk",
]
