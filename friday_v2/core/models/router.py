"""
core/models/router.py

WHAT THIS IS FOR:
Turns a ROLE ("reasoning", "vision") into a live ModelProvider,
based on config/default.yaml. The orchestrator calls
`router.get("reasoning")` — it never says "give me qwen3".

WHY IT'S BUILT THIS WAY:
This is the actual abstraction layer Principle E asks for. Adding a
provider = registering it in PROVIDER_CLASSES. Changing which model
answers "reasoning" = editing YAML. No code path elsewhere changes.
"""

from __future__ import annotations

from config.settings import Settings
from core.models.base import ModelProvider
from core.models.ollama_provider import OllamaProvider

PROVIDER_CLASSES = {
    "ollama": OllamaProvider,
}


class ModelRouter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._cache: dict[str, ModelProvider] = {}

    def get(self, role: str) -> ModelProvider:
        if role in self._cache:
            return self._cache[role]

        role_config = getattr(self._settings.models, role, None)
        if role_config is None:
            raise ValueError(f"No model configured for role '{role}'")

        provider_cls = PROVIDER_CLASSES.get(role_config.provider)
        if provider_cls is None:
            raise ValueError(f"Unknown provider '{role_config.provider}' for role '{role}'")

        provider = provider_cls(model=role_config.model)
        self._cache[role] = provider
        return provider
