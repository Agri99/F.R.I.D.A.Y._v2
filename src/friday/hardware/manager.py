"""Hardware probing, telemetry, resource budgeting, and profile selection."""
from __future__ import annotations

from dataclasses import dataclass

from friday.hardware.budget import ResourceBudget, ResourcePressure
from friday.hardware.capability import CapabilityTier, evaluate_capability
from friday.hardware.probe import HardwareProfile, probe_hardware, recommend_models_for_tier
from friday.hardware.profile import load_profile, select_profile
from friday.hardware.telemetry import TelemetryMonitor, TelemetrySnapshot


@dataclass
class HardwareState:
    profile: HardwareProfile
    telemetry: TelemetrySnapshot
    pressure: ResourcePressure
    selected_profile: str


class HardwareManager:
    """Coordinates maximum hardware capacity with current resource availability."""

    def __init__(
        self,
        budget: ResourceBudget | None = None,
        monitor: TelemetryMonitor | None = None,
    ) -> None:
        self.budget = budget or ResourceBudget()
        self.monitor = monitor or TelemetryMonitor()
        self.profile: HardwareProfile | None = None

    def initialize(self, start_monitoring: bool = True) -> HardwareState:
        self.profile = probe_hardware()
        if start_monitoring:
            self.monitor.start()
        return self.state()

    def state(self) -> HardwareState:
        if self.profile is None:
            self.profile = probe_hardware()
        telemetry = self.monitor.latest
        return HardwareState(
            profile=self.profile,
            telemetry=telemetry,
            pressure=self.budget.evaluate(telemetry),
            selected_profile=select_profile(self.profile),
        )

    def recommended_models(self) -> dict[str, str]:
        if self.profile is None:
            self.profile = probe_hardware()
        return recommend_models_for_tier(self.profile.capability_tier)

    def should_downgrade(self) -> bool:
        return self.state().pressure == ResourcePressure.CRITICAL

    def can_upgrade(self) -> bool:
        return self.budget.permits_model_upgrade(self.monitor.latest)

    def stop(self) -> None:
        self.monitor.stop()


__all__ = [
    "CapabilityTier",
    "HardwareManager",
    "HardwareProfile",
    "HardwareState",
    "ResourceBudget",
    "ResourcePressure",
    "TelemetryMonitor",
    "TelemetrySnapshot",
    "evaluate_capability",
    "load_profile",
    "probe_hardware",
    "select_profile",
]
