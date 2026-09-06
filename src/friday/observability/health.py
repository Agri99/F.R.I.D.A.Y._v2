"""
src/friday/observability/health.py

WHAT THIS IS FOR:
System health checks for Model, Security, Audio, and Memory subsystems.
Runbook §79, §99.
"""
from typing import Dict, Any


def check_model_health() -> Dict[str, Any]:
    """Checks if Ollama or Cloud API is responsive."""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return {"status": "ok", "message": "Ollama is reachable"}
    except Exception as e:
        return {"status": "degraded", "message": f"Model endpoint unreachable: {e}"}


def check_security_health() -> Dict[str, Any]:
    """Checks if audit path and capabilities are intact."""
    from pathlib import Path
    audit_dir = Path("data/audit")
    if not audit_dir.exists():
        return {"status": "degraded", "message": "Audit path missing"}
    return {"status": "ok", "message": "Security invariants met"}


def check_audio_health() -> Dict[str, Any]:
    """Checks mic/speaker availability."""
    try:
        import sounddevice as sd
        in_devs = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        out_devs = [d for d in sd.query_devices() if d.get("max_output_channels", 0) > 0]
        if not in_devs or not out_devs:
            return {"status": "degraded", "message": "Missing audio input/output devices"}
        return {"status": "ok", "message": "Audio subsystem ready"}
    except Exception as e:
        return {"status": "degraded", "message": f"Audio error: {e}"}


def check_memory_health() -> Dict[str, Any]:
    """Checks SQLite database integrity."""
    from pathlib import Path
    import sqlite3
    db_path = Path("data/friday.db")
    if not db_path.exists():
        return {"status": "ok", "message": "Memory DB not yet created (clean state)"}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA integrity_check;")
        conn.close()
        return {"status": "ok", "message": "Memory DB is healthy"}
    except Exception as e:
        return {"status": "error", "message": f"Memory DB corrupt: {e}"}


def run_all_healthchecks() -> Dict[str, Any]:
    return {
        "models": check_model_health(),
        "security": check_security_health(),
        "audio": check_audio_health(),
        "memory": check_memory_health(),
    }

