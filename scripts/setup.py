#!/usr/bin/env python3
"""
scripts/setup.py

WHAT THIS IS FOR:
Interactive/automated first-run bootstrap wizard for F.R.I.D.A.Y. v2 (Runbook §81).
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

# Add src to sys.path
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def check_python_version() -> bool:
    print(f"[*] Python Version: {sys.version.split()[0]} ({platform.system()} {platform.release()})")
    if sys.version_info < (3, 11):
        print("[!] Warning: Python 3.11+ is strongly recommended.")
        return False
    return True


def ensure_directories() -> None:
    print("[*] Initializing runtime directories...")
    dirs = [
        _ROOT / "data" / "audit",
        _ROOT / "data" / "trajectories",
        _ROOT / "data" / "jobs",
        _ROOT / "data" / "voice_enrollment",
        _ROOT / "secrets" / "google",
        _ROOT / "skills" / "builtin",
        _ROOT / "skills" / "learned",
        _ROOT / "skills" / "archived",
        _ROOT / "workspace",
        _ROOT / "models",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print("    [+] All directories ready.")


def detect_hardware_and_profile() -> str:
    print("[*] Probing hardware capabilities...")
    try:
        from friday.models.hardware import detect_hardware, recommend_profile
        hw = detect_hardware()
        print(f"    CPU: {hw.cpu_model} ({hw.cpu_cores} cores)")
        print(f"    RAM: {hw.ram_gb:.1f} GB")
        print(f"    GPU: {hw.gpu_name or 'None'} ({hw.vram_gb or 0:.1f} GB VRAM)")
        profile = recommend_profile(hw)
        print(f"    [+] Recommended Hardware Profile: {profile}")
        return profile
    except Exception as exc:
        print(f"    [!] Hardware detection fallback ({exc}). Defaulting to balanced.yaml")
        return "balanced.yaml"


def check_ollama() -> bool:
    print("[*] Checking Ollama service...")
    try:
        import urllib.request
        import json
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        if req.status == 200:
            data = json.loads(req.read().decode())
            models = [m.get("name") for m in data.get("models", [])]
            print(f"    [+] Ollama is online. Installed models: {', '.join(models) if models else 'None'}")
            return True
    except Exception:
        pass
    print("    [!] Ollama is not reachable on http://localhost:11434.")
    print("        Please start Ollama and run: ollama pull qwen2.5-coder:7b")
    return False


def setup_env_file() -> dict[str, str]:
    print("[*] Interactive Configuration (Runbook §81)")
    
    config = {}
    
    # owner identity
    owner = input("    [?] What is your name (Owner Identity)? [Boss]: ").strip()
    config['OWNER_NAME'] = owner or "Boss"
    
    # wake word
    wake = input("    [?] What should the wake word be? [friday]: ").strip()
    config['WAKE_WORD'] = wake or "friday"
    
    # mic/speaker
    print("    [?] Audio devices can be listed later with 'python -m sounddevice'")
    config['AUDIO_INPUT_DEVICE'] = input("    [?] Default microphone ID or name? [default]: ").strip() or "default"
    config['AUDIO_OUTPUT_DEVICE'] = input("    [?] Default speaker ID or name? [default]: ").strip() or "default"
    
    # STT/TTS
    config['STT_MODEL'] = input("    [?] STT engine? [faster-whisper]: ").strip() or "faster-whisper"
    config['TTS_VOICE'] = input("    [?] TTS voice? [en_US-lessac-medium]: ").strip() or "en_US-lessac-medium"
    
    # google integration
    google = input("    [?] Enable Google API integrations (Gmail/Calendar)? (y/N): ").strip().lower()
    config['ENABLE_GOOGLE'] = "true" if google == "y" else "false"
    
    # docker dev mode
    docker = input("    [?] Enable Docker development mode for isolated sandboxes? (Y/n): ").strip().lower()
    config['ENABLE_DOCKER'] = "false" if docker == "n" else "true"
    
    # security passphrase
    passphrase = input("    [?] Security passphrase for destructive operations (optional): ").strip()
    if passphrase:
        config['SECURITY_PASSPHRASE'] = passphrase
        
    # voice enrollment
    voice_en = input("    [?] Enable speaker verification (Voice Enrollment)? (y/N): ").strip().lower()
    config['REQUIRE_VOICE_ENROLLMENT'] = "true" if voice_en == "y" else "false"

    env_path = _ROOT / ".env"
    
    print(f"\n[*] Writing configuration to {env_path}")
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        
    for k, v in config.items():
        # simple upsert
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{k}="):
                lines[i] = f"{k}={v}"
                found = True
                break
        if not found:
            lines.append(f"{k}={v}")
            
    env_path.write_text("\n".join(lines) + "\n")
    print("    [+] .env file updated.")
    return config


def initialize_database() -> None:
    print("[*] Initializing SQLite memory database...")
    try:
        from friday.memory.database import MemoryDatabase
        db_path = _ROOT / "data" / "friday.db"
        db = MemoryDatabase(str(db_path))
        print("    [+] Database connected and verified.")
    except Exception as exc:
        print(f"    [!] Database initialization error: {exc}")


def main() -> None:
    print("\n==========================================")
    print("      F.R.I.D.A.Y. Setup Wizard          ")
    print("==========================================\n")

    check_python_version()
    ensure_directories()
    profile = detect_hardware_and_profile()
    
    config = setup_env_file()
    
    # Record the chosen hardware profile
    env_path = _ROOT / ".env"
    with open(env_path, "a") as f:
        f.write(f"\nHARDWARE_PROFILE={profile}\n")
    
    initialize_database()
    check_ollama()

    print("\n[+] Setup completed successfully!")
    print("    To run FRIDAY:   friday")
    print("    To test system:  friday doctor\n")


if __name__ == "__main__":
    main()
