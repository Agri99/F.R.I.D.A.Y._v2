"""Plugin manifest parsing and validation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{1,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
_VALID_RISKS = {"GREEN", "YELLOW", "ORANGE", "RED"}


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    api_version: int
    entrypoint: str
    risk: str = "RED"
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "PluginManifest":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Plugin manifest must be a YAML mapping")
        manifest = cls.from_dict(data)
        manifest.validate()
        return manifest

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        return cls(
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            api_version=int(data.get("api_version", 0)),
            entrypoint=str(data.get("entrypoint", "")),
            risk=str(data.get("risk", "RED")).upper(),
            capabilities=tuple(str(cap) for cap in data.get("capabilities", [])),
            description=str(data.get("description", "")),
        )

    def validate(self) -> None:
        if not _NAME_RE.fullmatch(self.name):
            raise ValueError(f"Invalid plugin name: {self.name!r}")
        if not _VERSION_RE.fullmatch(self.version):
            raise ValueError(f"Invalid plugin version: {self.version!r}")
        if self.api_version < 1:
            raise ValueError("Plugin api_version must be at least 1")
        if self.entrypoint.count(":") != 1:
            raise ValueError("Plugin entrypoint must use 'module:factory' format")
        if self.risk not in _VALID_RISKS:
            raise ValueError(f"Invalid plugin risk: {self.risk}")
        if not self.capabilities:
            raise ValueError("Plugin must declare at least one capability")
