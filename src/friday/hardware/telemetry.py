"""
Continuous hardware telemetry monitor.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None


@dataclass
class TelemetrySnapshot:
    cpu_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_percent: float = 0.0
    gpu_util_percent: float | None = None
    vram_used_gb: float | None = None
    disk_percent: float = 0.0
    timestamp: float = field(default_factory=time.time)


class TelemetryMonitor:
    """Continuously monitors CPU, RAM, GPU, VRAM, and disk on a background interval."""

    def __init__(self, interval_seconds: float = 2.0) -> None:
        self._interval = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_snapshot: TelemetrySnapshot = TelemetrySnapshot()

    @property
    def latest(self) -> TelemetrySnapshot:
        with self._lock:
            return self._last_snapshot

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._last_snapshot = self._sample()
            self._stop_event.wait(self._interval)

    def _sample(self) -> TelemetrySnapshot:
        if psutil is None:
            return TelemetrySnapshot()
        snap = TelemetrySnapshot()
        try:
            snap.cpu_percent = psutil.cpu_percent(interval=None)
        except Exception:
            pass
        try:
            mem = psutil.virtual_memory()
            snap.ram_used_gb = mem.used / (1024 ** 3)
            snap.ram_percent = mem.percent
        except Exception:
            pass
        try:
            disk = psutil.disk_usage("/")
            snap.disk_percent = disk.percent
        except Exception:
            pass
        # GPU stats attempted via nvidia-smi / rocm-smi
        try:
            import subprocess
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                 "--format=csv,noheader", "--id=0"],
                capture_output=True, text=True, timeout=2,
            )
            if res.stdout.strip():
                util, mem_used = res.stdout.strip().split(",")
                snap.gpu_util_percent = float(util.strip().replace("%", ""))
                snap.vram_used_gb = float(mem_used.strip().replace(" MiB", "")) / 1024.0
        except Exception:
            pass
        return snap
