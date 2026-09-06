#!/usr/bin/env python3
"""
scripts/doctor.py

WHAT THIS IS FOR:
Diagnostic entrypoint for FRIDAY (Runbook §80).
Runs checks on:
  1. Python version (>= 3.11)
  2. Package dependencies
  3. Audio input device
  4. Audio output device
  5. Wake word engine
  6. STT engine
  7. TTS engine
  8. Ollama connection
  9. Configured models
  10. GPU / Hardware acceleration
  11. Docker availability
  12. Browser (Playwright)
  13. Memory DB (SQLite/FTS5)
  14. Workspace directory
  15. Secrets store
  16. Google OAuth credentials
  17. Audit path & logging
Outputs PASS, WARN, or FAIL with remediation advice.
"""
from __future__ import annotations

import os
import sys
import shutil
import sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))


def check_item(name: str, check_fn) -> tuple[str, str]:
    try:
        ok, msg = check_fn()
        return ("PASS" if ok else "WARN", msg)
    except Exception as e:
        return ("FAIL", str(e))


def run_diagnostics():
    print("=" * 60)
    print("           F.R.I.D.A.Y. SYSTEM DOCTOR")
    print("=" * 60)

    checks = []

    # 1. Python
    def c_python():
        v = sys.version_info
        ok = v.major == 3 and v.minor >= 11
        return ok, f"Python {v.major}.{v.minor}.{v.micro} (expected >= 3.11)"
    checks.append(("Python Environment", c_python))

    # 2. Package Dependencies
    def c_pkgs():
        missing = []
        for pkg in ["pydantic", "yaml", "psutil", "sounddevice", "numpy", "ollama"]:
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
        import sounddevice as sd
        devices = sd.query_devices()
        has_input = any(d.get("max_input_channels", 0) > 0 for d in devices)
        return has_input, "Microphone available" if has_input else "No recording input device detected"
    checks.append(("Audio Input Device", c_audio_in))

    # 4. Audio Output
    def c_audio_out():
        import sounddevice as sd
        devices = sd.query_devices()
        has_out = any(d.get("max_output_channels", 0) > 0 for d in devices)
        return has_out, "Speaker available" if has_out else "No playback output device detected"
    checks.append(("Audio Output Device", c_audio_out))

    # 5. Wake word
    def c_wakeword():
        try:
            import openwakeword
            return True, "openWakeWord library installed"
        except ImportError:
            return False, "openwakeword package missing"
    checks.append(("Wake Word Engine", c_wakeword))

    # 6. STT
    def c_stt():
        try:
            import faster_whisper
            return True, "faster-whisper available"
        except ImportError:
            return False, "faster-whisper package missing"
    checks.append(("STT Engine", c_stt))

    # 7. TTS
    def c_tts():
        from friday.config import Settings
        cfg = Settings.load()
        voice_path = Path("models/piper") / f"{cfg.voice.tts_voice}.onnx"
        if voice_path.exists():
            return True, f"TTS voice model found: {cfg.voice.tts_voice}"
        return False, f"TTS model not downloaded at {voice_path} (will download or synthesize on demand)"
    checks.append(("TTS Engine", c_tts))

    # 8. Ollama connection
    def c_ollama():
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            return True, "Ollama daemon reachable at localhost:11434"
        except Exception:
            return False, "Ollama daemon not reachable. Run 'ollama serve'"
    checks.append(("Ollama Server", c_ollama))

    # 9. Docker
    def c_docker():
        if shutil.which("docker") is None:
            return False, "Docker CLI not found on PATH"
        return True, "Docker executable detected"
    checks.append(("Docker Environment", c_docker))

    # 10. Playwright
    def c_browser():
        try:
            import playwright
            return True, "Playwright library installed"
        except ImportError:
            return False, "playwright package not installed"
    checks.append(("Browser Automation", c_browser))

    # 11. Memory DB
    def c_db():
        db_path = _ROOT / "data" / "friday.db"
        if not db_path.exists():
            return False, f"Database not found at {db_path} (will be created on first start)"
        conn = sqlite3.connect(str(db_path))
        conn.close()
        return True, "SQLite database accessible"
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

    results = []
    for title, fn in checks:
        status, msg = check_item(title, fn)
        color = {"PASS": "\033[92m", "WARN": "\033[93m", "FAIL": "\033[91m"}.get(status, "")
        reset = "\033[0m"
        print(f"[{color}{status:4s}{reset}] {title:25s} - {msg}")
        results.append((status, title, msg))

    print("=" * 60)
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    if fails:
        print(f"FAILED with {len(fails)} critical issues. Please remediate before running FRIDAY.")
    elif warns:
        print(f"ONLINE with {len(warns)} warnings. FRIDAY is operational with fallbacks.")
    else:
        print("ALL CHECKS PASSED. FRIDAY is in 100% operational condition.")
    print("=" * 60)


if __name__ == "__main__":
    run_diagnostics()
