"""
src/friday/interaction/llm_streaming.py

WHAT THIS IS FOR:
True LLM streaming integration (Runbook §10 — Phase V6).

Connects ModelProvider.stream() directly to the TTS pipeline for
real-time text-to-audio streaming. This is the critical piece that
enables FRIDAY to start speaking before the full response is generated.

The key invariant:
    ModelProvider.stream() -> ModelDelta -> Segmenter -> StreamingTts

NOT:
    accumulate full response -> then synthesize
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from friday.models.base import ModelDelta, ModelMessage
from friday.interaction.streaming_tts import StreamingTts
from friday.interaction.segmenter import segment


@dataclass
class StreamingConfig:
    """Configuration for LLM streaming."""
    max_tokens_per_second: float = 50.0  # Rate limiting for TTS
    buffer_timeout_ms: int = 100  # Max time to wait before flushing
    cancel_on_interruption: bool = True


@dataclass
class StreamingMetrics:
    """Metrics for a streaming session."""
    first_token_latency_ms: float | None = None
    first_audio_latency_ms: float | None = None
    total_tokens: int = 0
    total_audio_chunks: int = 0
    cancelled: bool = False
    error: str | None = None


class LlmStreamToTts:
    """Bridges LLM streaming output directly to TTS synthesis.

    This is the core of "true streaming" - it connects ModelProvider.stream()
    directly to StreamingTts, feeding text deltas as they arrive rather than
    waiting for the complete response.

    Usage:
        bridge = LlmStreamToTts(streaming_tts, interruption_manager)
        metrics = bridge.stream(model_provider.stream(messages), generation_id)
    """

    def __init__(
        self,
        streaming_tts: StreamingTts,
        interruption_manager: Any | None = None,
        config: StreamingConfig | None = None,
        on_first_token: Callable[[], None] | None = None,
        on_first_audio: Callable[[], None] | None = None,
    ) -> None:
        self.tts = streaming_tts
        self.interruption = interruption_manager
        self.config = config or StreamingConfig()
        self._lock = threading.Lock()
        self._cancelled = False
        self._generation = 0
        self._on_first_token = on_first_token
        self._on_first_audio = on_first_audio

    def stream(
        self,
        llm_stream: Iterator[ModelDelta],
        generation_id: int | None = None,
    ) -> StreamingMetrics:
        """Stream LLM deltas to TTS.

        Args:
            llm_stream: Iterator yielding ModelDelta objects
            generation_id: Current generation ID for staleness checks

        Returns:
            StreamingMetrics with latency and count information
        """
        metrics = StreamingMetrics()
        start_time = time.time()
        first_token_time = None
        first_audio_time = None
        token_count = 0

        # Start TTS generation
        turn_id = f"stream-{int(start_time * 1000)}"
        tts_gen = self.tts.start(turn_id=turn_id)

        try:
            for delta in llm_stream:
                # Check for cancellation
                if self._should_cancel(generation_id):
                    metrics.cancelled = True
                    self.tts.cancel()
                    break

                # Extract text
                text = None
                if isinstance(delta, str):
                    text = delta
                elif hasattr(delta, 'text'):
                    text = delta.text

                if not text:
                    continue

                # Track first token
                if first_token_time is None:
                    first_token_time = time.time()
                    metrics.first_token_latency_ms = (first_token_time - start_time) * 1000
                    if self._on_first_token:
                        self._on_first_token()

                token_count += len(text.split())

                # Feed to TTS
                self.tts.feed(text)

                # Check if we have first audio
                if first_audio_time is None and self.tts.first_audio_timestamp:
                    first_audio_time = self.tts.first_audio_timestamp
                    metrics.first_audio_latency_ms = (first_audio_time - start_time) * 1000
                    if self._on_first_audio:
                        self._on_first_audio()

            # Finalize TTS (flush any remaining buffer)
            if not metrics.cancelled:
                self.tts.finish()

        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            metrics.error = str(e)

        metrics.total_tokens = token_count
        metrics.total_audio_chunks = self.tts.generation_id() - tts_gen if tts_gen else 0

        return metrics

    def cancel(self) -> None:
        """Cancel the streaming session."""
        with self._lock:
            self._cancelled = True
        self.tts.cancel()

    def _should_cancel(self, generation_id: int | None) -> bool:
        """Check if we should cancel based on generation or interruption."""
        with self._lock:
            if self._cancelled:
                return True

        if self.interruption is None:
            return False

        if generation_id is not None:
            return self.interruption.is_stale(generation_id)

        return False


def stream_llm_to_tts(
    model_provider: Any,
    messages: list[ModelMessage],
    streaming_tts: StreamingTts,
    interruption_manager: Any | None = None,
    tools: list[dict] | None = None,
) -> StreamingMetrics:
    """Convenience function to stream from model to TTS.

    Usage:
        metrics = stream_llm_to_tts(
            model_provider=router.get("fast"),
            messages=[ModelMessage(role="user", content="Hello")],
            streaming_tts=tts,
        )
    """
    bridge = LlmStreamToTts(streaming_tts, interruption_manager)

    # Get the stream iterator
    stream = model_provider.stream(messages, tools=tools)

    return bridge.stream(stream)


class AccumulatingAdapter:
    """Adapter for model providers that don't support true streaming.

    Some providers may return the full response at once. This adapter
    breaks it into sentence-level chunks to simulate streaming for the
    TTS pipeline, preserving the same interface.

    This is NOT ideal - real streaming is preferred - but it allows
    graceful degradation.
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self._emitted = False

    def __iter__(self) -> Iterator[ModelDelta]:
        if self._emitted:
            return

        # Break text into sentences
        sentences = segment(self._text)

        for sentence in sentences:
            if sentence.strip():
                yield ModelDelta(text=sentence + " ")

        self._emitted = True


__all__ = [
    "LlmStreamToTts",
    "StreamingConfig",
    "StreamingMetrics",
    "stream_llm_to_tts",
    "AccumulatingAdapter",
]
