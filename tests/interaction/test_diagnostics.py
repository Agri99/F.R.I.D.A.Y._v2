"""
tests/interaction/test_diagnostics.py

WHAT THIS IS FOR:
Tests for the voice diagnostic pipeline (Live Conversation Solution - Phase 3).
Platform-independent: mocks the microphone and audio devices.
"""

from __future__ import annotations



from friday.interaction.diagnostics import (
    VoiceDiagnostics,
    VoiceDiagnosticState,
)


class FakeSTT:
    """Stand-in for SpeechRecognizer."""
    def __init__(self, transcript: str = "hello friday"):
        self._transcript = transcript

    def transcribe(self, audio_file: str) -> str:
        return self._transcript

    def record_until_silence(self, path: str = "data/audio.wav") -> str:
        return path


class FakeTTS:
    """Stand-in for SpeechSynthesizer."""
    def __init__(self, success: bool = True, duration: float = 0.5):
        self.success = success
        self.duration = duration
        self.spoken: list[str] = []

    def speak(self, text: str):
        self.spoken.append(text)
        from friday.interaction.tts import TTSResult
        return TTSResult(
            success=self.success,
            duration_seconds=self.duration
        )


class FakeAgent:
    """Stand-in for the orchestrator."""
    def __init__(self, response: str = "The current time is 10:30 AM."):
        self._response = response
        self.calls: list[str] = []

    def __call__(self, query: str) -> str:
        self.calls.append(query)
        return self._response


class TestVoiceDiagnosticState:
    def test_add_result(self):
        state = VoiceDiagnosticState()
        state.add_result("test1", True, "Test passed")
        assert state.results["test1"]["passed"] is True
        assert state.results["test1"]["message"] == "Test passed"

    def test_add_warning(self):
        state = VoiceDiagnosticState()
        state.add_warning("Low RMS")
        assert "Low RMS" in state.warnings

    def test_summary(self):
        state = VoiceDiagnosticState()
        state.add_result("test1", True, "Pass")
        state.add_result("test2", False, "Fail")
        summary = state.summary()
        assert summary["total_tests"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1


class TestVoiceDiagnostics:
    def test_test_speaker_success(self):
        tts = FakeTTS(success=True, duration=0.5)
        diagnostics = VoiceDiagnostics()
        result = diagnostics.test_speaker(tts, "Hello, I am FRIDAY.")
        assert result is True
        assert diagnostics.state.results["speaker"]["passed"] is True

    def test_test_speaker_failure(self):
        tts = FakeTTS(success=False)
        diagnostics = VoiceDiagnostics()
        result = diagnostics.test_speaker(tts, "Hello, I am FRIDAY.")
        assert result is False
        assert diagnostics.state.results["speaker"]["passed"] is False

    def test_test_agent_success(self):
        agent = FakeAgent()
        diagnostics = VoiceDiagnostics()
        result = diagnostics.test_agent(agent, "what time is it?")
        assert result is True
        assert diagnostics.state.results["agent"]["passed"] is True
        assert "what time is it?" in agent.calls

    def test_test_agent_failure(self):
        def bad_agent(query):
            raise RuntimeError("Agent crashed")
        diagnostics = VoiceDiagnostics()
        result = diagnostics.test_agent(bad_agent, "what time is it?")
        assert result is False
        assert diagnostics.state.results["agent"]["passed"] is False

    def test_run_diagnostics_convenience(self):
        stt = FakeSTT()
        tts = FakeTTS(success=True, duration=0.5)
        agent = FakeAgent()
        diagnostics = VoiceDiagnostics()
        result = diagnostics.run_all_diagnostics(stt, tts, agent)
        assert "speaker" in result["results"]
        assert "agent" in result["results"]
        # Speaker test should pass
        assert result["results"]["speaker"]["passed"] is True
        # Agent test should pass
        assert result["results"]["agent"]["passed"] is True
