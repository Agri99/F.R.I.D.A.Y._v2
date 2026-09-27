"""
src/friday/models/registry.py

WHAT THIS IS FOR:
Central registry of all known model definitions. Each entry carries the
metadata needed for the router to choose the best candidate and for the
provisioner to download/verify it.

Runbook §11, §45, §46, §47.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ModelEntry:
    """One registered model with its full capability metadata."""
    id: str
    provider: str
    role: str
    model: str
    tools: bool = False
    vision: bool = False
    streaming: bool = True
    quantization: str = "Q4_K_M"
    context_length: int = 8192
    ram_estimate_gb: float = 0.0
    vram_estimate_gb: float = 0.0
    source_url: str = ""
    sha256: str = ""
    license: str = ""
    languages: list = field(default_factory=lambda: ["en"])
    installed: bool = False
    health: str = "UNKNOWN"
    benchmark: dict = field(default_factory=dict)


class ModelRegistry:
    """Thread-safe model registry backed by optional JSON persistence."""

    def __init__(self, entries=None):
        self._lock = threading.Lock()
        self._entries: dict[str, ModelEntry] = {}
        for e in (entries or []):
            self._entries[e.id] = e

    def register(self, entry: ModelEntry) -> None:
        with self._lock:
            self._entries[entry.id] = entry

    def get(self, model_id: str):
        with self._lock:
            return self._entries.get(model_id)

    def all(self):
        with self._lock:
            return list(self._entries.values())

    def by_role(self, role: str):
        with self._lock:
            candidates = [e for e in self._entries.values() if e.role == role]
        candidates.sort(key=lambda e: (not e.installed, e.health != "HEALTHY", e.ram_estimate_gb))
        return candidates

    def best_for_role(self, role: str):
        for e in self.by_role(role):
            if e.installed and e.health in ("HEALTHY", "UNKNOWN"):
                return e
        return None

    def update_health(self, model_id: str, health: str) -> None:
        with self._lock:
            if model_id in self._entries:
                self._entries[model_id].health = health

    def update_benchmark(self, model_id: str, results: dict) -> None:
        with self._lock:
            if model_id in self._entries:
                self._entries[model_id].benchmark.update(results)

    def mark_installed(self, model_id: str, installed: bool = True) -> None:
        with self._lock:
            if model_id in self._entries:
                self._entries[model_id].installed = installed

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = [asdict(e) for e in self._entries.values()]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "ModelRegistry":
        path = Path(path)
        entries = []
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                for item in raw:
                    try:
                        entries.append(ModelEntry(**item))
                    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                        pass
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                pass
        if not entries:
            entries = _default_entries()
        return cls(entries)


def _default_entries():
    return [
        ModelEntry(id="qwen3:4b-q4_k_m", provider="ollama", role="fast",
                   model="qwen3:4b", tools=True, streaming=True,
                   quantization="Q4_K_M", context_length=32768, ram_estimate_gb=3.5, license="Apache-2.0"),
        ModelEntry(id="qwen3:8b-q4_k_m", provider="ollama", role="reasoning",
                   model="qwen3:8b", tools=True, streaming=True,
                   quantization="Q4_K_M", context_length=32768, ram_estimate_gb=6.0, license="Apache-2.0"),
        ModelEntry(id="qwen3-vl:8b-q4_k_m", provider="ollama", role="vision",
                   model="qwen3-vl:8b", tools=True, vision=True, streaming=True,
                   quantization="Q4_K_M", context_length=32768, ram_estimate_gb=8.0, license="Apache-2.0"),
    ]


__all__ = ["ModelEntry", "ModelRegistry"]
