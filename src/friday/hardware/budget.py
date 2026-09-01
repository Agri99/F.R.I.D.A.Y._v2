"""Resource pressure evaluation and execution budgets."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from friday.hardware.telemetry import TelemetrySnapshot


class ResourcePressure(str, Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ResourceBudget:
    max_cpu_percent: float = 80.0
    max_ram_percent: float = 85.0
    max_gpu_percent: float = 90.0
    max_disk_percent: float = 90.0

    def evaluate(self, snapshot: TelemetrySnapshot) -> ResourcePressure:
        values = [snapshot.cpu_percent, snapshot.ram_percent, snapshot.disk_percent]
        ratios = [
            values[0] / max(self.max_cpu_percent, 1.0),
            values[1] / max(self.max_ram_percent, 1.0),
            values[2] / max(self.max_disk_percent, 1.0),
        ]
        if snapshot.gpu_util_percent is not None:
            ratios.append(snapshot.gpu_util_percent / max(self.max_gpu_percent, 1.0))
        highest = max(ratios, default=0.0)
        if highest >= 1.0:
            return ResourcePressure.CRITICAL
        if highest >= 0.8:
            return ResourcePressure.ELEVATED
        return ResourcePressure.NORMAL

    def permits_model_upgrade(self, snapshot: TelemetrySnapshot) -> bool:
        return self.evaluate(snapshot) == ResourcePressure.NORMAL
