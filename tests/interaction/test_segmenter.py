"""
tests/interaction/test_segmenter.py

WHAT THIS IS FOR:
Unit tests for the sentence/clause segmenter (Runbook §23).
"""

from __future__ import annotations

from friday.interaction.segmenter import iter_sentences, segment, split_into_clauses


class TestSegmenter:
    def test_empty_input(self):
        assert segment("") == []
        assert segment("   ") == []
        assert list(iter_sentences("")) == []

    def test_single_sentence(self):
        assert segment("Hello there.") == ["Hello there."]

    def test_multiple_sentences(self):
        out = segment("Hello there. How are you? I am fine!")
        assert out == ["Hello there.", "How are you?", "I am fine!"]

    def test_short_sentences_concatenated(self):
        # "Hi." (3 chars) is shorter than min_length=8 so the segmenter
        # concatenates it with the next sentence. That's the intended
        # behaviour for streaming TTS: avoid sending tiny fragments.
        out = segment("Hi. How are you today?")
        assert len(out) == 1
        assert "Hi." in out[0]
        assert "How are you today?" in out[0]

    def test_clause_split(self):
        out = split_into_clauses("Open Chrome, then VS Code, and finally Terminal")
        assert len(out) == 3

    def test_clause_no_delimiter(self):
        out = split_into_clauses("Open Chrome")
        assert out == ["Open Chrome"]

    def test_iter_sentences_yields(self):
        # "First." is shorter than min_length=8 so it merges with "Second.".
        text = "First. Second. Third."
        out = list(iter_sentences(text))
        assert len(out) == 2
        assert "First." in out[0]
        assert "Third." in out[1]
