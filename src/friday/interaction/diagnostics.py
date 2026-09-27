"""
src/friday/interaction/diagnostics.py

WHAT THIS IS FOR:
Voice diagnostic pipeline (Live Conversation Solution - Phase 3).

Before touching "true live conversation", FRIDAY needs this sequence to work:

Test 1 -- Speaker
    hard-coded "Hello, I am FRIDAY."
        --> Chatterbox Turbo
        --> speaker

Test 2 -- Microphone
    Record audio and inspect: sample count, duration, RMS, peak, input device

Test 3 -- STT
    Use an existing WAV: audio.wav --> Whisper --> "hello friday"

Test 4 -- Agent
    "what time is it?" --> agent --> text response (no voice)

Test 5 -- Full voice
    microphone --> record --> STT --> agent --> TTS --> speaker
"""

from __future__ import annotations

import os
import time
import numpy as np
from typing import Any, Callable

# Voice state tracking
class VoiceDiagnosticState:
    """Track diagnostic test results for debugging."""
    def __init__(self):
        self.results = {}
        self.errors = []
        self.warnings = []

    def add_result(self, test_name: str, passed: bool, message: str, details: dict = None):
        self.results[test_name] = {
            "passed": passed,
            "message": message,
            "details": details or {}
        }
        if not passed:
            self.errors.append(f"{test_name}: {message}")

    def add_warning(self, message: str):
        self.warnings.append(message)

    def summary(self) -> dict:
        return {
            "total_tests": len(self.results),
            "passed": sum(1 for r in self.results.values() if r["passed"]),
            "failed": sum(1 for r in self.results.values() if not r["passed"]),
            "errors": self.errors,
            "warnings": self.warnings,
            "results": self.results
        }


class VoiceDiagnostics:
    """Voice diagnostic pipeline for debugging and validation."""

    def __init__(self):
        self.state = VoiceDiagnosticState()

    def test_speaker(self, synthesizer: Any, text: str = "Hello, I am FRIDAY.") -> bool:
        """Test 1: Speaker - verify TTS works and can play audio."""
        print(f"[DIAGNOSTICS] Test 1: Speaker - speaking '{text}'")
        try:
            result = synthesizer.speak(text)
            if hasattr(result, 'success'):
                if result.success:
                    self.state.add_result("speaker", True, f"Speaker test passed: {result.duration_seconds:.2f}s", {
                        "duration": result.duration_seconds
                    })
                    return True
                else:
                    self.state.add_result("speaker", False, f"Speaker test failed: {result.error}")
                    return False
            else:
                # For legacy TTS that doesn't return a result
                self.state.add_result("speaker", True, "Speaker test passed (legacy TTS)")
                return True
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            self.state.add_result("speaker", False, f"Speaker test exception: {e}")
            return False

    def test_microphone(self, stt: Any, test_file: str = "data/test_mic.wav", duration: float = 2.0) -> bool:
        """Test 2: Microphone - record audio and inspect it."""
        print(f"[DIAGNOSTICS] Test 2: Microphone - recording {duration}s")
        try:
            # Use the existing record_until_silence but with a shorter duration
            import sounddevice as sd
            import soundfile as sf

            # Create directory if needed
            os.makedirs(os.path.dirname(test_file), exist_ok=True)

            # Record audio
            audio_data = []
            sample_rate = 16000
            with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16") as stream:
                start_time = time.time()
                while time.time() - start_time < duration:
                    chunk, _ = stream.read(int(sample_rate * 0.1))  # 100ms chunks
                    audio_data.append(chunk.flatten())

            if not audio_data:
                self.state.add_result("microphone", False, "No audio data recorded")
                return False

            audio = np.concatenate(audio_data)

            # Analyze the recording
            rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
            peak = np.max(np.abs(audio))
            duration_actual = len(audio) / sample_rate

            self.state.add_result("microphone", True, "Microphone test passed", {
                "duration": duration_actual,
                "rms": float(rms),
                "peak": int(peak),
                "samples": len(audio),
                "sample_rate": sample_rate
            })

            # Save the recording for analysis
            sf.write(test_file, audio, sample_rate)

            # Check if the recording contains meaningful audio (not just silence)
            if rms < 100:
                self.state.add_warning(f"Very low RMS ({rms:.1f}) - possible microphone issue")
            if peak < 500:
                self.state.add_warning(f"Very low peak ({peak}) - possible microphone issue")

            return True
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            self.state.add_result("microphone", False, f"Microphone test exception: {e}")
            return False

    def test_stt(self, stt: Any, audio_file: str = "data/test_audio.wav") -> bool:
        """Test 3: STT - transcribe a known audio file."""
        print(f"[DIAGNOSTICS] Test 3: STT - transcribing {audio_file}")
        try:
            if not os.path.exists(audio_file):
                self.state.add_result("stt", False, f"Audio file not found: {audio_file}")
                return False

            transcript = stt.transcribe(audio_file)
            if not transcript:
                self.state.add_result("stt", False, "STT produced empty transcript")
                return False

            self.state.add_result("stt", True, f"STT test passed: '{transcript}'", {
                "transcript": transcript
            })
            return True
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            self.state.add_result("stt", False, f"STT test exception: {e}")
            return False

    def test_agent(self, agent: Callable, test_query: str = "what time is it?") -> bool:
        """Test 4: Agent - verify the agent can process a query without voice."""
        print(f"[DIAGNOSTICS] Test 4: Agent - processing '{test_query}'")
        try:
            response = agent(test_query)
            if not response:
                self.state.add_result("agent", False, "Agent returned empty response")
                return False

            self.state.add_result("agent", True, f"Agent test passed: '{response[:50]}...'", {
                "response_length": len(str(response))
            })
            return True
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            self.state.add_result("agent", False, f"Agent test exception: {e}")
            return False

    def test_full_voice(self, stt: Any, tts: Any, agent: Callable, test_file: str = "data/test_voice.wav") -> bool:
        """Test 5: Full voice - microphone --> record --> STT --> agent --> TTS --> speaker."""
        print("[DIAGNOSTICS] Test 5: Full voice E2E test")
        try:
            # Test 5a: Record audio
            print("  [5a] Recording audio...")
            import sounddevice as sd
            import soundfile as sf

            os.makedirs(os.path.dirname(test_file), exist_ok=True)
            sample_rate = 16000
            audio_data = []
            with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16") as stream:
                start_time = time.time()
                while time.time() - start_time < 2.0:  # Record 2 seconds
                    chunk, _ = stream.read(int(sample_rate * 0.1))
                    audio_data.append(chunk.flatten())

            if not audio_data:
                self.state.add_result("full_voice", False, "No audio recorded")
                return False

            audio = np.concatenate(audio_data)
            sf.write(test_file, audio, sample_rate)
            print(f"  [5a] Recorded {len(audio)} samples ({len(audio)/sample_rate:.2f}s)")

            # Test 5b: Transcribe
            print("  [5b] Transcribing...")
            transcript = stt.transcribe(test_file)
            if not transcript:
                self.state.add_result("full_voice", False, "STT produced empty transcript")
                return False
            print(f"  [5b] Transcript: '{transcript}'")

            # Test 5c: Get agent response
            print("  [5c] Getting agent response...")
            response = agent(transcript)
            if not response:
                self.state.add_result("full_voice", False, "Agent returned empty response")
                return False
            print(f"  [5c] Response: '{str(response)[:50]}...'")

            # Test 5d: Speak response
            print("  [5d] Speaking response...")
            tts_result = tts.speak(str(response))
            print(f"  [5d] Speech completed: {tts_result.success}")

            self.state.add_result("full_voice", True, "Full voice E2E test passed", {
                "transcript": transcript,
                "response_length": len(str(response)),
                "speech_success": tts_result.success if hasattr(tts_result, 'success') else True
            })
            return True
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            self.state.add_result("full_voice", False, f"Full voice test exception: {e}")
            return False

    def run_all_diagnostics(self, stt: Any, tts: Any, agent: Callable) -> dict:
        """Run all diagnostic tests and return results."""
        print("[DIAGNOSTICS] Running full diagnostic suite...")

        # Test 1: Speaker
        speaker_passed = self.test_speaker(tts)

        # Test 2: Microphone (only if speaker test passed)
        mic_passed = False
        if speaker_passed:
            mic_passed = self.test_microphone(stt)

        # Test 3: STT
        stt_passed = self.test_stt(stt)

        # Test 4: Agent
        agent_passed = self.test_agent(agent)

        # Test 5: Full voice (only if all previous tests passed)
        if speaker_passed and mic_passed and stt_passed and agent_passed:
            self.test_full_voice(stt, tts, agent)

        print("[DIAGNOSTICS] Diagnostic suite completed")
        return self.state.summary()


def run_diagnostics(stt: Any, tts: Any, agent: Callable) -> dict:
    """Convenience function to run all voice diagnostics."""
    diagnostics = VoiceDiagnostics()
    return diagnostics.run_all_diagnostics(stt, tts, agent)


__all__ = [
    "VoiceDiagnostics",
    "VoiceDiagnosticState",
    "run_diagnostics",
]
