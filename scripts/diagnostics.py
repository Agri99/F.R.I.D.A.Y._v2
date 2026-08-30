#!/usr/bin/env python3
"""
scripts/diagnostics.py

WHAT THIS IS FOR:
Structured diagnostics and system inspection for F.R.I.D.A.Y. v3 (§28).
Provides detailed system state inspection for debugging and monitoring.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


class SystemDiagnostics:
    """Comprehensive system diagnostics for F.R.I.D.A.Y. v3."""

    def __init__(self):
        self.results = {}

    def run_full_diagnostics(self) -> dict:
        """Run all diagnostic checks and return structured results."""
        print("[*] Running full system diagnostics...")

        self.results = {
            "timestamp": datetime.now().isoformat(),
            "system": self._check_system(),
            "python": self._check_python(),
            "dependencies": self._check_dependencies(),
            "directories": self._check_directories(),
            "database": self._check_database(),
            "models": self._check_models(),
            "audio": self._check_audio(),
            "network": self._check_network(),
            "config": self._check_config(),
            "logs": self._check_logs(),
            "performance": self._check_performance(),
        }

        return self.results

    def _check_system(self) -> dict:
        """System-level checks."""
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "hostname": platform.node(),
            "uptime_seconds": self._get_uptime(),
        }

    def _get_uptime(self) -> float:
        try:
            import psutil
            return time.time() - psutil.boot_time()
        except Exception:
            return 0.0

    def _check_python(self) -> dict:
        return {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "path": sys.path[:5],
        }

    def _check_dependencies(self) -> dict:
        """Check key dependencies are installed and their versions."""
        deps = {}
        packages = [
            "pydantic", "pyyaml", "requests", "psutil", "pillow",
            "ollama", "sounddevice", "soundfile", "numpy",
            "pywin32", "pywinauto", "pycaw", "comtypes",
            "PySide6", "websockets", "faster_whisper", "openwakeword",
            "piper_tts", "onnxruntime", "speechbrain", "torch", "torchaudio",
            "playwright", "google-auth", "pytesseract",
        ]

        for pkg in packages:
            try:
                mod = __import__(pkg.replace("-", "_"))
                version = getattr(mod, "__version__", "unknown")
                deps[pkg] = {"installed": True, "version": version}
            except ImportError:
                deps[pkg] = {"installed": False, "version": None}

        return deps

    def _check_directories(self) -> dict:
        required = [
            "data", "data/audit", "data/jobs", "data/trajectories",
            "data/voice_enrollment", "skills/builtin", "skills/learned",
            "workspace", "models", "secrets", "config"
        ]

        dirs = {}
        for d in required:
            path = _ROOT / d
            exists = path.exists()
            writable = path.is_dir() and os.access(path, os.W_OK) if exists else False
            dirs[d] = {"exists": exists, "writable": writable}

        return {"checked": len(required), "present": sum(1 for d in dirs.values() if d["exists"]), "details": dirs}

    def _check_database(self) -> dict:
        db_path = _ROOT / "data" / "friday.db"
        if not db_path.exists():
            return {"exists": False, "error": "Database file not found"}

        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Check tables
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

            # Check row counts
            counts = {}
            for table in tables:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    counts[table] = count
                except Exception:
                    counts[table] = -1

            # Check FTS tables
            fts_tables = [t for t in tables if "_fts" in t]

            conn.close()

            return {
                "path": str(db_path),
                "size_mb": db_path.stat().st_size / (1024 * 1024),
                "tables": tables,
                "fts_tables": fts_tables,
                "row_counts": counts,
            }
        except Exception as e:
            return {"exists": True, "error": str(e)}

    def _check_models(self) -> dict:
        """Check Ollama and model availability."""
        models = {"ollama_running": False, "models": [], "error": None}

        try:
            import requests
            r = requests.get("http://localhost:11434/api/tags", timeout=3)
            if r.status_code == 200:
                models["ollama_running"] = True
                models["models"] = [m.get("name") for m in r.json().get("models", [])]
            else:
                models["error"] = f"HTTP {r.status_code}"
        except Exception as e:
            models["error"] = str(e)

        # Check local model cache
        models_dir = _ROOT / "models"
        if models_dir.exists():
            cached = list(models_dir.rglob("*.gguf")) + list(models_dir.rglob("*.bin"))
            models["cached_models"] = [str(f.relative_to(models_dir)) for f in cached[:20]]

        return models

    def _check_audio(self) -> dict:
        audio = {"devices": [], "default_input": None, "default_output": None, "error": None}

        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    audio["devices"].append({
                        "index": i,
                        "name": dev.get("name"),
                        "input_channels": dev.get("max_input_channels"),
                        "output_channels": dev.get("max_output_channels"),
                        "sample_rate": dev.get("default_samplerate"),
                    })

            # Get defaults
            try:
                default_in = sd.query_devices(kind="input")
                audio["default_input"] = default_in.get("name")
            except Exception:
                pass

            try:
                default_out = sd.query_devices(kind="output")
                audio["default_output"] = default_out.get("name")
            except Exception:
                pass

        except Exception as e:
            audio["error"] = str(e)

        return audio

    def _check_network(self) -> dict:
        net = {"ollama_reachable": False, "internet": False, "dns": False, "latency_ms": 0}

        try:
            import requests
            start = time.time()
            r = requests.get("http://localhost:11434/api/tags", timeout=2)
            net["ollama_reachable"] = r.status_code == 200
            net["latency_ms"] = (time.time() - start) * 1000
        except Exception:
            pass

        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            net["internet"] = True
            net["dns"] = True
        except Exception:
            pass

        return net

    def _check_config(self) -> dict:
        config = {
            "env_file": (_ROOT / ".env").exists(),
            "env_example": (_ROOT / ".env.example").exists(),
            "pyproject": (_ROOT / "pyproject.toml").exists(),
            "config_dir": (_ROOT / "config").exists(),
            "config_files": [],
        }

        config_dir = _ROOT / "config"
        if config_dir.exists():
            config["config_files"] = [f.name for f in config_dir.glob("*.yaml")]

        return config

    def _check_logs(self) -> dict:
        log_dirs = {
            "audit": _ROOT / "data" / "audit",
            "trajectories": _ROOT / "data" / "trajectories",
            "jobs": _ROOT / "data" / "jobs",
        }

        logs = {}
        for name, path in log_dirs.items():
            if path.exists():
                files = list(path.glob("*"))
                total_size = sum(f.stat().st_size for f in files)
                logs[name] = {
                    "path": str(path),
                    "files": len(files),
                    "size_mb": sum(f.stat().st_size for f in files) / (1024 * 1024),
                }
            else:
                logs[name] = {"path": str(path), "files": 0, "size_mb": 0, "error": "Directory missing"}

        return logs

    def _check_performance(self) -> dict:
        perf = {}

        # CPU benchmark
        try:
            import numpy as np
            size = 512
            a = np.random.randn(size, size).astype(np.float32)
            b = np.random.randn(size, size).astype(np.float32)

            start = time.time()
            for _ in range(10):
                _ = a @ b
            elapsed = time.time() - start
            perf["cpu_matmul_10x512_ms"] = elapsed * 1000
        except Exception:
            perf["cpu_matmul_10x512_ms"] = -1

        # Memory
        try:
            import psutil
            mem = psutil.virtual_memory()
            perf["memory_total_gb"] = mem.total / (1024**3)
            perf["memory_available_gb"] = mem.available / (1024**3)
            perf["memory_percent"] = mem.percent
        except Exception:
            pass

        # Disk
        try:
            usage = shutil.disk_usage(str(_ROOT))
            perf["disk_free_gb"] = usage.free / (1024**3)
            perf["disk_total_gb"] = usage.total / (1024**3)
        except Exception:
            pass

        return perf

    def print_results(self, output_format: str = "text") -> None:
        """Print diagnostics results."""
        if not self.results:
            self.run_full_diagnostics()

        if output_format == "json":
            print(json.dumps(self.results, indent=2, default=str))
        else:
            print("\n" + "=" * 60)
            print("F.R.I.D.A.Y. v3 - SYSTEM DIAGNOSTICS REPORT")
            print("=" * 60)
            print(f"Timestamp: {self.results.get('timestamp', 'unknown')}")

            for category, data in self.results.items():
                if category == "timestamp":
                    continue
                print(f"\n[{category.upper()}]")
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, dict):
                            print(f"  {key}:")
                            for k, v in value.items():
                                print(f"    {k}: {v}")
                        elif isinstance(value, list):
                            print(f"  {key}: {len(value)} items")
                            for item in value[:5]:
                                print(f"    - {item}")
                            if len(value) > 5:
                                print(f"    ... and {len(value) - 5} more")
                        else:
                            print(f"  {key}: {value}")
                else:
                    print(f"  {data}")


def main():
    parser = argparse.ArgumentParser(description="F.R.I.D.A.Y. v3 Structured Diagnostics")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--output", help="Output file path")
    args = parser.parse_args()

    diag = SystemDiagnostics()
    results = diag.run_full_diagnostics()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved to {args.output}")

    diag.print_results(args.format)


if __name__ == "__main__":
    main()