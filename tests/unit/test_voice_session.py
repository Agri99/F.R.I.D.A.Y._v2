from __future__ import annotations

from dataclasses import dataclass

from friday.interaction.session import SessionState, VoiceSession


class FakeSTT:
    def __init__(self, transcripts: list[str], followups: list[str | None]):
        self.transcripts = iter(transcripts)
        self.followups = iter(followups)

    def record_until_silence(self):
        return "initial.wav"

    def transcribe(self, path):
        return next(self.transcripts)

    def listen_for_followup(self, timeout_seconds):
        return next(self.followups)


class FakeWake:
    def __init__(self):
        self.calls = 0

    def listen_for_wakeword(self):
        self.calls += 1


@dataclass
class SpeechResult:
    interrupted: bool = False


class FakeTTS:
    def __init__(self, interrupt: bool = False):
        self.spoken: list[str] = []
        self.interrupt = interrupt
        self.cancelled = False

    def speak_interruptible(self, text, wakeword, on_interrupt=None):
        self.spoken.append(text)
        if self.interrupt and on_interrupt:
            on_interrupt()
        return SpeechResult(self.interrupt)

    def cancel(self):
        self.cancelled = True


def test_voice_session_preserves_followup_turns():
    stt = FakeSTT(["first question", "follow up"], ["followup.wav", None])
    tts = FakeTTS()
    wake = FakeWake()
    calls = []
    states = []
    session = VoiceSession(stt, tts, wake, lambda text: calls.append(text) or f"answer: {text}", on_state_change=states.append)

    response = session.run_once()

    assert calls == ["first question", "follow up"]
    assert tts.spoken == ["answer: first question", "answer: follow up"]
    assert response == "answer: follow up"
    assert SessionState.FOLLOWUP_LISTENING in states
    assert session.state == SessionState.IDLE


def test_barge_in_invalidates_turn_and_cancels_tts():
    stt = FakeSTT(["do something"], [None])
    tts = FakeTTS(interrupt=True)
    session = VoiceSession(stt, tts, FakeWake(), lambda text: "planned action")

    assert session.run_once() is None
    assert tts.cancelled
    assert session.state == SessionState.INTERRUPTED


def test_runtime_control_does_not_reach_agent():
    stt = FakeSTT(["go offline"], [None])
    called = []
    agent_calls = []
    session = VoiceSession(
        stt,
        FakeTTS(),
        FakeWake(),
        lambda text: agent_calls.append(text),
        controls={"offline": lambda: called.append("offline")},
    )

    session.run_once()

    assert called == ["offline"]
    assert agent_calls == []
