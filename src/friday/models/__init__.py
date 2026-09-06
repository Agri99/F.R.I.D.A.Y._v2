"""
src/friday/models/__init__.py

WHAT THIS IS FOR:
Exports the key public classes of the models subsystem.
Clients should import from `friday.models`, not internal files.
"""

from __future__ import annotations

from friday.models.base import (
    ModelDelta,
    ModelFormat,
    ModelMessage,
    ModelProvider,
    ModelResponse,
    ModelSpec,
    ProviderHealth,
    Quantization,
)
from friday.models.router import ModelRouter
from friday.models.registry import ModelEntry, ModelRegistry
from friday.models.provisioning import ModelProvisioner, ProvisionResult
from friday.models.integrity import IntegrityResult, verify_file, compute_sha256

__all__ = [
    "ModelDelta",
    "ModelFormat",
    "ModelMessage",
    "ModelProvider",
    "ModelResponse",
    "ModelRouter",
    "ModelSpec",
    "ProviderHealth",
    "Quantization",
    "ModelEntry",
    "ModelRegistry",
    "ModelProvisioner",
    "ProvisionResult",
    "IntegrityResult",
    "verify_file",
    "compute_sha256",
]
