"""
src/friday/models/base.py

WHAT THIS IS FOR:
Defines the CONTRACT every model backend must satisfy. The rest of
FRIDAY (orchestrator, skills, memory) talks to `ModelProvider`, never
to a specific backend directly.

WHY IT'S BUILT THIS WAY (Principle E — Model portability):
Provides a clean abstraction over local, remote, and cloud models, allowing
routing, streaming, and tool use without coupling to an API structure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator


class ModelFormat(str, Enum):
    GGUF = "GGUF"
    SAFETENSORS = "SAFETENSORS"
    ONNX = "ONNX"
    REMOTE = "REMOTE"


class Quantization(str, Enum):
    Q4_K_M = "Q4_K_M"
    Q5_K_M = "Q5_K_M"
    Q6_K = "Q6_K"
    FP16 = "FP16"
    BF16 = "BF16"


@dataclass(frozen=True)
class ModelSpec:
    family: str
    parameters_billions: float
    format: ModelFormat
    quantization: Quantization
    runtime: str
    context_length: int
    role: str
    model_id: str = ""

    @property
    def estimated_memory_gb(self) -> float:
        bits_per_weight = {
            Quantization.Q4_K_M: 4.5,
            Quantization.Q5_K_M: 5.5,
            Quantization.Q6_K: 6.5,
            Quantization.FP16: 16.0,
            Quantization.BF16: 16.0,
        }[self.quantization]
        weights = self.parameters_billions * bits_per_weight / 8.0
        return round(weights * 1.15, 2)


@dataclass
class ProviderHealth:
    available: bool
    model_loaded: bool
    latency_ms: float | None = None


@dataclass
class ModelDelta:
    text: str
    tool_calls: list[dict] | None = None


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
    """Every backend implements this protocol."""

    @abstractmethod
    def generate(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
        images: list[str] | None = None,
    ) -> ModelResponse:
        """Send messages (+ optional tool schemas and vision images) and get a response back."""
        raise NotImplementedError

    @abstractmethod
    def stream(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
    ) -> Iterator[ModelDelta]:
        """Stream chunks of the response."""
        raise NotImplementedError

    @abstractmethod
    def supports_tools(self) -> bool:
        """Whether this provider supports structured tool calling."""
        raise NotImplementedError

    @abstractmethod
    def supports_vision(self) -> bool:
        """Whether this provider supports vision/image inputs."""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Detailed health check for the provider and model."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Quick check if the provider is healthy/available."""
        try:
            return self.health().available
        except Exception:
            return False

