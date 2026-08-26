"""
src/friday/models/router.py

WHAT THIS IS FOR:
Turns a ROLE ("reasoning", "vision", "fast") into a live ModelProvider,
based on config/default.yaml. Handles lazy-loading, health-checking,
and automatic fallback (e.g., if reasoning is down, try fast).

WHY IT'S BUILT THIS WAY:
Decouples intent from specific models and hardware, aligning with
Principle E (Model portability). Ensures robust execution by checking health.
"""

from __future__ import annotations

from typing import Type

from friday.config import Settings, ModelRoleConfig
from friday.models.base import ModelProvider
from friday.models.ollama_backend import OllamaProvider
from friday.models.cloud_backend import CloudProvider


# Registry pattern for providers
PROVIDER_CLASSES: dict[str, Type[ModelProvider]] = {
    "ollama": OllamaProvider,
    "cloud": CloudProvider,
}


class ModelRouter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._cache: dict[str, ModelProvider] = {}
        # Allows for fallbacks in case the primary provider for a role is unhealthy
        self._fallback_chain = {
            "reasoning": "fast",
            "vision": "reasoning"
        }

    def _instantiate_provider(self, role_config: ModelRoleConfig) -> ModelProvider:
        provider_cls = PROVIDER_CLASSES.get(role_config.provider)
        if provider_cls is None:
            raise ValueError(f"Unknown provider '{role_config.provider}'")

        # Basic instantiation, assuming constructor accepts model. 
        # In a real app we might pass kwargs based on provider type.
        if role_config.provider == "cloud":
            # Just an example of fetching API keys safely from config
            api_key = getattr(self._settings, "cloud_api_key", "dummy-key")
            return provider_cls(model=role_config.model, api_key=api_key)
        else:
            return provider_cls(model=role_config.model)

    def get(self, role: str) -> ModelProvider:
        """Get a provider by role, using lazy loading."""
        if role in self._cache:
            return self._cache[role]

        models_config = getattr(self._settings, "models", None)
        if models_config is None:
            raise ValueError("Settings has no 'models' configuration")

        role_config = getattr(models_config, role, None)
        if role_config is None:
            raise ValueError(f"No model configured for role '{role}'")

        provider = self._instantiate_provider(role_config)
        self._cache[role] = provider
        return provider

    def route(self, task_complexity: str, needs_vision: bool = False) -> ModelProvider:
        """
        Smart routing based on task requirements and health checks.
        Task complexity can be 'high' (reasoning) or 'low' (fast).
        """
        preferred_role = "reasoning" if task_complexity == "high" else "fast"
        if needs_vision:
            preferred_role = "vision"

        current_role = preferred_role
        while current_role:
            try:
                provider = self.get(current_role)
                health = provider.health()
                
                if health.available and health.model_loaded:
                    if needs_vision and not provider.supports_vision():
                        # If vision is strictly required but not supported, fallback
                        pass
                    else:
                        return provider
            except Exception:
                pass
            
            # Move to fallback role if available
            current_role = self._fallback_chain.get(current_role)
            if not current_role:
                break
                
        # If all health checks fail or fallbacks exhaust, return the preferred role's provider
        # and let the caller deal with the Exception when they try to use it.
        return self.get(preferred_role)
