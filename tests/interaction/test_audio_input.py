"""
tests/interaction/test_audio_input.py

WHAT THIS IS FOR:
Unit tests for BoundedAudioQueue and RingAudioBuffer (Runbook §18).
The actual AudioInputStream.start() requires a real microphone + PortAudio
and is exercised in the live Windows test lab, not here.
"""

from __future__ import annotations

import numpy as np
import pytest

from friday.interaction.audio_input import (
    AudioChunk,
    BoundedAudioQueue,
    RingAudioBuffer,
)


def _chunk(samples: int = 160) -> AudioChunk:
    return AudioChunk(
        data=np.zeros(samples, dtype=np.int16),
        timestamp=0.0,
        sample_rate=16000,
    )


class TestBoundedAudioQueue:
    def test_put_and_get(self):
        q = BoundedAudioQueue(max_size=4)
        c = _chunk()
        q.put(c)
        assert q.qsize() == 1
        assert q.get(timeout=0.1) is c

    def test_drops_oldest_when_full(self):
        q = BoundedAudioQueue(max_size=2)
        a, b, c = _chunk(1), _chunk(2), _chunk(3)
        q.put(a)
        q.put(b)
        q.put(c)  # forces drop of a
        out = [q.get(timeout=0.1), q.get(timeout=0.1)]
        assert out[0] is b
        assert out[1] is c

    def test_min_size_validation(self):
        with pytest.raises(ValueError):
            BoundedAudioQueue(max_size=1)


class TestRingAudioBuffer:
    def test_push_and_drain(self):
        buf = RingAudioBuffer(maxlen=4)
        a, b = _chunk(1), _chunk(2)
        buf.push(a)
        buf.push(b)
        assert len(buf) == 2
        drained = buf.drain()
        assert drained == [a, b]
        assert len(buf) == 0

    def test_maxlen(self):
        buf = RingAudioBuffer(maxlen=3)
        chunks = [_chunk(i) for i in range(5)]
        for c in chunks:
            buf.push(c)
        snap = buf.snapshot()
        assert len(snap) == 3
        assert snap == chunks[-3:]

    def test_snapshot_does_not_clear(self):
        buf = RingAudioBuffer(maxlen=4)
        c = _chunk(8)
        buf.push(c)
        _ = buf.snapshot()
        assert len(buf) == 1
