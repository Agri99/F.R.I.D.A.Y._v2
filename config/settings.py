"""
config/settings.py

WHAT THIS IS FOR:
The single place FRIDAY reads its configuration from. Everything else
in the codebase (model router, policy engine, tool registry) takes a
`Settings` object instead of reading files or env vars directly.

WHY IT'S BUILT THIS WAY:
Pydantic validates the YAML shape at startup. If someone typos a key
or forgets one, FRIDAY refuses to boot instead of crashing three
layers deep at 2am mid-task. That's "fail closed" (Principle G)
applied to configuration itself, not just to actions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class ModelRoleConfig(BaseModel):
    provider: str
    model: str


class ModelsConfig(BaseModel):
    reasoning: ModelRoleConfig
    vision: ModelRoleConfig


class SecurityConfig(BaseModel):
    default_risk_tier: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    auto_approve_tiers: list[str]
    confirm_required_tiers: list[str]
    hard_block_without_second_factor: list[str]


class PathsConfig(BaseModel):
    data_dir: str
    audit_log: str
    skills_dir: str


class AppConfig(BaseModel):
    name: str
    offline_first: bool


class NetworkConfig(BaseModel):
    assume_online: bool


class Settings(BaseModel):
    app: AppConfig
    network: NetworkConfig
    models: ModelsConfig
    security: SecurityConfig
    paths: PathsConfig

    @classmethod
    def load(cls, path: str | Path = "config/default.yaml") -> "Settings":
        raw = yaml.safe_load(Path(path).read_text())
        return cls.model_validate(raw)

    def ensure_dirs(self) -> None:
        Path(self.paths.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.paths.skills_dir).mkdir(parents=True, exist_ok=True)
