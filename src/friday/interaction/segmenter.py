"""
src/friday/interaction/segmenter.py

WHAT THIS IS FOR:
Sentence/clause segmentation for sentence-level streaming TTS.

Runbook §23 — LLM stream -> text segmenter -> sentence/clause queue ->
Piper synthesis -> audio playback queue. The segmenter is intentionally
lightweight and deterministic so the first sentence can be synthesized
before the LLM has finished generating the response.
"""

from __future__ import annotations

import re
from typing import Iterator

# Sentence-final punctuation. Keep the regex conservative so abbreviations
# like "e.g." or "U.S." don't fragment sentences unintentionally; we accept
# the rare false split in exchange for low-latency TTS start.
_END_PUNCT = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_PUNCT = re.compile(r"(?<=[,;:])\s+")

# Minimum characters before we consider a sentence ready to flush — this
# avoids sending "Hi" then "." then " " as three separate sentences.
_MIN_SENTENCE_LEN = 8


def segment(text: str, min_length: int = _MIN_SENTENCE_LEN) -> list[str]:
    """Split text into sentences suitable for streaming TTS.

    Empty / whitespace-only input returns an empty list. Sentences shorter
    than ``min_length`` are concatenated with the next sentence when possible.
    """
    if not text:
        return []
    text = text.strip()
    if not text:
        return []
    pieces = _END_PUNCT.split(text)
    sentences: list[str] = []
    pending = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if pending and len(pending) < min_length:
            pending = (pending + " " + piece).strip()
        else:
            if pending:
                sentences.append(pending)
            pending = piece
    if pending:
        sentences.append(pending)
    return sentences


def iter_sentences(text: str, min_length: int = _MIN_SENTENCE_LEN) -> Iterator[str]:
    """Yield sentences from ``text`` as they become available."""
    for s in segment(text, min_length=min_length):
        yield s


def split_into_clauses(sentence: str) -> list[str]:
    """Split a sentence on commas/semicolons/colons for fine-grained streaming.

    Returns the input unchanged if there are no clause boundaries.
    """
    if not sentence or "," not in sentence and ";" not in sentence and ":" not in sentence:
        return [sentence]
    parts = _CLAUSE_PUNCT.split(sentence)
    return [p.strip() for p in parts if p.strip()]


__all__ = ["segment", "iter_sentences", "split_into_clauses"]
