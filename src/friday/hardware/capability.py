"""
Hardware capability tier evaluation.
"""
from __future__ import annotations

from enum import Enum

from friday.hardware.probe import HardwareProfile


class CapabilityTier(str, Enum):
    LOW = "LOW"
    BALANCED = "BALANCED"
    HIGH = "HIGH"
    MAXIMUM = "MAXIMUM"


def evaluate_capability(profile: HardwareProfile) -> CapabilityTier:
    """Return the capability tier for the given hardware profile."""
    return CapabilityTier(profile.capability_tier)
