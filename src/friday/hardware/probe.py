"""
Hardware probe wrappers.
"""
from __future__ import annotations

from friday.models.hardware import detect_hardware, HardwareProfile, recommend_profile, recommend_models_for_tier

__all__ = ["probe_hardware", "HardwareProfile", "recommend_profile", "recommend_models_for_tier"]


def probe_hardware() -> HardwareProfile:
    """Detect system hardware capabilities and classify capability tier."""
    return detect_hardware()
