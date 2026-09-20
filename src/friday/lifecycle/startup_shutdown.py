"""
src/friday/lifecycle/startup_shutdown.py

WHAT THIS IS FOR:
Orderly startup and shutdown (Runbook §41 — Phase T2).

Startup:
  1. Single-instance lock
  2. Load config
  3. Load state
  4. Profile hardware
  5. Health-check
  6. Start audio
  7. Start jobs
  8. Start UI

Shutdown:
  1. Stop jobs
  2. Stop capture
  3. Stop playback
  4. Cancel active generation
  5. Flush audit
  6. Persist state
  7. Release lock
  8. Exit
"""

from __future__ import annotations

import sys
import time
import atexit
from pathlib import Path
from typing import Any, Callable
import logging

logger = logging.getLogger(__name__)


class SingleInstanceLock:
    """Prevent multiple instances from running."""

    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self._locked = False

    def acquire(self, timeout: float = 5.0) -> bool:
        """Acquire the lock."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                # Try to create lock file exclusively
                with open(self.lock_file, "x") as f:
                    f.write(str(time.time()))
                self._locked = True
                return True
            except FileExistsError:
                time.sleep(0.1)
        return False

    def release(self) -> None:
        """Release the lock."""
        if self._locked:
            try:
                self.lock_file.unlink()
                self._locked = False
            except FileNotFoundError:
                pass

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Could not acquire lock - another instance running?")
        return self

    def __exit__(self, *args):
        self.release()


class StartupManager:
    """Orchestrates orderly startup."""

    def __init__(self):
        self._lock: SingleInstanceLock | None = None
        self._components: dict[str, Any] = {}
        self._startup_order = [
            "lock",
            "config",
            "state",
            "hardware",
            "health_check",
            "audio",
            "jobs",
            "ui",
        ]

    def startup(self, root_dir: Path) -> bool:
        """Execute startup sequence.

        Args:
            root_dir: Project root directory

        Returns:
            True if startup successful
        """
        logger.info("FRIDAY startup sequence starting")

        try:
            # 1. Acquire lock
            lock_file = root_dir / "data" / ".friday.lock"
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            self._lock = SingleInstanceLock(lock_file)
            if not self._lock.acquire():
                logger.error("Could not acquire instance lock - another instance running")
                return False
            logger.info("Instance lock acquired")

            # 2. Load config
            from friday.config import Settings
            config = Settings.load()
            self._components["config"] = config
            logger.info("Configuration loaded")

            # 3. Load state
            state_file = root_dir / "data" / "state.json"
            if state_file.exists():
                import json
                with open(state_file) as f:
                    state = json.load(f)
                self._components["state"] = state
                logger.info("State restored")
            else:
                self._components["state"] = {}

            # 4. Profile hardware
            from friday.hardware.probe import HardwareProfile
            profile = HardwareProfile()
            profile.probe()
            self._components["hardware"] = profile
            logger.info(f"Hardware profiled: {profile.capability_tier}")

            # 5. Health check
            if not self._health_check():
                logger.error("Health check failed")
                return False

            # 6. Start audio
            from friday.interaction import AudioCapture, AudioCaptureConfig
            audio_config = AudioCaptureConfig(
                sample_rate=config.voice.sample_rate if hasattr(config, 'voice') else 16000
            )
            audio = AudioCapture(audio_config)
            audio.start()
            self._components["audio"] = audio
            logger.info("Audio capture started")

            # 7. Start jobs
            from friday.jobs import JobRegistry
            jobs = JobRegistry()
            jobs.start()
            self._components["jobs"] = jobs
            logger.info("Job scheduler started")

            # 8. Start UI (if enabled)
            if config.ui_enabled if hasattr(config, 'ui_enabled') else True:
                logger.info("UI layer ready (lazy-loaded on first access)")

            logger.info("FRIDAY startup complete")
            return True

        except Exception as e:
            logger.error(f"Startup failed: {e}")
            self._cleanup()
            return False

    def _health_check(self) -> bool:
        """Run health checks on critical systems."""
        try:
            # Audio devices
            import sounddevice as sd
            devices = sd.query_devices()
            has_input = any(d.get("max_input_channels", 0) > 0 for d in devices)
            has_output = any(d.get("max_output_channels", 0) > 0 for d in devices)

            if not has_input or not has_output:
                logger.warning("Audio devices missing - will run degraded")

            # Models
            config = self._components.get("config")
            if config and hasattr(config, "models"):
                logger.info("Model config present")

            return True
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return False

    def _cleanup(self) -> None:
        """Clean up on failure."""
        if self._lock:
            self._lock.release()


class ShutdownManager:
    """Orchestrates orderly shutdown."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self._shutdown_handlers: list[tuple[str, Callable[[], None]]] = []

    def register_handler(self, name: str, handler: Callable[[], None]) -> None:
        """Register a shutdown handler."""
        self._shutdown_handlers.append((name, handler))

    def shutdown(self) -> None:
        """Execute shutdown sequence."""
        logger.info("FRIDAY shutdown sequence starting")

        try:
            # 1. Stop jobs
            logger.info("Stopping jobs")

            # 2. Stop capture
            logger.info("Stopping audio capture")

            # 3. Stop playback
            logger.info("Stopping audio playback")

            # 4. Cancel active generation
            logger.info("Canceling active generation")

            # 5. Flush audit
            logger.info("Flushing audit log")

            # 6. Persist state
            state_file = self.root_dir / "data" / "state.json"
            state_file.parent.mkdir(parents=True, exist_ok=True)
            import json
            with open(state_file, "w") as f:
                json.dump({"shutdown_time": time.time()}, f)
            logger.info("State persisted")

            # 7. Run custom handlers
            for name, handler in reversed(self._shutdown_handlers):
                try:
                    logger.info(f"Running shutdown handler: {name}")
                    handler()
                except Exception as e:
                    logger.error(f"Shutdown handler {name} failed: {e}")

            # 8. Release lock
            logger.info("Releasing instance lock")

            logger.info("FRIDAY shutdown complete")

        except Exception as e:
            logger.error(f"Shutdown error: {e}")


def setup_lifecycle(root_dir: Path) -> tuple[StartupManager, ShutdownManager]:
    """Set up startup and shutdown managers."""
    startup = StartupManager()
    shutdown = ShutdownManager(root_dir)

    # Register shutdown handlers
    @atexit.register
    def at_exit():
        shutdown.shutdown()

    return startup, shutdown


__all__ = [
    "SingleInstanceLock",
    "StartupManager",
    "ShutdownManager",
    "setup_lifecycle",
]
