"""
src/friday/models/router.py

WHAT THIS IS FOR:
Turns a ROLE ("reasoning", "vision", "fast") into a live ModelProvider,
based on config/default.yaml. Handles lazy-loading, health-checking,
automatic fallback, hardware-aware model selection, and specialized model roles.

WHY IT'S BUILT THIS WAY:
Decouples intent from specific models and hardware, aligning with
Principle E (Model portability). Ensures robust execution by checking health.
Supports specialized model roles: fast→simple, reasoning→planning, vision→screen, STT→speech, TTS→synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Type

from friday.config import Settings, ModelRoleConfig
from friday.models.base import ModelProvider
from friday.models.ollama_backend import OllamaProvider
from friday.models.cloud_backend import CloudProvider
from friday.models.hardware import HardwareProfile, detect_hardware, recommend_models_for_tier


# Registry pattern for providers
PROVIDER_CLASSES: dict[str, Type[ModelProvider]] = {
    "ollama": OllamaProvider,
    "cloud": CloudProvider,
}

# Specialized model roles with their capabilities
class ModelRole(Enum):
    FAST = "fast"              # Simple commands, quick responses
    REASONING = "reasoning"    # Complex planning, multi-step tasks
    VISION = "vision"          # Screen understanding, OCR, UI analysis
    EMBEDDING = "embedding"    # Vector embeddings for memory/search
    STT = "stt"                # Speech-to-text transcription
    TTS = "tts"                # Text-to-speech synthesis
    RERANKER = "reranker"      # Re-ranking search results

ROLES = [r.value for r in ModelRole]

# Task complexity levels
class TaskComplexity(Enum):
    LOW = "low"        # Simple: toggle, status, quick query
    MEDIUM = "medium"  # Standard: file ops, search, navigation
    HIGH = "high"      # Complex: multi-step planning, coding, analysis

# Latency targets
class LatencyTarget(Enum):
    IMMEDIATE = "immediate"    # <500ms - for interactive responses
    FAST = "fast"              # <2s - for normal operations
    NORMAL = "normal"          # <10s - for standard tasks
    RELAXED = "relaxed"        # >10s - for heavy computation

# Resource budget tiers
class ResourceBudget(Enum):
    MINIMAL = "minimal"    # Embedded/edge - tiny models only
    LOW = "low"            # Laptop - small models
    MEDIUM = "medium"      # Desktop - medium models
    HIGH = "high"          # Workstation - large models
    MAXIMUM = "maximum"    # Server - massive models


@dataclass
class RoutingContext:
    """Context for routing decisions."""
    task_complexity: TaskComplexity = TaskComplexity.MEDIUM
    needs_vision: bool = False
    needs_audio: bool = False  # STT/TTS
    latency_target: LatencyTarget = LatencyTarget.NORMAL
    resource_budget: ResourceBudget = ResourceBudget.MEDIUM
    online: bool = True
    prefer_local: bool = True
    max_tokens: int = 4096


class ModelRouter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._cache: dict[str, ModelProvider] = {}
        # Allows for fallbacks in case the primary provider for a role is unhealthy
        self._fallback_chain = {
            ModelRole.REASONING.value: ModelRole.FAST.value,
            ModelRole.VISION.value: ModelRole.REASONING.value,
            ModelRole.STT.value: ModelRole.FAST.value,
            ModelRole.TTS.value: ModelRole.FAST.value,
        }

        # Hardware-aware model selection
        self._hardware_profile: HardwareProfile | None = None
        self._model_recommendations: dict[str, str] = {}

    def _detect_hardware_if_needed(self) -> HardwareProfile:
        """Lazy hardware detection."""
        if self._hardware_profile is None:
            self._hardware_profile = detect_hardware()
            self._model_recommendations = recommend_models_for_tier(self._hardware_profile.capability_tier)
        return self._hardware_profile

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

    def get_recommended_model(self, role: str) -> str:
        """Get hardware-recommended model for a role."""
        hw = self._detect_hardware_if_needed()
        return self._model_recommendations.get(role, "")

    def route(self, context: RoutingContext) -> ModelProvider:
        """
        Smart routing based on task requirements, hardware, and health checks.
        Considers: task complexity, vision/audio needs, latency target, resource budget, online status.
        """
        # Determine preferred role based on context
        preferred_role = self._select_preferred_role(context)

        # Try preferred role and fallbacks
        current_role = preferred_role
        while current_role:
            try:
                provider = self.get(current_role)
                health = provider.health()

                if health.available and health.model_loaded:
                    # Check if provider meets requirements
                    if context.needs_vision and not provider.supports_vision():
                        pass  # Fall through to fallback
                    elif context.needs_audio and not (provider.supports_vision() or hasattr(provider, 'supports_audio')):
                        pass  # Fall through to fallback
                    elif not context.online and current_role in self._get_online_only_roles():
                        pass  # Fall through to fallback
                    else:
                        return provider
            except Exception:
                pass

            # Move to fallback role if available
            current_role = self._fallback_chain.get(current_role)
            if not current_role:
                break

        # If all health checks fail or fallbacks exhaust, return the preferred role's provider
        return self.get(preferred_role)

    def _select_preferred_role(self, context: RoutingContext) -> str:
        """Select the best model role for the given context."""
        # Vision tasks always use vision model
        if context.needs_vision:
            return ModelRole.VISION.value

        # Audio tasks
        if context.needs_audio:
            # For TTS we need a TTS model, for STT we need STT model
            # This is handled by the caller specifying the exact role
            pass

        # Complexity-based routing
        if context.task_complexity == TaskComplexity.HIGH:
            return ModelRole.REASONING.value
        elif context.task_complexity == TaskComplexity.LOW:
            return ModelRole.FAST.value
        else:
            return ModelRole.REASONING.value  # Default to reasoning for medium

    def _get_online_only_roles(self) -> set[str]:
        """Roles that require online/cloud models."""
        return {ModelRole.RERANKER.value}  # Reranker typically needs cloud

    def route_for_role(self, role: str, context: RoutingContext | None = None) -> ModelProvider:
        """Route to a specific role with optional context."""
        if context:
            # Validate role is appropriate for context
            if role == ModelRole.VISION.value and not context.needs_vision:
                # Vision model requested but not needed - use reasoning instead
                return self.route(context)
            if role == ModelRole.FAST.value and context.task_complexity == TaskComplexity.HIGH:
                # Fast model requested for complex task - upgrade to reasoning
                context.task_complexity = TaskComplexity.HIGH
                return self.route(context)

        return self.get(role)

    def get_recommended_model(self, role: str) -> str:
        """Get hardware-recommended model for a role."""
        hw = self._detect_hardware_if_needed()
        return self._model_recommendations.get(role, "")

    def select_profile(self, hardware: HardwareProfile) -> str:
        """Select a configuration profile based on detected hardware."""
        if hardware.capability_tier == "LOW":
            return "laptop.yaml"
        elif hardware.capability_tier == "BALANCED":
            return "balanced.yaml"
        elif hardware.capability_tier == "HIGH":
            return "workstation.yaml"
        else:  # MAXIMUM
            return "workstation.yaml"

    def auto_configure_from_hardware(self) -> dict[str, str]:
        """Auto-configure model roles based on detected hardware."""
        hw = self._detect_hardware_if_needed()
        return self._model_recommendations.copy()

    def get_routing_info(self, context: RoutingContext) -> dict[str, Any]:
        """Get detailed routing information for debugging/observability."""
        hw = self._detect_hardware_if_needed()
        preferred = self._select_preferred_role(context)

        return {
            "hardware_tier": hw.capability_tier,
            "preferred_role": preferred,
            "fallback_chain": self._get_fallback_chain(preferred),
            "context": {
                "task_complexity": context.task_complexity.value,
                "needs_vision": context.needs_vision,
                "needs_audio": context.needs_audio,
                "latency_target": context.latency_target.value,
                "resource_budget": context.resource_budget.value,
                "online": context.online,
            },
            "recommended_models": self._model_recommendations,
        }

    def _get_fallback_chain(self, role: str) -> list[str]:
        chain = []
        current = role
        while current in self._fallback_chain:
            current = self._fallback_chain[current]
            chain.append(current)
        return chain
