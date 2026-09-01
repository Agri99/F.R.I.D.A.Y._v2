from __future__ import annotations

from dataclasses import dataclass

import pytest

from friday.config import FridayConfig
from friday.hardware.budget import ResourcePressure
from friday.hardware.manager import HardwareState
from friday.hardware.telemetry import TelemetrySnapshot
from friday.models.base import ModelProvider, ProviderHealth
from friday.models.router import ModelRole, ModelRouter, ModelRoutingError, RoutingContext, TaskComplexity


class FakeProvider(ModelProvider):
    def __init__(self, healthy: bool = True, vision: bool = False):
        self.healthy = healthy
        self.vision = vision

    def generate(self, messages, tools=None, images=None):
        raise NotImplementedError

    def stream(self, messages, tools=None):
        return iter(())

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return self.vision

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.healthy, self.healthy)


@dataclass
class FakeProfile:
    capability_tier: str = "BALANCED"


class FakeHardware:
    def __init__(self, pressure: ResourcePressure = ResourcePressure.NORMAL):
        self.pressure = pressure

    def state(self):
        return HardwareState(FakeProfile(), TelemetrySnapshot(), self.pressure, "balanced.yaml")

    def recommended_models(self):
        return {"fast": "portable-fast"}


def build_router(pressure: ResourcePressure = ResourcePressure.NORMAL) -> ModelRouter:
    return ModelRouter(FridayConfig(), hardware_manager=FakeHardware(pressure))


def test_model_router_routes_low_complexity_to_fast():
    router = build_router()
    fast = FakeProvider()
    router._cache[ModelRole.FAST.value] = fast

    assert router.route(RoutingContext(task_complexity=TaskComplexity.LOW)) is fast


def test_model_router_falls_back_from_unhealthy_reasoning():
    router = build_router()
    router._cache[ModelRole.REASONING.value] = FakeProvider(healthy=False)
    fast = FakeProvider()
    router._cache[ModelRole.FAST.value] = fast

    assert router.route(RoutingContext(task_complexity=TaskComplexity.HIGH)) is fast


def test_model_router_rejects_false_success_when_all_models_unhealthy():
    router = build_router()
    router._cache[ModelRole.REASONING.value] = FakeProvider(healthy=False)
    router._cache[ModelRole.FAST.value] = FakeProvider(healthy=False)

    with pytest.raises(ModelRoutingError, match="No healthy compatible"):
        router.route(RoutingContext(task_complexity=TaskComplexity.HIGH))


def test_model_router_requires_explicit_audio_role():
    router = build_router()

    with pytest.raises(ModelRoutingError, match="audio_role"):
        router.route(RoutingContext(needs_audio=True))


def test_resource_pressure_downgrades_to_fast():
    router = build_router(ResourcePressure.CRITICAL)
    fast = FakeProvider()
    router._cache[ModelRole.FAST.value] = fast

    assert router.route(RoutingContext(task_complexity=TaskComplexity.HIGH)) is fast


def test_vision_route_requires_vision_capability():
    router = build_router()
    router._cache[ModelRole.VISION.value] = FakeProvider(vision=False)
    router._cache[ModelRole.REASONING.value] = FakeProvider(vision=False)
    router._cache[ModelRole.FAST.value] = FakeProvider(vision=False)

    with pytest.raises(ModelRoutingError):
        router.route(RoutingContext(needs_vision=True))
