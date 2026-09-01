# src/friday/hardware/__init__.py

"""Hardware manager package."""

from friday.hardware.budget import ResourceBudget, ResourcePressure
from friday.hardware.capability import CapabilityTier, evaluate_capability
from friday.hardware.manager import HardwareManager, HardwareState
from friday.hardware.probe import HardwareProfile, probe_hardware
from friday.hardware.telemetry import TelemetryMonitor, TelemetrySnapshot

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
    "probe_hardware",
]
