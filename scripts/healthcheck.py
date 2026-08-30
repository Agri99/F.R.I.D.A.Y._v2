#!/usr/bin/env python3
"""
scripts/healthcheck.py

WHAT THIS IS FOR:
Structured system diagnostics and readiness checks for F.R.I.D.A.Y. v3 (§28 of Blueprint).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def check_directories() -> tuple[bool, str]:
    required = ["data", "data/audit", "data/jobs", "skills/builtin", "workspace"]
    missing = [d for d in required if not (_ROOT / d).exists()]
    if missing:
        return False, f"Missing directories: {', '.join(missing)}"
    return True, "All required runtime directories present."


def check_database() -> tuple[bool, str]:
    db_path = _ROOT / "data" / "friday.db"
    if not db_path.exists():
        return False, "Database file (data/friday.db) does not exist."
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        return True, f"SQLite database accessible. Tables: {', '.join(tables)}"
    except Exception as exc:
        return False, f"Database error: {exc}"


def check_ollama() -> tuple[bool, str]:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m.get("name") for m in r.json().get("models", [])]
            return True, f"Ollama online. Available models: {', '.join(models) if models else 'None'}"
    except Exception:
        pass
    return False, "Ollama is not reachable on http://localhost:11434."


def check_disk_space() -> tuple[bool, str]:
    try:
        usage = shutil.disk_usage(str(_ROOT))
        free_gb = usage.free / (1024 ** 3)
        if free_gb < 2.0:
            return False, f"Low disk space: {free_gb:.1f} GB remaining."
        return True, f"{free_gb:.1f} GB free disk space available."
    except Exception as exc:
        return True, f"Disk check skipped ({exc})"


def check_audio_subsystem() -> tuple[bool, str]:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devs = [d for d in devices if d.get("max_input_channels", 0) > 0]
        output_devs = [d for d in devices if d.get("max_output_channels", 0) > 0]
        return True, f"Audio ready. {len(input_devs)} input, {len(output_devs)} output devices detected."
    except Exception as exc:
        return False, f"Audio error: {exc}"


def main() -> None:
    print("\n=== F.R.I.D.A.Y. v3 System Health Diagnostics ===\n")
    checks = [
        ("Runtime Directories", check_directories),
        ("Disk Space", check_disk_space),
        ("Memory Database", check_database),
        ("Ollama Inference", check_ollama),
        ("Audio Subsystem", check_audio_subsystem),
    ]

    all_passed = True
    for name, check_fn in checks:
        passed, msg = check_fn()
        status_tag = "[PASS]" if passed else "[FAIL]"
        print(f"  {status_tag} {name}: {msg}")
        if not passed:
            all_passed = False

    print("\n================================================")
    if all_passed:
        print("[+] System is 100% HEALTHY and READY.")
    else:
        print("[!] Warnings/Failures detected. Please inspect items above.")
    print("================================================\n")


if __name__ == "__main__":
    main()
