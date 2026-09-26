"""
src/friday/resource/budget.py

WHAT THIS IS FOR:
Resource budgets and monitoring (Runbook §43 — Phase Q1).

Monitor:
  - CPU usage
  - RAM usage
  - VRAM usage
  - GPU utilization
  - STT/LLM/TTS latency
  - Queue depth
  - Disk usage

Degrade gracefully when resources constrained.
"""

from __future__ import annotations

import psutil
import threading
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ResourcePressure(str, Enum):
    """System resource pressure level."""
    NORMAL = "normal"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ResourceMetrics:
    """Current resource usage metrics."""
    cpu_percent: float
    ram_percent: float
    vram_percent: float | None
    gpu_percent: float | None
    disk_percent: float
    stt_latency_ms: float | None
    llm_latency_ms: float | None
    tts_latency_ms: float | None
    queue_depth: int
    pressure: ResourcePressure


class ResourceBudget:
    """Defines resource limits and thresholds."""

    def __init__(self):
        self.cpu_threshold_percent = 80.0
        self.ram_threshold_percent = 85.0
        self.vram_threshold_percent = 90.0
        self.stt_latency_threshold_ms = 1000.0
        self.llm_latency_threshold_ms = 2000.0
        self.tts_latency_threshold_ms = 500.0
        self.max_queue_depth = 100

    def get_critical_threshold(self) -> ResourceBudget:
        """Get threshold at which system becomes critical."""
        budget = ResourceBudget()
        budget.cpu_threshold_percent = 95.0
        budget.ram_threshold_percent = 95.0
        budget.vram_threshold_percent = 98.0
        return budget


class ResourceMonitor:
    """Monitors system resources and enforces budgets."""

    def __init__(self, budget: ResourceBudget | None = None):
        self.budget = budget or ResourceBudget()
        self._lock = threading.Lock()
        self._metrics: ResourceMetrics | None = None
        self._running = False

    def get_metrics(self) -> ResourceMetrics:
        """Get current resource metrics."""
        with self._lock:
            if self._metrics:
                return self._metrics

        metrics = self._sample_metrics()
        with self._lock:
            self._metrics = metrics
        return metrics

    def _sample_metrics(self) -> ResourceMetrics:
        """Sample current resource usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            ram_percent = psutil.virtual_memory().percent
            disk_percent = psutil.disk_usage("/").percent

            # Try to get GPU metrics (optional)
            vram_percent = None
            gpu_percent = None
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    vram_percent = gpus[0].memoryUsed / gpus[0].memoryTotal * 100
                    gpu_percent = gpus[0].load * 100
            except Exception:
                pass

            pressure = self._calculate_pressure(cpu_percent, ram_percent, vram_percent)

            return ResourceMetrics(
                cpu_percent=cpu_percent,
                ram_percent=ram_percent,
                vram_percent=vram_percent,
                gpu_percent=gpu_percent,
                disk_percent=disk_percent,
                stt_latency_ms=None,
                llm_latency_ms=None,
                tts_latency_ms=None,
                queue_depth=0,
                pressure=pressure,
            )
        except Exception as e:
            logger.error(f"Error sampling metrics: {e}")
            return ResourceMetrics(
                cpu_percent=0,
                ram_percent=0,
                vram_percent=None,
                gpu_percent=None,
                disk_percent=0,
                stt_latency_ms=None,
                llm_latency_ms=None,
                tts_latency_ms=None,
                queue_depth=0,
                pressure=ResourcePressure.NORMAL,
            )

    def _calculate_pressure(
        self,
        cpu_percent: float,
        ram_percent: float,
        vram_percent: float | None,
    ) -> ResourcePressure:
        """Calculate overall resource pressure."""
        # Check critical first
        if (
            cpu_percent > 95
            or ram_percent > 95
            or (vram_percent and vram_percent > 98)
        ):
            return ResourcePressure.CRITICAL

        # Check high
        if (
            cpu_percent > self.budget.cpu_threshold_percent
            or ram_percent > self.budget.ram_threshold_percent
            or (vram_percent and vram_percent > self.budget.vram_threshold_percent)
        ):
            return ResourcePressure.HIGH

        # Check moderate
        if (
            cpu_percent > 60
            or ram_percent > 75
            or (vram_percent and vram_percent > 80)
        ):
            return ResourcePressure.MODERATE

        return ResourcePressure.NORMAL

    def should_degrade(self) -> bool:
        """Check if system should degrade performance."""
        metrics = self.get_metrics()
        return metrics.pressure in (ResourcePressure.HIGH, ResourcePressure.CRITICAL)

    def get_model_recommendation(self) -> str:
        """Recommend model size based on resources."""
        metrics = self.get_metrics()

        if metrics.pressure == ResourcePressure.CRITICAL:
            return "tiny"  # Smallest model
        elif metrics.pressure == ResourcePressure.HIGH:
            return "small"
        elif metrics.pressure == ResourcePressure.MODERATE:
            return "medium"
        else:
            return "large"  # Full-size model

    def log_metrics(self) -> None:
        """Log current metrics for debugging."""
        metrics = self.get_metrics()
        logger.info(
            f"Resources: CPU={metrics.cpu_percent:.1f}%, "
            f"RAM={metrics.ram_percent:.1f}%, "
            f"Pressure={metrics.pressure.value}"
        )


__all__ = [
    "ResourcePressure",
    "ResourceMetrics",
    "ResourceBudget",
    "ResourceMonitor",
]
