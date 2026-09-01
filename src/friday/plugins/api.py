"""Stable plugin API exposed by the trusted core."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from friday.plugins.manifest import PluginManifest


@dataclass
class PluginContext:
    granted_capabilities: frozenset[str]
    services: dict[str, Any] = field(default_factory=dict)

    def require(self, capability: str) -> None:
        if capability not in self.granted_capabilities:
            raise PermissionError(f"Plugin capability not granted: {capability}")


class Plugin(ABC):
    manifest: PluginManifest

    @abstractmethod
    def activate(self, context: PluginContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def deactivate(self) -> None:
        raise NotImplementedError

    def health(self) -> bool:
        return True
