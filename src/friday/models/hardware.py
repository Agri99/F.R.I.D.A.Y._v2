"""
src/friday/models/hardware.py

WHAT THIS IS FOR:
Hardware capability detection for smart model/profile routing.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Any

@dataclass
class HardwareProfile:
    cpu_model: str
    cpu_cores: int
    ram_gb: float
    gpu_vendor: str | None     # 'nvidia' | 'amd' | 'intel' | None
    gpu_name: str | None
    vram_gb: float | None
    cuda_available: bool
    rocm_available: bool
    storage_free_gb: float
    screen_resolution: tuple[int, int]
    capability_tier: str       # 'LOW' | 'BALANCED' | 'HIGH' | 'MAXIMUM'


def detect_hardware() -> HardwareProfile:
    """Detect system hardware capabilities."""
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
        cpu_cores = psutil.cpu_count(logical=False) or 4
        
        # Simple storage check
        disk = psutil.disk_usage('/')
        storage_free_gb = disk.free / (1024**3)
    except ImportError:
        ram_gb = 16.0
        cpu_cores = 8
        storage_free_gb = 100.0

    gpu_vendor = None
    gpu_name = None
    vram_gb = None
    cuda_available = False
    
    # Try nvidia-smi
    try:
        res = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], 
                             capture_output=True, text=True, check=True)
        if res.stdout.strip():
            gpu_vendor = "nvidia"
            parts = res.stdout.strip().split(',')
            gpu_name = parts[0].strip()
            vram_gb = float(parts[1].strip().replace(" MiB", "")) / 1024.0
            cuda_available = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Tier classification
    tier = "LOW"
    if vram_gb is not None:
        if vram_gb >= 24:
            tier = "MAXIMUM"
        elif vram_gb >= 12:
            tier = "HIGH"
        elif vram_gb >= 8:
            tier = "BALANCED"
    elif ram_gb >= 32:
        tier = "BALANCED"
        
    return HardwareProfile(
        cpu_model=platform.processor(),
        cpu_cores=cpu_cores,
        ram_gb=ram_gb,
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        cuda_available=cuda_available,
        rocm_available=False,
        storage_free_gb=storage_free_gb,
        screen_resolution=(1920, 1080), # stub
        capability_tier=tier
    )

def recommend_profile(hw: HardwareProfile) -> str:
    """Recommend a config profile based on hardware."""
    if hw.capability_tier == "LOW":
        return "laptop.yaml"
    elif hw.capability_tier == "BALANCED":
        return "balanced.yaml"
    else:
        return "workstation.yaml"
