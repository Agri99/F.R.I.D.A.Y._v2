"""
src/friday/observability/voice_metrics.py

WHAT THIS IS FOR:
Voice-pipeline metrics — Runbook §79 (Voice section).

Captured metrics:
    wake_latency_ms          — wake-word detection to first response frame
    stt_latency_ms           — audio end to transcript ready
    time_to_first_audio_ms   — agent start to first synthesized audio
    barge_in_latency_ms      — user speech detected during TTS to playback stopped
    turn_duration_ms         — turn begin to turn end
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VoiceMetricSample:
    """A single metric sample."""
    name: str
    value_ms: float
    timestamp: float
    turn_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class VoiceMetrics:
    """Thread-safe voice metric collector.

    Keeps the last ``max_samples`` for each metric so callers can read
    averages, percentiles, or the most recent value. Long-term storage is
    out of scope (the runbook §79 leaves that to whatever the platform
    observability backend is).
    """

    def __init__(self, max_samples: int = 256) -> None:
        self._lock = threading.Lock()
        self._max = max(16, int(max_samples))
        self._buckets: dict[str, deque[VoiceMetricSample]] = {}
        self._listeners: list[Any] = []

    def record(
        self,
        name: str,
        value_ms: float,
        turn_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        sample = VoiceMetricSample(
            name=name,
            value_ms=float(value_ms),
            timestamp=time.time(),
            turn_id=turn_id,
            extra=dict(extra) if extra else {},
        )
        with self._lock:
            bucket = self._buckets.setdefault(name, deque(maxlen=self._max))
            bucket.append(sample)
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(sample)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                pass

    def add_listener(self, callback: Any) -> None:
        with self._lock:
            self._listeners.append(callback)

    def samples(self, name: str) -> list[VoiceMetricSample]:
        with self._lock:
            return list(self._buckets.get(name, ()))

    def latest(self, name: str) -> VoiceMetricSample | None:
        with self._lock:
            bucket = self._buckets.get(name)
            if not bucket:
                return None
            return bucket[-1]

    def average_ms(self, name: str) -> float | None:
        with self._lock:
            bucket = self._buckets.get(name)
            if not bucket:
                return None
            return sum(s.value_ms for s in bucket) / len(bucket)


_global = VoiceMetrics()


def get_voice_metrics() -> VoiceMetrics:
    return _global


__all__ = ["VoiceMetrics", "VoiceMetricSample", "get_voice_metrics"]
