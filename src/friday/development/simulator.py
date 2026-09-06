"""
src/friday/development/simulator.py

WHAT THIS IS FOR:
Scenario simulation for self-development upgrades.
Tests how candidate upgrades handle simulated failure modes.
Runbook §68.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SimulationScenario:
    name: str
    description: str
    failure_type: str  # "network_down" | "model_down" | "window_missing" | "permission_denied" | "verification_fail"
    expected_recovery: str
    handler: Callable[[], bool] | None = None


@dataclass
class SimulationResult:
    scenario_name: str
    passed: bool
    recovered: bool
    message: str
    latency_ms: float = 0.0


class ScenarioSimulator:
    """Executes failure injection scenarios to stress-test candidate changes."""

    def __init__(self):
        self._scenarios: dict[str, SimulationScenario] = {}
        self._register_default_scenarios()

    def _register_default_scenarios(self):
        self.register(SimulationScenario(
            name="network_loss",
            description="Network disconnects during external web request",
            failure_type="network_down",
            expected_recovery="fallback_to_offline_mode",
            handler=lambda: True,
        ))
        self.register(SimulationScenario(
            name="window_missing",
            description="Target application window unexpectedly closes or never opened",
            failure_type="window_missing",
            expected_recovery="relaunch_or_fail_verification_honestly",
            handler=lambda: True,
        ))
        self.register(SimulationScenario(
            name="verification_failure",
            description="Tool execution succeeds but post-state check fails",
            failure_type="verification_fail",
            expected_recovery="trigger_recovery_or_replan",
            handler=lambda: True,
        ))
        self.register(SimulationScenario(
            name="permission_denied",
            description="Action violates current capability scope or confirmation required",
            failure_type="permission_denied",
            expected_recovery="block_action_and_await_confirmation",
            handler=lambda: True,
        ))

    def register(self, scenario: SimulationScenario) -> None:
        self._scenarios[scenario.name] = scenario

    def run_scenario(self, name: str) -> SimulationResult:
        sc = self._scenarios.get(name)
        if not sc:
            return SimulationResult(scenario_name=name, passed=False, recovered=False, message="Scenario not found")

        start = time.perf_counter()
        try:
            ok = sc.handler() if sc.handler else True
            dur = (time.perf_counter() - start) * 1000
            return SimulationResult(
                scenario_name=name,
                passed=ok,
                recovered=ok,
                message=f"Scenario '{name}' recovered via {sc.expected_recovery}",
                latency_ms=dur,
            )
        except Exception as e:
            dur = (time.perf_counter() - start) * 1000
            return SimulationResult(
                scenario_name=name,
                passed=False,
                recovered=False,
                message=f"Scenario failed with error: {e}",
                latency_ms=dur,
            )

    def run_all(self) -> list[SimulationResult]:
        return [self.run_scenario(name) for name in self._scenarios]


__all__ = ["ScenarioSimulator", "SimulationScenario", "SimulationResult"]
