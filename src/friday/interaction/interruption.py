"""
src/friday/interaction/interruption.py

WHAT THIS IS FOR:
InterruptionManager — atomic cancellation of the active turn.

Runbook §24:
    speech detected while FRIDAY speaks
        -> InterruptionManager
            - stop playback
            - cancel TTS
            - cancel LLM stream
            - cancel interruptible tool planning
            - increment turn generation
            - start new listening turn

Generation IDs prevent stale results from overwriting a newer turn.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class InterruptionEvent:
    generation_before: int
    generation_after: int
    reason: str
    timestamp: float


class Cancellable:
    """Anything that exposes a ``cancel()`` method to abort in-flight work.

    Used as a marker so the InterruptionManager can fan out cancellations
    uniformly.
    """

    def cancel(self) -> None:  # pragma: no cover - trivial
        raise NotImplementedError


class InterruptionManager:
    """Coordinate cancellation across STT, LLM stream, TTS, and tools.

    Every consumer registers a cancel callback. On ``interrupt()``:
      1. The turn generation is incremented.
      2. Every registered cancel callback runs (in registration order).
      3. Subscribers are notified of the interruption event.
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._callbacks: list[tuple[str, Callable[[int, int], None]]] = []
        self._subscribers: list[Callable[[InterruptionEvent], None]] = []
        self._clock = clock or time.time

    def generation(self) -> int:
        with self._lock:
            return self._generation

    def next_generation(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def register(self, name: str, callback: Callable[[int, int], None]) -> None:
        """Register a cancel callback.

        ``callback(prev_generation, new_generation)`` runs when ``interrupt``
        is called. The callback MUST be idempotent — the manager does not
        guarantee ordering relative to the generation increment.
        """
        with self._lock:
            self._callbacks.append((name, callback))

    def unregister(self, name: str) -> None:
        with self._lock:
            self._callbacks = [(n, cb) for (n, cb) in self._callbacks if n != name]

    def subscribe(self, callback: Callable[[InterruptionEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def is_stale(self, captured_generation: int) -> bool:
        """True if the captured generation no longer matches the active one."""
        with self._lock:
            return captured_generation != self._generation

    def interrupt(self, reason: str = "user_barge_in") -> int:
        """Cancel the current turn and bump the generation. Returns the new gen."""
        with self._lock:
            prev = self._generation
            self._generation += 1
            new = self._generation
            callbacks = list(self._callbacks)
            subscribers = list(self._subscribers)

        for _name, cb in callbacks:
            try:
                cb(prev, new)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                # Defensive: a misbehaving cancel must not stop others.
                pass

        event = InterruptionEvent(
            generation_before=prev,
            generation_after=new,
            reason=reason,
            timestamp=self._clock(),
        )
        for sub in subscribers:
            try:
                sub(event)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                pass
        return new


__all__ = ["InterruptionManager", "InterruptionEvent", "Cancellable"]
