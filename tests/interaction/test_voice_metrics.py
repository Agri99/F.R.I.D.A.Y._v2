"""
tests/interaction/test_voice_metrics.py

WHAT THIS IS FOR:
Unit tests for VoiceMetrics (Runbook §79 — voice).
"""

from __future__ import annotations

from friday.observability.voice_metrics import VoiceMetrics, get_voice_metrics


class TestVoiceMetrics:
    def test_record_and_read(self):
        m = VoiceMetrics()
        m.record("stt_latency_ms", 120.0, turn_id="t1")
        m.record("stt_latency_ms", 90.0, turn_id="t2")
        samples = m.samples("stt_latency_ms")
        assert len(samples) == 2
        assert samples[-1].value_ms == 90.0
        assert samples[-1].turn_id == "t2"

    def test_average(self):
        m = VoiceMetrics()
        m.record("barge_in_latency_ms", 100.0)
        m.record("barge_in_latency_ms", 200.0)
        assert m.average_ms("barge_in_latency_ms") == 150.0

    def test_latest(self):
        m = VoiceMetrics()
        assert m.latest("missing") is None
        m.record("wake_latency_ms", 50.0)
        m.record("wake_latency_ms", 75.0)
        latest = m.latest("wake_latency_ms")
        assert latest is not None
        assert latest.value_ms == 75.0

    def test_listener(self):
        m = VoiceMetrics()
        received: list = []
        m.add_listener(lambda s: received.append(s))
        m.record("time_to_first_audio_ms", 250.0)
        assert len(received) == 1

    def test_global_singleton(self):
        a = get_voice_metrics()
        b = get_voice_metrics()
        assert a is b
