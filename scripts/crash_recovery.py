#!/usr/bin/env python3
"""
scripts/crash_recovery.py

WHAT THIS IS FOR:
Crash recovery and automatic restart for F.R.I.D.A.Y. v3 (§28).
Handles graceful shutdown, state persistence, and automatic recovery.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_STATE_DIR = _ROOT / "data" / "state"
_CRASH_LOG = _ROOT / "data" / "crash_log.jsonl"
_RECOVERY_STATE = _STATE_DIR / "recovery_state.json"


class CrashRecoveryManager:
    """Manages crash recovery and graceful shutdown for F.R.I.D.A.Y. v3."""

    def __init__(self):
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.crashed = False
        self.shutdown_requested = False
        self._register_signal_handlers()
        atexit.register(self._on_exit)

    def _register_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._signal_handler)
            except Exception:
                pass  # Windows may not support all signals

    def _signal_handler(self, signum, frame) -> None:
        print(f"\n[*] Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
        self.save_state()

    def _on_exit(self) -> None:
        """Called on normal program exit."""
        if not self.shutdown_requested:
            print("[*] Normal exit detected")
        self.save_state()

    def save_state(self, component: str = "app", state: dict | None = None) -> None:
        """Persist current state for recovery."""
        _STATE_DIR.mkdir(parents=True, exist_ok=True)

        state_data = {
            "timestamp": datetime.now().isoformat(),
            "component": component,
            "pid": os.getpid(),
            "state": state or {},
        }

        state_file = _STATE_DIR / f"{component}_state.json"
        state_file.write_text(json.dumps(state_data, indent=2))

        # Also append to crash log
        with open(_CRASH_LOG, "a") as f:
            f.write(json.dumps(state_data) + "\n")

    def check_for_crash(self) -> bool:
        """Check if last run ended unexpectedly."""
        if not _RECOVERY_STATE.exists():
            return False

        try:
            data = json.loads(_RECOVERY_STATE.read_text())
            # If state is from a different PID, it was a crash
            if data.get("pid") != os.getpid():
                self.crashed = True
                return True
        except Exception:
            pass
        return False

    def get_last_state(self, component: str = "app") -> dict | None:
        """Get the last saved state for a component."""
        state_file = _STATE_DIR / f"{component}_state.json"
        if state_file.exists():
            try:
                return json.loads(state_file.read_text())
            except Exception:
                pass
        return None

    def clear_recovery_state(self) -> None:
        """Clear crash recovery state after successful startup."""
        _RECOVERY_STATE.unlink(missing_ok=True)
        self.crashed = False

    def log_crash(self, error: Exception, context: str = "") -> None:
        """Log a crash with full context."""
        crash_entry = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": __import__('traceback').format_exc(),
            "context": context,
            "pid": os.getpid(),
        }

        with open(_CRASH_LOG, "a") as f:
            f.write(json.dumps(crash_entry) + "\n")

        print(f"[!] Crash logged: {type(error).__name__}: {error}")

    def attempt_recovery(self, component: str = "app") -> bool:
        """Attempt to recover from last known state."""
        state = self.get_last_state(component)
        if not state:
            print("[!] No recovery state found")
            return False

        print(f"[*] Attempting recovery for {component}...")
        print(f"    Last state: {state.get('timestamp', 'unknown')}")

        # This would be implemented by the specific component
        # For now, just indicate recovery is possible
        return True


class Watchdog:
    """Watchdog timer to detect and restart hung processes."""

    def __init__(self, timeout_seconds: int = 60):
        self.timeout = timeout_seconds
        self.last_heartbeat = time.time()
        self.running = False
        self._thread = None

    def start(self) -> None:
        self.running = True
        import threading
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)

    def heartbeat(self) -> None:
        self.last_heartbeat = time.time()

    def _run(self) -> None:
        while self.running:
            time.sleep(1)
            if time.time() - self.last_heartbeat > self.timeout:
                print(f"[!] Watchdog timeout - process appears hung!")
                self._trigger_restart()

    def _trigger_restart(self) -> None:
        print("[!] Triggering emergency restart...")
        # In a real implementation, this would restart the process
        # For now, just log the event
        with open(_CRASH_LOG, "a") as f:
            f.write(json.dumps({
                "timestamp": datetime.now().isoformat(),
                "event": "watchdog_timeout",
                "message": "Process hang detected, restart triggered",
            }) + "\n")


def main():
    parser = argparse.ArgumentParser(description="F.R.I.D.A.Y. v3 Crash Recovery Manager")
    parser.add_argument("--check-crash", action="store_true", help="Check if last run crashed")
    parser.add_argument("--recover", help="Component to recover (app, voice, etc.)")
    parser.add_argument("--log-crash", action="store_true", help="Simulate crash logging")
    args = parser.parse_args()

    manager = CrashRecoveryManager()

    if args.check_crash:
        if manager.check_for_crash():
            print("[!] Previous run ended unexpectedly (crash detected)")
            state = manager.get_last_state()
            if state:
                print(f"  Last state: {state}")
            return 1
        else:
            print("[+] No crash detected - clean shutdown")
            return 0

    if args.recover:
        success = manager.attempt_recovery(args.recover)
        if success:
            print("[+] Recovery attempted")
        return 0 if success else 1

    if args.log_crash:
        # Simulate a crash for testing
        try:
            raise RuntimeError("Simulated crash for testing")
        except Exception as e:
            manager.log_crash(e, "Test crash simulation")
        return 0

    print("Usage: python crash_recovery.py --check-crash | --recover <component> | --log-crash")
    return 0


if __name__ == "__main__":
    sys.exit(main())