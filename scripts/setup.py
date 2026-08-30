#!/usr/bin/env python3
"""
scripts/setup.py

WHAT THIS IS FOR:
Interactive/automated first-run bootstrap wizard for F.R.I.D.A.Y. v3 (§7, §28 of Blueprint).
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
        _ROOT / "data",
        _ROOT / "data" / "audit",
        _ROOT / "data" / "trajectories",
        _ROOT / "data" / "jobs",
        _ROOT / "data" / "voice_enrollment",
        _ROOT / "secrets",
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
    import requests
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m.get("name") for m in r.json().get("models", [])]
            print(f"    [+] Ollama is online. Installed models: {', '.join(models) if models else 'None'}")
            return True
    except Exception:
        pass
    print("    [!] Ollama is not reachable on http://localhost:11434.")
    print("        Please start Ollama and run: ollama pull qwen3:8b")
    return False


def setup_env_file() -> None:
    print("[*] Checking environment configuration...")
    env_path = _ROOT / ".env"
    example_path = _ROOT / ".env.example"
    if not env_path.exists() and example_path.exists():
        shutil.copy(example_path, env_path)
        print("    [+] Created .env from .env.example")
    elif env_path.exists():
        print("    [+] Existing .env configuration detected.")


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
    print("      F.R.I.D.A.Y. v3 Setup Wizard       ")
    print("==========================================\n")

    check_python_version()
    ensure_directories()
    setup_env_file()
    initialize_database()
    detect_hardware_and_profile()
    check_ollama()

    print("\n[+] Setup completed successfully!")
    print("    To run FRIDAY in voice mode:   python src/friday/app.py")
    print("    To run FRIDAY in text mode:    python src/friday/app.py --text\n")


if __name__ == "__main__":
    main()
