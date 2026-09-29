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


def test_language_chain_english_priority():
    from friday.interaction.stt import resolve_language_chain
    # English gets priority when its prob is >= 0.25 even if another language is slightly higher
    probs = [("id", 0.40), ("en", 0.35), ("su", 0.10)]
    assert resolve_language_chain(probs) == "en"

    # English within 0.20 of top
    probs_close = [("es", 0.45), ("en", 0.28)]
    assert resolve_language_chain(probs_close) == "en"


def test_language_chain_indonesian_fallback():
    from friday.interaction.stt import resolve_language_chain
    # When English is negligible, Indonesian is picked
    probs = [("id", 0.60), ("en", 0.05), ("su", 0.15)]
    assert resolve_language_chain(probs) == "id"


def test_language_chain_sundanese_fallback():
    from friday.interaction.stt import resolve_language_chain
    # When English and Indonesian are low, Sundanese is picked
    probs = [("su", 0.55), ("id", 0.10), ("en", 0.05)]
    assert resolve_language_chain(probs) == "su"


def test_language_chain_other_languages():
    from friday.interaction.stt import resolve_language_chain
    # Confident non-chain language
    probs = [("ja", 0.85), ("en", 0.05)]
    assert resolve_language_chain(probs) == "ja"

    # Low confidence across the board defaults to English
    probs_low = [("fr", 0.20), ("de", 0.15)]
    assert resolve_language_chain(probs_low) == "en"


def test_speech_recognizer_detects_language():
    from friday.interaction.stt import SpeechRecognizer

    calls = []

    class MockModel:
        def detect_language(self, audio):
            return "id", 0.70, [("id", 0.70), ("en", 0.05)]

        def transcribe(self, audio, language, initial_prompt, **kwargs):
            calls.append((language, initial_prompt))
            return iter([FakeSegment("Buka kalkulator")]), None

    rec = SpeechRecognizer(language="auto")
    rec._model = MockModel()
    text = rec.transcribe("dummy.wav")
    assert text == "Buka kalkulator"
    assert len(calls) == 1
    assert calls[0][0] == "id"
    assert "asisten komputer" in calls[0][1]

