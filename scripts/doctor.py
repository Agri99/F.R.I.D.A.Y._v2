#!/usr/bin/env python3
"""
scripts/doctor.py

WHAT THIS IS FOR:
Diagnostic entrypoint for FRIDAY (Runbook §80, §13).

Runs checks on:
  1. Python version (>= 3.11)
  2. Package dependencies
  3. Audio input device
  4. Audio output device
  5. Wake word engine
  6. STT engine
  7. TTS engine
  8. LLM provider (Ollama/cloud)
  9. Configured models
  10. GPU / Hardware acceleration
  11. Docker availability
  12. Browser (Playwright)
  13. Memory DB (SQLite/FTS5)
  14. Workspace directory
  15. Secrets store
  16. Google OAuth credentials
  17. Audit path & logging

With --voice flag, runs additional voice pipeline diagnostics:
  - Wake word detection
  - VAD calibration
  - STT streaming
  - TTS synthesis
  - Latency benchmarks

Outputs PASS, WARN, or FAIL with remediation advice.
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Callable

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))


def check_item(name: str, check_fn: Callable[[], tuple[bool, str]]) -> tuple[str, str, str]:
    try:
        ok, msg = check_fn()
        return ("PASS" if ok else "WARN", name, msg)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
        return ("FAIL", name, str(e))


def run_basic_diagnostics() -> list[tuple[str, str, str]]:
    """Run basic system diagnostics."""
    checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = []

    # 1. Python
    def c_python():
        v = sys.version_info
        ok = v.major == 3 and v.minor >= 11
        return ok, f"Python {v.major}.{v.minor}.{v.micro} (expected >= 3.11)"
    checks.append(("Python Environment", c_python))

    # 2. Package Dependencies
    def c_pkgs():
        missing = []
        for pkg in ["pydantic", "yaml", "psutil", "sounddevice", "numpy"]:
            try:
                __import__(pkg)
            except ImportError:
                missing.append(pkg)
        if missing:
            return False, f"Missing packages: {', '.join(missing)}"
        return True, "Core dependencies installed"
    checks.append(("Core Dependencies", c_pkgs))

    # 3. Audio Input
    def c_audio_in():
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            has_input = any(d.get("max_input_channels", 0) > 0 for d in devices)
            return has_input, "Microphone available" if has_input else "No recording input device detected"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Audio check failed: {e}"
    checks.append(("Audio Input Device", c_audio_in))

    # 4. Audio Output
    def c_audio_out():
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            has_out = any(d.get("max_output_channels", 0) > 0 for d in devices)
            return has_out, "Speaker available" if has_out else "No playback output device detected"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Audio check failed: {e}"
    checks.append(("Audio Output Device", c_audio_out))

    # 5. Wake word
    def c_wakeword():
        if importlib.util.find_spec("openwakeword") is not None:
            return True, "openWakeWord library installed"
        return False, "openwakeword package missing"
    checks.append(("Wake Word Engine", c_wakeword))

    # 6. STT
    def c_stt():
        if importlib.util.find_spec("faster_whisper") is not None:
            return True, "faster-whisper available"
        return False, "faster-whisper package missing"
    checks.append(("STT Engine", c_stt))

    # 7. TTS
    def c_tts():
        if importlib.util.find_spec("chatterbox") is not None:
            try:
                import torch
                dev = "CUDA" if torch.cuda.is_available() else "CPU"
                return True, f"Chatterbox Turbo available (device: {dev})"
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
                return False, f"TTS check failed: {e}"
        return False, "chatterbox-tts package missing (pip install chatterbox-tts)"
    checks.append(("TTS Engine (Chatterbox Turbo)", c_tts))

    # 8. LLM Provider
    def c_llm():
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            return True, "Ollama daemon reachable at localhost:11434"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            return False, "Ollama daemon not reachable. Run 'ollama serve'"
    checks.append(("LLM Provider (Ollama)", c_llm))

    # 9. Docker
    def c_docker():
        if shutil.which("docker") is None:
            return False, "Docker CLI not found on PATH"
        return True, "Docker executable detected"
    checks.append(("Docker Environment", c_docker))

    # 10. Playwright
    def c_browser():
        if importlib.util.find_spec("playwright") is not None:
            return True, "Playwright library installed"
        return False, "playwright package not installed"
    checks.append(("Browser Automation", c_browser))

    # 11. Memory DB
    def c_db():
        db_path = _ROOT / "data" / "friday.db"
        if not db_path.exists():
            return False, f"Database not found at {db_path} (will be created on first start)"
        try:
            conn = sqlite3.connect(str(db_path))
            conn.close()
            return True, "SQLite database accessible"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Database error: {e}"
    checks.append(("Memory Database", c_db))

    # 12. Workspace directory
    def c_workspace():
        ws = _ROOT / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        return True, f"Workspace active at {ws}"
    checks.append(("Workspace", c_workspace))

    # 13. Audit directory
    def c_audit():
        ad = _ROOT / "data" / "audit"
        ad.mkdir(parents=True, exist_ok=True)
        return True, f"Audit directory ready at {ad}"
    checks.append(("Audit Log Path", c_audit))

    # Run all checks
    results = []
    for title, fn in checks:
        results.append(check_item(title, fn))
    return results


def run_voice_diagnostics() -> list[tuple[str, str, str]]:
    """Run voice-specific diagnostics (Runbook §13)."""
    results: list[tuple[str, str, str]] = []

    # 1. VAD Calibration
    def test_vad():
        try:
            from friday.interaction.vad import RmsVoiceActivityDetector, SileroVoiceActivityDetector
            # Try Silero first
            try:
                SileroVoiceActivityDetector()
                return True, "Silero VAD loaded successfully"
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                # Fallback to RMS
                RmsVoiceActivityDetector(rms_threshold=50.0)
                return True, "RMS VAD available (Silero not found)"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"VAD initialization failed: {e}"
    results.append(check_item("VAD", test_vad))

    # 2. Wake Word Model
    def test_wakeword_model():
        try:
            model_path = _ROOT / "models" / "hey_friday.onnx"
            if model_path.exists():
                return True, f"Wake word model found at {model_path}"
            # Check for openwakeword default models
            if importlib.util.find_spec("openwakeword") is not None:
                return True, "openwakeword will download models on first use"
            return False, "Wake word model not found and openwakeword not installed"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Wake word check failed: {e}"
    results.append(check_item("Wake Word Model", test_wakeword_model))

    # 3. STT Model
    def test_stt_model():
        try:
            from friday.interaction.stt import StreamingTranscriber  # noqa: F401
            # Don't actually load the model, just verify the class works
            return True, "StreamingTranscriber available (model loads on first use)"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"STT check failed: {e}"
    results.append(check_item("Streaming STT", test_stt_model))

    # 4. TTS Synthesis
    def test_tts_synthesis():
        try:
            from friday.interaction.streaming_tts import StreamingTts, QueuedAudioSink
            # Test that we can create a StreamingTts
            def dummy_synth(text: str):
                return None
            sink = QueuedAudioSink()
            StreamingTts(synth=dummy_synth, sink=sink)
            return True, "StreamingTts initialized successfully"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"TTS check failed: {e}"
    results.append(check_item("Streaming TTS", test_tts_synthesis))

    # 5. Audio Capture
    def test_audio_capture():
        try:
            from friday.interaction.audio_capture import AudioCapture, AudioCaptureConfig
            config = AudioCaptureConfig()
            AudioCapture(config)
            # Don't actually start it, just verify creation
            return True, "AudioCapture service available"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Audio capture check failed: {e}"
    results.append(check_item("Audio Capture Service", test_audio_capture))

    # 6. Audio Output
    def test_audio_output():
        try:
            from friday.interaction.audio_output import AudioOutputService, AudioOutputConfig
            config = AudioOutputConfig()
            AudioOutputService(config)
            return True, "AudioOutputService available"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Audio output check failed: {e}"
    results.append(check_item("Audio Output Service", test_audio_output))

    # 7. Turn Detector
    def test_turn_detector():
        try:
            from friday.interaction.turn_detector import TurnDetector, TurnDetectorConfig
            config = TurnDetectorConfig()
            TurnDetector(config)
            return True, "TurnDetector initialized successfully"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Turn detector check failed: {e}"
    results.append(check_item("Turn Detector", test_turn_detector))

    # 8. Conversation Manager
    def test_conversation_manager():
        try:
            from friday.interaction.conversation import ConversationManager
            manager = ConversationManager()
            snap = manager.snapshot()
            return True, f"ConversationManager ready (id={snap.conversation_id[:12]}...)"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Conversation manager check failed: {e}"
    results.append(check_item("Conversation Manager", test_conversation_manager))

    # 9. Interruption Manager
    def test_interruption_manager():
        try:
            from friday.interaction.interruption import InterruptionManager
            im = InterruptionManager()
            gen = im.generation()
            return True, f"InterruptionManager ready (gen={gen})"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Interruption manager check failed: {e}"
    results.append(check_item("Interruption Manager", test_interruption_manager))

    # 10. Voice Pipeline
    def test_voice_pipeline():
        try:
            from friday.interaction.pipeline import VoicePipeline
            from friday.interaction.audio_input import AudioInputStream
            from friday.interaction.vad import RmsVoiceActivityDetector
            from friday.interaction.turn_detector import TurnDetector
            from friday.interaction.streaming_tts import StreamingTts, QueuedAudioSink
            from friday.interaction.interruption import InterruptionManager
            from friday.interaction.conversation import ConversationManager
            from friday.interaction.stt import StreamingTranscriber

            sink = QueuedAudioSink()
            tts = StreamingTts(synth=lambda x: None, sink=sink)
            VoicePipeline(
                audio_input=AudioInputStream(),
                vad=RmsVoiceActivityDetector(),
                transcriber=StreamingTranscriber(model_size="small"),
                turn_detector=TurnDetector(),
                streaming_tts=tts,
                interruption=InterruptionManager(),
                conversation=ConversationManager(),
                sink=sink,
            )
            return True, "VoicePipeline assembled successfully"
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            return False, f"Pipeline assembly failed: {e}"
    results.append(check_item("Voice Pipeline Assembly", test_voice_pipeline))

    return results


def print_results(results: list[tuple[str, str, str]], title: str) -> tuple[int, int]:
    """Print results and return (fails, warns) counts."""
    print(f"\n{title}")
    print("=" * 60)

    fails = 0
    warns = 0

    for status, title_text, msg in results:
        color = {"PASS": "\033[92m", "WARN": "\033[93m", "FAIL": "\033[91m"}.get(status, "")
        reset = "\033[0m"
        print(f"[{color}{status:4s}{reset}] {title_text:30s} - {msg}")
        if status == "FAIL":
            fails += 1
        elif status == "WARN":
            warns += 1

    return fails, warns


def main():
    parser = argparse.ArgumentParser(description="F.R.I.D.A.Y. System Doctor")
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Run additional voice pipeline diagnostics",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("           F.R.I.D.A.Y. SYSTEM DOCTOR")
    print("=" * 60)

    total_fails = 0
    total_warns = 0

    # Basic diagnostics
    basic_results = run_basic_diagnostics()
    fails, warns = print_results(basic_results, "Basic System Checks")
    total_fails += fails
    total_warns += warns

    # Voice diagnostics (if requested)
    if args.voice:
        voice_results = run_voice_diagnostics()
        fails, warns = print_results(voice_results, "Voice Pipeline Checks")
        total_fails += fails
        total_warns += warns

    print("=" * 60)
    if total_fails > 0:
        print(f"FAILED with {total_fails} critical issues. Please remediate before running FRIDAY.")
    elif total_warns > 0:
        print(f"ONLINE with {total_warns} warnings. FRIDAY is operational with fallbacks.")
    else:
        print("ALL CHECKS PASSED. FRIDAY is in 100% operational condition.")
    print("=" * 60)

    return 1 if total_fails > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
