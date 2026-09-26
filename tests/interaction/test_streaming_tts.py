"""
tests/interaction/test_streaming_tts.py

WHAT THIS IS FOR:
Unit tests for StreamingTts (Runbook §23).
"""

from __future__ import annotations


from friday.interaction.streaming_tts import (
    QueuedAudioSink,
    StreamingTts,
    iter_llm_deltas_to_text,
)


def _synth(side_effect):
    """Build a synth callable returning canned audio per sentence."""
    counter = {"i": 0}

    def _call(text: str):
        idx = counter["i"]
        counter["i"] += 1
        return side_effect(text, idx)

    return _call


class TestStreamingTts:
    def test_single_sentence_emits_one_chunk(self):
        sink = QueuedAudioSink()
        synth = _synth(lambda text, idx: (b"audio-bytes", 22050))
        tts = StreamingTts(synth=synth, sink=sink)
        tts.start()
        tts.feed("Hello there.")
        tts.finish()
        chunks = sink.drain()
        assert len(chunks) == 1
        assert chunks[0].audio == b"audio-bytes"
        assert chunks[0].sample_rate == 22050
        assert chunks[0].sentence_index == 1
        assert tts.time_to_first_audio() is not None

    def test_multiple_sentences_emit_in_order(self):
        sink = QueuedAudioSink()
        synth = _synth(lambda text, idx: (f"audio-{idx}".encode(), 22050))
        tts = StreamingTts(synth=synth, sink=sink)
        tts.start()
        tts.feed("First sentence. Second sentence.")
        tts.finish()
        chunks = sink.drain()
        assert len(chunks) == 2
        assert chunks[0].audio == b"audio-0"
        assert chunks[1].audio == b"audio-1"

    def test_cancel_discards_buffered_text(self):
        sink = QueuedAudioSink()
        synth = _synth(lambda text, idx: (b"x", 22050))
        tts = StreamingTts(synth=synth, sink=sink)
        tts.start()
        tts.feed("First sentence.")
        tts.cancel()
        tts.feed("This should be discarded because generation moved on.")
        tts.finish()
        chunks = sink.drain()
        assert len(chunks) == 0

    def test_generation_increments_on_restart(self):
        sink = QueuedAudioSink()
        synth = _synth(lambda text, idx: (b"x", 22050))
        tts = StreamingTts(synth=synth, sink=sink)
        gen1 = tts.start()
        gen2 = tts.start()
        assert gen2 > gen1

    def test_stale_results_dropped(self):
        """After cancel(), a stale synth that finishes must not enqueue."""
        sink = QueuedAudioSink()
        events: list[bool] = []
        tts_generation_at_synth_entry: list[int] = []
        tts_gen = {"v": 0}

        def synth(text):
            tts_generation_at_synth_entry.append(tts_gen["v"])
            # Simulate slow synth: caller cancels before this returns.
            return None

        tts = StreamingTts(synth=synth, sink=sink)
        tts_gen["v"] = tts.start()
        tts.feed("Long sentence.")
        tts.cancel()
        tts.finish()
        assert sink.qsize() == 0

    def test_finish_drains_leftover(self):
        sink = QueuedAudioSink()
        synth = _synth(lambda text, idx: (f"x{idx}".encode(), 22050))
        tts = StreamingTts(synth=synth, sink=sink)
        tts.start()
        tts.feed("Hello there how are you doing")  # No sentence boundary yet
        tts.finish()
        chunks = sink.drain()
        assert len(chunks) == 1
        assert chunks[0].audio == b"x0"

    def test_iter_llm_deltas_to_text(self):
        class Delta:
            def __init__(self, t):
                self.text = t

        deltas = [Delta("Hello"), Delta(", world"), "."]
        text = "".join(iter_llm_deltas_to_text(deltas))
        assert text == "Hello, world."

    def test_iter_llm_deltas_accepts_plain_strings(self):
        assert list(iter_llm_deltas_to_text(["a", "", "b"])) == ["a", "b"]
