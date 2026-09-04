"""
tests/interaction/test_interruption.py

WHAT THIS IS FOR:
Unit tests for InterruptionManager (Runbook §24).
"""

from __future__ import annotations

from friday.interaction.interruption import InterruptionManager


class TestInterruptionManager:
    def test_initial_generation_is_zero(self):
        m = InterruptionManager()
        assert m.generation() == 0

    def test_interrupt_increments_generation(self):
        m = InterruptionManager()
        prev = m.generation()
        new = m.interrupt(reason="test")
        assert new == prev + 1
        assert m.is_stale(prev) is True

    def test_is_stale_returns_false_for_current(self):
        m = InterruptionManager()
        m.interrupt()
        current = m.generation()
        assert m.is_stale(current) is False

    def test_registered_callback_runs(self):
        m = InterruptionManager()
        calls: list[tuple[int, int]] = []
        m.register("stt", lambda p, n: calls.append((p, n)))
        m.interrupt(reason="barge_in")
        assert calls == [(0, 1)]

    def test_faulty_callback_does_not_break_others(self):
        m = InterruptionManager()
        calls: list[int] = []

        def bad(_p, _n):
            raise RuntimeError("boom")

        m.register("bad", bad)
        m.register("good", lambda _p, _n: calls.append(1))
        m.interrupt()
        assert calls == [1]

    def test_subscribe_receives_event(self):
        m = InterruptionManager()
        events: list = []
        m.subscribe(lambda e: events.append(e))
        m.interrupt(reason="wake_word")
        assert len(events) == 1
        assert events[0].reason == "wake_word"
        assert events[0].generation_after > events[0].generation_before

    def test_unregister(self):
        m = InterruptionManager()
        calls: list[int] = []
        m.register("stt", lambda _p, _n: calls.append(1))
        m.unregister("stt")
        m.interrupt()
        assert calls == []
