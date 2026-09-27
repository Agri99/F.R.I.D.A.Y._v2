"""
src/friday/observability/events.py

WHAT THIS IS FOR:
Event tracking and observability bus (Runbook §79).
"""
import time
from typing import Any, Callable
from dataclasses import dataclass, field
import threading


@dataclass
class ObservabilityEvent:
    name: str
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.subscribers = []
        return cls._instance

    def subscribe(self, callback: Callable[[ObservabilityEvent], None]):
        self.subscribers.append(callback)

    def publish(self, name: str, **kwargs):
        event = ObservabilityEvent(name=name, data=kwargs)
        for sub in self.subscribers:
            try:
                sub(event)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                pass


def track_event(name: str, **kwargs):
    """Global helper to emit an observability event."""
    EventBus().publish(name, **kwargs)

