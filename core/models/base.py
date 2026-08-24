"""
core/models/base.py

WHAT THIS IS FOR:
Defines the CONTRACT every model backend must satisfy. The rest of
FRIDAY (orchestrator, skills, memory) talks to `ModelProvider`, never
to "Qwen3" or "Ollama" directly.

WHY IT'S BUILT THIS WAY (Principle E — Model portability):
If you swap Qwen3 8B for a bigger model on better hardware, or add a
cloud fallback later, you edit `default.yaml` and maybe write one new
provider class. You never touch the orchestrator, the tool registry,
or the skill engine. That's the whole point of this file existing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ModelMessage:
    role: str          # "system" | "user" | "assistant" | "tool"
    content: str


@dataclass
class ModelResponse:
    text: str
    tool_calls: list[dict] = field(default_factory=list)
    raw: dict | None = None


class ModelProvider(ABC):
    """Every backend (Ollama, a future cloud fallback, a test stub) implements this."""

    @abstractmethod
    def generate(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
    ) -> ModelResponse:
        """Send messages (+ optional tool schemas) and get a response back."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap health check. Used at startup and before routing a task."""
        raise NotImplementedError
