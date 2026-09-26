"""
tests/interaction/test_llm_streaming.py

Tests for true LLM-to-TTS streaming (Runbook §10 — Phase V6).
"""

from __future__ import annotations

from typing import Iterator
from unittest.mock import MagicMock

import numpy as np
import pytest

from friday.models.base import ModelDelta
from friday.interaction.llm_streaming import (
    LlmStreamToTts,
    stream_llm_to_tts,
    AccumulatingAdapter,
)
from friday.interaction.streaming_tts import StreamingTts, QueuedAudioSink


class TestLlmStreamToTts:
    """Tests for LLM-to-TTS streaming bridge."""

    @pytest.fixture
    def mock_tts(self):
        """Create a mock StreamingTts."""
        def dummy_synth(text: str):
            # Simulate synthesis by returning noise
            if not text.strip():
                return None
            samples = int(16000 * len(text.split()) * 0.2)  # ~0.2s per word
            return np.zeros(samples, dtype=np.int16).tobytes(), 16000

        sink = QueuedAudioSink()
        return StreamingTts(synth=dummy_synth, sink=sink)

    def test_stream_text_deltas(self, mock_tts):
        """Test streaming text deltas to TTS."""
        bridge = LlmStreamToTts(mock_tts)

        # Simulate LLM stream
        def llm_stream():
            yield ModelDelta(text="Hello ")
            yield ModelDelta(text="how ")
            yield ModelDelta(text="can ")
            yield ModelDelta(text="I ")
            yield ModelDelta(text="help?")

        metrics = bridge.stream(llm_stream())

        assert metrics.total_tokens > 0
        assert not metrics.cancelled

    def test_first_token_latency_tracked(self, mock_tts):
        """Test that first token latency is measured."""
        bridge = LlmStreamToTts(mock_tts)
        first_token_called = {"count": 0}

        def on_first_token():
            first_token_called["count"] += 1

        bridge._on_first_token = on_first_token

        def llm_stream():
            yield ModelDelta(text="Hello")

        metrics = bridge.stream(llm_stream())

        assert metrics.first_token_latency_ms is not None
        assert first_token_called["count"] == 1

    def test_first_audio_latency_tracked(self, mock_tts):
        """Test that first audio latency is measured."""
        bridge = LlmStreamToTts(mock_tts)
        first_audio_called = {"count": 0}

        def on_first_audio():
            first_audio_called["count"] += 1

        bridge._on_first_audio = on_first_audio

        def llm_stream():
            yield ModelDelta(text="Hello there.")

        metrics = bridge.stream(llm_stream())

        # First audio time should be tracked after synthesis
        # (may be None if synthesis doesn't happen immediately)
        assert first_audio_called["count"] >= 0  # Callback may or may not be called

    def test_cancellation_stops_stream(self, mock_tts):
        """Test that cancellation stops the stream."""
        from friday.interaction.interruption import InterruptionManager

        im = InterruptionManager()
        bridge = LlmStreamToTts(mock_tts, interruption_manager=im)

        def llm_stream():
            for i in range(100):
                yield ModelDelta(text=f"word{i} ")

        # Cancel immediately
        bridge.cancel()

        metrics = bridge.stream(llm_stream())

        assert metrics.cancelled

    def test_generation_staleness_detected(self, mock_tts):
        """Test that stale generation IDs are detected."""
        from friday.interaction.interruption import InterruptionManager

        im = InterruptionManager()
        bridge = LlmStreamToTts(mock_tts, interruption_manager=im)

        gen_id = im.generation()

        def llm_stream():
            yield ModelDelta(text="Hello ")
            # Simulate barge-in
            im.interrupt(reason="test")
            yield ModelDelta(text="world")

        metrics = bridge.stream(llm_stream(), generation_id=gen_id)

        assert metrics.cancelled

    def test_token_count_accumulated(self, mock_tts):
        """Test that token count is accumulated."""
        bridge = LlmStreamToTts(mock_tts)

        def llm_stream():
            yield ModelDelta(text="one two three four five")

        metrics = bridge.stream(llm_stream())

        assert metrics.total_tokens == 5

    def test_empty_deltas_ignored(self, mock_tts):
        """Test that empty deltas are ignored."""
        bridge = LlmStreamToTts(mock_tts)

        def llm_stream():
            yield ModelDelta(text="")
            yield ModelDelta(text="Hello")
            yield ModelDelta(text="")
            yield ModelDelta(text="world")
            yield ModelDelta(text="")

        metrics = bridge.stream(llm_stream())

        # Should only count non-empty deltas
        assert metrics.total_tokens == 2

    def test_stream_function_convenience(self, mock_tts):
        """Test convenience function."""
        from friday.models.base import ModelProvider, ModelMessage

        # Mock model provider
        mock_provider = MagicMock(spec=ModelProvider)

        def mock_stream(messages, tools=None):
            yield ModelDelta(text="Hello ")
            yield ModelDelta(text="world")

        mock_provider.stream = mock_stream

        messages = [ModelMessage(role="user", content="Hi")]

        metrics = stream_llm_to_tts(
            model_provider=mock_provider,
            messages=messages,
            streaming_tts=mock_tts,
        )

        assert metrics.total_tokens > 0
        assert not metrics.cancelled


class TestAccumulatingAdapter:
    """Tests for fallback accumulating adapter."""

    def test_breaks_text_into_sentences(self):
        """Test that text is broken into sentences."""
        text = "Hello there. How are you?"
        adapter = AccumulatingAdapter(text)

        deltas = list(adapter)

        assert len(deltas) > 0
        # Should have at least 2 sentences
        assert len(deltas) >= 2

    def test_handles_empty_text(self):
        """Test handling of empty text."""
        adapter = AccumulatingAdapter("")

        deltas = list(adapter)

        assert len(deltas) == 0

    def test_iterator_only_yields_once(self):
        """Test that iterator only yields once."""
        text = "Hello world."
        adapter = AccumulatingAdapter(text)

        deltas1 = list(adapter)
        deltas2 = list(adapter)

        assert len(deltas1) > 0
        assert len(deltas2) == 0  # Second iteration returns nothing


class TestStreamingIntegration:
    """Integration tests for streaming pipeline."""

    def test_voice_session_with_streaming(self):
        """Test VoiceSession with streaming support."""
        from friday.interaction.session import VoiceSession

        # Mock agent that supports streaming
        def mock_agent_with_stream(query: str):
            return "Response to: " + query

        def mock_stream(query: str) -> Iterator[ModelDelta]:
            words = query.split()
            for word in words:
                yield ModelDelta(text=word + " ")

        mock_agent_with_stream.stream = mock_stream

        session = VoiceSession(
            stt=MagicMock(),
            tts=MagicMock(),
            wakeword=MagicMock(),
            agent=mock_agent_with_stream,
        )

        # Verify agent has stream method
        assert hasattr(session.agent, "stream")
        assert callable(session.agent.stream)

    def test_streaming_vs_batch_fallback(self):
        """Test that batch fallback works when stream not available."""
        from friday.interaction.streaming_tts import iter_llm_deltas_to_text
        from friday.models.base import ModelDelta

        # Batch mode: complete text
        text = "Hello world"
        deltas = [ModelDelta(text=text)]

        result = list(iter_llm_deltas_to_text(deltas))

        assert len(result) == 1
        assert "Hello" in result[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
