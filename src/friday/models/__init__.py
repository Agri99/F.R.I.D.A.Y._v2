"""
src/friday/models/__init__.py

WHAT THIS IS FOR:
Exports the key public classes of the models subsystem.
Clients should import from `friday.models`, not internal files.
"""

from __future__ import annotations

from friday.models.base import (
    ModelDelta,
    ModelMessage,
    ModelProvider,
    ModelResponse,
    ProviderHealth,
)
from friday.models.router import ModelRouter

__all__ = [
    "ModelDelta",
    "ModelMessage",
    "ModelProvider",
    "ModelResponse",
    "ProviderHealth",
    "ModelRouter",
]
