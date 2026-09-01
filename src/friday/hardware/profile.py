"""Hardware profile selection and loading."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from friday.hardware.probe import HardwareProfile, recommend_profile


def select_profile(profile: HardwareProfile) -> str:
    """Select a profile filename for the detected hardware."""
    return recommend_profile(profile)


def load_profile(profile_name: str, profiles_dir: str | Path = "config/profiles") -> dict[str, Any]:
    """Load a hardware profile without embedding hardware assumptions in business logic."""
    safe_name = Path(profile_name).name
    path = Path(profiles_dir) / safe_name
    if not path.exists():
        raise FileNotFoundError(f"Hardware profile not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Hardware profile must be a mapping: {path}")
    return data
