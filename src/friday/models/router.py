"""Hardware-aware model routing behind role-based interfaces."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from friday.config import ModelRoleConfig, Settings
from friday.hardware.budget import ResourcePressure
from friday.models.base import ModelProvider, ModelSpec, Quantization

if TYPE_CHECKING:
    from friday.hardware.manager import HardwareManager
    from friday.hardware.probe import HardwareProfile

from friday.models.cloud_backend import CloudProvider
from friday.models.llamacpp_backend import LlamaCppProvider
from friday.models.ollama_backend import OllamaProvider

PROVIDER_CLASSES: dict[str, type[ModelProvider]] = {
    "ollama": OllamaProvider,
    "llama.cpp": LlamaCppProvider,
    "llamacpp": LlamaCppProvider,
    "cloud": CloudProvider,
}


class ModelRoutingError(RuntimeError):
    """No configured, healthy provider can satisfy a routing request."""


class ModelRole(str, Enum):
    FAST = "fast"
    REASONING = "reasoning"
    VISION = "vision"
    CODE = "code"
    REVIEWER = "reviewer"
    EMBEDDING = "embedding"
    STT = "stt"
    TTS = "tts"


ROLES = [role.value for role in ModelRole]


class TaskComplexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LatencyTarget(str, Enum):
    IMMEDIATE = "immediate"
    FAST = "fast"
    NORMAL = "normal"
    RELAXED = "relaxed"


class ResourceBudget(str, Enum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAXIMUM = "maximum"


@dataclass
class RoutingContext:
    task_complexity: TaskComplexity = TaskComplexity.MEDIUM
    required_role: str | None = None
    needs_vision: bool = False
    audio_role: str | None = None
    needs_audio: bool = False
    latency_target: LatencyTarget = LatencyTarget.NORMAL
    resource_budget: ResourceBudget = ResourceBudget.MEDIUM
    online: bool = True
    prefer_local: bool = True
    max_tokens: int = 4096
    minimum_quantization: Quantization | None = None


class ModelRouter:
    def __init__(self, settings: Settings, hardware_manager: HardwareManager | None = None):
        self._settings = settings
        self._hardware = hardware_manager
        self._cache: dict[str, ModelProvider] = {}
        self._model_specs: dict[str, ModelSpec] = {}
        self._reasoning_preference: str | None = None
        self._fallback_chain = {
            ModelRole.REASONING.value: ModelRole.FAST.value,
            ModelRole.CODE.value: ModelRole.REASONING.value,
            ModelRole.REVIEWER.value: ModelRole.REASONING.value,
            ModelRole.VISION.value: ModelRole.REASONING.value,
        }

    def register_model_spec(self, spec: ModelSpec) -> None:
        key = spec.model_id or f"{spec.family}:{spec.role}:{spec.quantization.value}"
        self._model_specs[key] = spec

    def get_model_spec(self, key: str) -> ModelSpec | None:
        return self._model_specs.get(key)

    def select_quantization(self, role: str, available_memory_gb: float) -> Quantization:
        candidates = [spec for spec in self._model_specs.values() if spec.role == role]
        precision = {
            Quantization.BF16: 5,
            Quantization.FP16: 5,
            Quantization.Q6_K: 4,
            Quantization.Q5_K_M: 3,
            Quantization.Q4_K_M: 2,
        }
        fitting = [spec for spec in candidates if spec.estimated_memory_gb <= available_memory_gb]
        if not fitting:
            return Quantization.Q4_K_M
        return max(fitting, key=lambda spec: precision[spec.quantization]).quantization

    def _role_config(self, role: str) -> ModelRoleConfig:
        config = getattr(self._settings.models, role, None)
        if config is None and role in {ModelRole.CODE.value, ModelRole.REVIEWER.value}:
            config = getattr(self._settings.models, ModelRole.REASONING.value, None)
        if config is None:
            raise ModelRoutingError(f"No model configured for role '{role}'")
        return config

    def _instantiate_provider(self, config: ModelRoleConfig) -> ModelProvider:
        provider_cls = PROVIDER_CLASSES.get(config.provider.lower())
        if provider_cls is None:
            raise ModelRoutingError(f"Unknown model provider '{config.provider}'")
        kwargs: dict[str, Any] = {"model": config.model}
        if config.timeout_seconds is not None:
            kwargs["timeout"] = config.timeout_seconds
        if config.provider.lower() == "cloud":
            kwargs["api_key"] = getattr(self._settings, "cloud_api_key", "")
            if config.base_url:
                kwargs["base_url"] = config.base_url
        elif config.provider.lower() in {"llama.cpp", "llamacpp"}:
            if config.base_url:
                kwargs["base_url"] = config.base_url
            if config.supports_tools is not None:
                kwargs["supports_tools"] = config.supports_tools
            if config.supports_vision is not None:
                kwargs["supports_vision"] = config.supports_vision
        elif config.base_url:
            kwargs["host"] = config.base_url
        return provider_cls(**kwargs)

    def get(self, role: str) -> ModelProvider:
        if role not in self._cache:
            self._cache[role] = self._instantiate_provider(self._role_config(role))
        return self._cache[role]

    def route(self, context: RoutingContext) -> ModelProvider:
        preferred = self._select_preferred_role(context)
        attempted: list[str] = []
        for role in self._roles_to_try(preferred):
            attempted.append(role)
            try:
                provider = self.get(role)
                if self._compatible(provider, role, context):
                    return provider
            except Exception:
                continue
        raise ModelRoutingError(f"No healthy compatible model provider for roles: {', '.join(attempted)}")

    def _roles_to_try(self, preferred: str) -> list[str]:
        roles = [preferred]
        seen = {preferred}
        current = preferred
        while current in self._fallback_chain:
            current = self._fallback_chain[current]
            if current in seen:
                break
            seen.add(current)
            roles.append(current)
        return roles

    def _compatible(self, provider: ModelProvider, role: str, context: RoutingContext) -> bool:
        health = provider.health()
        if not (health.available and health.model_loaded):
            return False
        config = self._role_config(role)
        if not context.online and config.provider.lower() == "cloud":
            return False
        if context.needs_vision and not provider.supports_vision():
            return False
        if context.prefer_local and config.provider.lower() == "cloud":
            return False
        return True

    def set_reasoning_preference(self, preference: str) -> None:
        """Prefer fast or deep reasoning on subsequent routes."""
        if preference not in {"fast", "deep"}:
            raise ModelRoutingError(f"Unknown reasoning preference '{preference}'")
        self._reasoning_preference = preference

    def _select_preferred_role(self, context: RoutingContext) -> str:
        if context.required_role:
            if context.required_role not in ROLES:
                raise ModelRoutingError(f"Unknown model role '{context.required_role}'")
            return context.required_role
        if context.needs_vision:
            return ModelRole.VISION.value
        if context.audio_role:
            if context.audio_role not in {ModelRole.STT.value, ModelRole.TTS.value}:
                raise ModelRoutingError(f"Invalid audio role '{context.audio_role}'")
            return context.audio_role
        if context.needs_audio:
            raise ModelRoutingError("Audio routing requires audio_role='stt' or audio_role='tts'")
        if self._hardware_manager().state().pressure == ResourcePressure.CRITICAL:
            return ModelRole.FAST.value
        # Explicit user preference overrides task complexity.
        if getattr(self, "_reasoning_preference", None) == "fast":
            return ModelRole.FAST.value
        if context.task_complexity == TaskComplexity.LOW:
            return ModelRole.FAST.value
        return ModelRole.REASONING.value

    def route_for_role(self, role: str, context: RoutingContext | None = None) -> ModelProvider:
        routing = context or RoutingContext()
        routing.required_role = role
        return self.route(routing)

    def _hardware_manager(self) -> HardwareManager:
        if self._hardware is None:
            from friday.hardware.manager import HardwareManager
            self._hardware = HardwareManager()
        return self._hardware

    def get_recommended_model(self, role: str) -> str:
        return self._hardware_manager().recommended_models().get(role, "")

    def select_profile(self, hardware: HardwareProfile) -> str:
        from friday.hardware.profile import select_profile

        return select_profile(hardware)

    def auto_configure_from_hardware(self) -> dict[str, str]:
        return self._hardware_manager().recommended_models().copy()

    def get_routing_info(self, context: RoutingContext) -> dict[str, Any]:
        state = self._hardware_manager().state()
        preferred = self._select_preferred_role(context)
        return {
            "hardware_tier": state.profile.capability_tier,
            "resource_pressure": state.pressure.value,
            "selected_profile": state.selected_profile,
            "preferred_role": preferred,
            "fallback_chain": self._roles_to_try(preferred)[1:],
            "recommended_models": self._hardware_manager().recommended_models(),
        }


__all__ = [
    "LatencyTarget",
    "ModelRole",
    "ModelRouter",
    "ModelRoutingError",
    "ResourceBudget",
    "RoutingContext",
    "TaskComplexity",
]
