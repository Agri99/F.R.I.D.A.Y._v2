"""STT confidence filtering - never act on nonsense transcripts."""
from __future__ import annotations

from friday.interaction.stt import SpeechRecognizer


class FakeSegment:
    def __init__(self, text, logprob=-0.3, no_speech=0.0, compression=1.0):
        self.text = text
        self.avg_logprob = logprob
        self.no_speech_prob = no_speech
        self.compression_ratio = compression


def _recognizer(segments):
    rec = SpeechRecognizer()
    rec._model = type("FakeModel", (), {"transcribe": lambda self, *a, **k: (iter(segments), None)})()
    return rec


def test_clean_speech_passes_through():
    rec = _recognizer([FakeSegment("open notepad")])
    assert rec.transcribe("x.wav") == "open notepad"


def test_empty_transcript_returns_empty():
    rec = _recognizer([FakeSegment("")])
    assert rec.transcribe("x.wav") == ""


def test_low_confidence_rejected():
    rec = _recognizer([FakeSegment("mmmm nonsense", logprob=-2.5, no_speech=0.8)])
    assert rec.transcribe("x.wav") == ""


def test_high_compression_rejected():
    rec = _recognizer([FakeSegment("aaaaaa", logprob=-1.2, compression=3.0)])
    assert rec.transcribe("x.wav") == ""


def test_confidence_score_is_bounded():
    rec = _recognizer([FakeSegment("hi", logprob=-0.3)])
    rec.transcribe("x.wav")
    assert 0.0 <= rec.context.last_confidence <= 1.0
