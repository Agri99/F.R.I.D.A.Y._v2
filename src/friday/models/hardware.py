"""
src/friday/models/hardware.py

WHAT THIS IS FOR:
Hardware capability detection for smart model/profile routing.
Enhanced with AMD/Intel GPU detection, CPU benchmarking, and performance estimation.
"""

from __future__ import annotations

import os
import platform
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class HardwareProfile:
    cpu_model: str
    cpu_cores: int
    cpu_logical_cores: int
    ram_gb: float
    gpu_vendor: str | None     # 'nvidia' | 'amd' | 'intel' | None
    gpu_name: str | None
    vram_gb: float | None
    cuda_available: bool
    rocm_available: bool
    intel_gpu: bool
    storage_free_gb: float
    screen_resolution: tuple[int, int]
    capability_tier: str       # 'LOW' | 'BALANCED' | 'HIGH' | 'MAXIMUM'

    # Performance estimates (tokens/sec for different model sizes)
    estimated_inference_speed: dict[str, float] = field(default_factory=dict)
    estimated_vision_speed: float = 0.0
    estimated_stt_speed: float = 0.0
    estimated_tts_speed: float = 0.0


def _detect_nvidia() -> tuple[Optional[str], Optional[str], Optional[float], bool]:
    """Detect NVIDIA GPU and VRAM."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, check=True, timeout=5
        )
        if res.stdout.strip():
            parts = res.stdout.strip().split(',')
            name = parts[0].strip()
            vram = float(parts[1].strip().replace(" MiB", "")) / 1024.0
            return "nvidia", name, vram, True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return None, None, None, False


def _detect_amd() -> tuple[Optional[str], Optional[str], Optional[float], bool]:
    """Detect AMD GPU via rocm-smi."""
    try:
        res = subprocess.run(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram"],
            capture_output=True, text=True, check=True, timeout=5
        )
        if res.stdout.strip():
            lines = res.stdout.strip().split('\n')
            name = "AMD GPU"
            vram = None
            for line in lines:
                if "Product" in line:
                    name = line.split(":")[-1].strip()
                elif "VRAM" in line or "vram" in line:
                    try:
                        vram = float(line.split(":")[-1].strip().split()[0]) / 1024.0  # MB to GB
                    except:
                        pass
            return "amd", name, vram, True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return None, None, None, False


def _detect_intel_gpu() -> bool:
    """Detect Intel integrated GPU."""
    try:
        res = subprocess.run(
            ["lspci", "-nn"],
            capture_output=True, text=True, check=True, timeout=5
        )
        if "VGA" in res.stdout and "Intel" in res.stdout:
            return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return False


def _estimate_cpu_inference_speed(cpu_cores: int, cpu_model: str) -> dict[str, float]:
    """Estimate inference speed (tokens/sec) for different model sizes."""
    # Rough estimates based on CPU cores and model
    base_speed = cpu_cores * 0.5  # Very rough baseline

    # Adjust for known CPU models
    model_lower = cpu_model.lower()
    if any(x in model_lower for x in ["i9", "ryzen 9", "threadripper", "xeon"]):
        base_speed *= 2.0
    elif any(x in model_lower for x in ["i7", "ryzen 7"]):
        base_speed *= 1.5
    elif any(x in model_lower for x in ["i5", "ryzen 5"]):
        base_speed *= 1.0
    else:
        base_speed *= 0.7

    return {
        "1b": base_speed * 50,      # ~50 tok/s per core for 1B model
        "3b": base_speed * 20,
        "7b": base_speed * 8,
        "13b": base_speed * 4,
        "30b": base_speed * 1.5,
        "70b": base_speed * 0.5,
    }


def _estimate_vision_speed(vram_gb: Optional[float], cuda: bool, rocm: bool) -> float:
    """Estimate vision model speed (images/sec)."""
    if vram_gb is None:
        return 0.1  # CPU only - very slow
    if vram_gb >= 12:
        return 4.0
    elif vram_gb >= 8:
        return 2.0
    elif vram_gb >= 4:
        return 1.0
    return 0.5


def _estimate_stt_speed(cpu_cores: int, vram_gb: Optional[float]) -> float:
    """Estimate STT speed (realtime factor)."""
    if vram_gb and vram_gb >= 4:
        return 4.0  # GPU accelerated
    return cpu_cores * 0.3  # CPU only


def _estimate_tts_speed(cpu_cores: int, vram_gb: Optional[float]) -> float:
    """Estimate TTS speed (realtime factor)."""
    if vram_gb and vram_gb >= 4:
        return 3.0  # GPU accelerated
    return cpu_cores * 0.4  # CPU only


def _benchmark_cpu_inference() -> float:
    """Quick CPU inference benchmark using a tiny model."""
    try:
        # Simple matrix multiplication benchmark as proxy
        import numpy as np
        size = 512
        a = np.random.randn(size, size).astype(np.float32)
        b = np.random.randn(size, size).astype(np.float32)

        start = time.time()
        for _ in range(10):
            _ = a @ b
        elapsed = time.time() - start

        # Normalize: faster = higher score
        return 10.0 / max(elapsed, 0.01)
    except Exception:
        return 1.0


def detect_hardware() -> HardwareProfile:
    """Detect system hardware capabilities with comprehensive GPU/CPU detection."""
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
        cpu_cores = psutil.cpu_count(logical=False) or 4
        cpu_logical = psutil.cpu_count(logical=True) or 8

        # Simple storage check
        disk = psutil.disk_usage('C:\\' if platform.system() == 'Windows' else '/')
        storage_free_gb = disk.free / (1024**3)
    except ImportError:
        ram_gb = 16.0
        cpu_cores = 8
        cpu_logical = 16
        storage_free_gb = 100.0

    # GPU detection
    gpu_vendor, gpu_name, vram_gb, cuda_available = _detect_nvidia()
    if gpu_vendor is None:
        gpu_vendor, gpu_name, vram_gb, rocm_available = _detect_amd()
        cuda_available = False
    else:
        rocm_available = False

    intel_gpu = _detect_intel_gpu()

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
    elif ram_gb >= 16:
        tier = "LOW"

    cpu_model = platform.processor() or platform.machine()
    estimated_inference = _estimate_cpu_inference_speed(cpu_cores, cpu_model)
    estimated_vision = _estimate_vision_speed(vram_gb, cuda_available, rocm_available)
    estimated_stt = _estimate_stt_speed(cpu_cores, vram_gb)
    estimated_tts = _estimate_tts_speed(cpu_cores, vram_gb)
    cpu_bench = _benchmark_cpu_inference()

    # Apply CPU benchmark factor
    for k in estimated_inference:
        estimated_inference[k] *= cpu_bench

    return HardwareProfile(
        cpu_model=cpu_model,
        cpu_cores=cpu_cores,
        cpu_logical_cores=cpu_logical,
        ram_gb=ram_gb,
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        cuda_available=cuda_available,
        rocm_available=rocm_available,
        intel_gpu=intel_gpu,
        storage_free_gb=storage_free_gb,
        screen_resolution=(1920, 1080),  # stub - could detect on Windows
        capability_tier=tier,
        estimated_inference_speed=estimated_inference,
        estimated_vision_speed=estimated_vision,
        estimated_stt_speed=estimated_stt,
        estimated_tts_speed=estimated_tts,
    )


def recommend_profile(hw: HardwareProfile) -> str:
    """Recommend a config profile based on hardware."""
    if hw.capability_tier == "LOW":
        return "laptop.yaml"
    elif hw.capability_tier == "BALANCED":
        return "balanced.yaml"
    elif hw.capability_tier == "HIGH":
        return "workstation.yaml"
    else:  # MAXIMUM
        return "workstation.yaml"


def recommend_models_for_tier(tier: str) -> dict[str, str]:
    """Recommend model sizes for each role based on capability tier."""
    if tier == "LOW":
        return {
            "fast": "qwen2:1.5b",
            "reasoning": "qwen2:3b",
            "vision": "llava:7b",
            "embedding": "nomic-embed-text",
            "stt": "whisper-tiny",
            "tts": "piper",
            "reranker": "bge-small",
        }
    elif tier == "BALANCED":
        return {
            "fast": "qwen2:3b",
            "reasoning": "qwen2:7b",
            "vision": "llava:13b",
            "embedding": "nomic-embed-text",
            "stt": "whisper-base",
            "tts": "piper",
            "reranker": "bge-base",
        }
    elif tier == "HIGH":
        return {
            "fast": "qwen2:7b",
            "reasoning": "qwen2:14b",
            "vision": "llava:34b",
            "embedding": "nomic-embed-text",
            "stt": "whisper-small",
            "tts": "piper",
            "reranker": "bge-large",
        }
    else:  # MAXIMUM
        return {
            "fast": "qwen2:14b",
            "reasoning": "qwen2:72b",
            "vision": "llama3.2-vision:90b",
            "embedding": "nomic-embed-text",
            "stt": "whisper-medium",
            "tts": "piper",
            "reranker": "bge-large",
        }


def print_hardware_summary(hw: HardwareProfile) -> None:
    """Print a human-readable hardware summary."""
    print(f"\n=== Hardware Profile ===")
    print(f"CPU: {hw.cpu_model} ({hw.cpu_cores}C/{hw.cpu_logical_cores}T)")
    print(f"RAM: {hw.ram_gb:.1f} GB")
    print(f"GPU: {hw.gpu_vendor or 'None'} - {hw.gpu_name or 'None'} (VRAM: {hw.vram_gb:.1f} GB)" if hw.vram_gb else f"GPU: {hw.gpu_vendor or 'None'}")
    print(f"CUDA: {hw.cuda_available}, ROCm: {hw.rocm_available}, Intel GPU: {hw.intel_gpu}")
    print(f"Storage: {hw.storage_free_gb:.1f} GB free")
    print(f"Tier: {hw.capability_tier}")
    print(f"\nEstimated Inference Speed (tok/s):")
    for model, speed in hw.estimated_inference_speed.items():
        print(f"  {model}: {speed:.1f} tok/s")
    print(f"Vision: {hw.estimated_vision_speed:.1f} img/s")
    print(f"STT: {hw.estimated_stt_speed:.1f}x realtime")
    print(f"TTS: {hw.estimated_tts_speed:.1f}x realtime")
    print(f"\nRecommended Profile: {recommend_profile(hw)}")
    print(f"Recommended Models: {recommend_models_for_tier(hw.capability_tier)}")