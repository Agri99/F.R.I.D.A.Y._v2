"""
Configuration definitions and loading logic for F.R.I.D.A.Y. v2.

Uses Pydantic for validation and structured access to application settings.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import yaml
from pydantic import BaseModel, Field

class AppConfig(BaseModel):
    name: str = "FRIDAY"
    offline_first: bool = True
    autonomy_level: int = 2

class NetworkConfig(BaseModel):
    assume_online: bool = False
    probe_interval_seconds: int = 30
    probe_urls: List[str] = Field(default_factory=list)

class ModelDef(BaseModel):
    provider: str
    model: str
    base_url: str | None = None
    timeout_seconds: int | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None

class ModelsConfig(BaseModel):
    fast: ModelDef
    reasoning: ModelDef
    vision: ModelDef
    code: ModelDef | None = None
    reviewer: ModelDef | None = None
    embedding: ModelDef | None = None
    stt: ModelDef | None = None
    tts: ModelDef | None = None

class RuntimeConfig(BaseModel):
    max_task_steps: int = 20
    max_retries_per_step: int = 2
    tool_timeout_seconds: int = 30
    max_recording_seconds: int = 18
    context_window_messages: int = 40
    keep_recent_messages: int = 30

class VoiceConfig(BaseModel):
    wake_word: str = "FRIDAY"
    stt_model: str = "small"
    tts_voice: str = "en_GB-jenny_dioco-medium"
    barge_in: bool = True
    followup_window_seconds: float = 5.0

class SecurityConfig(BaseModel):
    default_risk_tier: str = "RED"
    auto_approve_tiers: List[str] = Field(default_factory=lambda: ["GREEN"])
    confirm_required_tiers: List[str] = Field(default_factory=lambda: ["YELLOW", "ORANGE"])
    hard_block_without_second_factor: List[str] = Field(default_factory=lambda: ["RED"])
    default_filesystem_root: str = "./workspace"
    require_voice_auth_for_orange: bool = True
    require_passphrase_for_red: bool = True
    confirmation_ttl_seconds: int = 60

class LearningConfig(BaseModel):
    enabled: bool = True
    auto_create_skills: bool = True
    auto_promote_skills: bool = False
    require_validation: bool = True

class BrowserConfig(BaseModel):
    enabled: bool = True
    engine: str = "playwright"

class GoogleConfig(BaseModel):
    gmail_enabled: bool = True
    calendar_enabled: bool = True

class PathsConfig(BaseModel):
    data_dir: str = "./data"
    audit_dir: str = "./data/audit"
    trajectories_dir: str = "./data/trajectories"
    skills_dir: str = "./skills"
    secrets_dir: str = "./secrets"
    workspace_dir: str = "./workspace"
    models_dir: str = "./models"

class FridayConfig(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    models: ModelsConfig = Field(
        default_factory=lambda: ModelsConfig(
            fast=ModelDef(provider="ollama", model="qwen3:4b"),
            reasoning=ModelDef(provider="ollama", model="qwen3:8b"),
            vision=ModelDef(provider="ollama", model="qwen3-vl:8b"),
        )
    )
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)

    security: SecurityConfig = Field(default_factory=SecurityConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    def ensure_dirs(self) -> None:
        """Create all necessary directories."""
        dirs = [
            self.paths.data_dir,
            self.paths.audit_dir,
            self.paths.trajectories_dir,
            self.paths.skills_dir,
            self.paths.secrets_dir,
            self.paths.workspace_dir,
            self.paths.models_dir
        ]
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)

    @classmethod
    def _dict_merge(cls, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries."""
        merged = base.copy()
        for k, v in override.items():
            if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                merged[k] = cls._dict_merge(merged[k], v)
            else:
                merged[k] = v
        return merged

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "FridayConfig":
        """Load configuration, applying environment overrides if present."""
        if not config_path:
            # Default to the default.yaml next to this file, or similar
            config_path = str(Path(__file__).parent.parent.parent / "config" / "default.yaml")
        
        base_path = Path(config_path)
        config_data = {}
        if base_path.exists():
            with open(base_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
                
        # Handle overlays
        env = os.environ.get("FRIDAY_ENV")
        if env:
            env_path = base_path.parent / f"{env}.yaml"
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    env_data = yaml.safe_load(f) or {}
                    config_data = cls._dict_merge(config_data, env_data)
        
        config = cls(**config_data)
        return config

Settings = FridayConfig
ModelRoleConfig = ModelDef

__all__ = ["FridayConfig", "Settings", "AppConfig", "NetworkConfig", "ModelsConfig", "ModelDef", "ModelRoleConfig", "RuntimeConfig", "VoiceConfig", "SecurityConfig", "LearningConfig", "BrowserConfig", "GoogleConfig", "PathsConfig"]
