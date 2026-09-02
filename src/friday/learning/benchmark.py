"""Skill benchmark runner for auto-promotion evaluation."""
from __future__ import annotations

import time
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from pathlib import Path

from friday.learning.promotion import PromotionManager, PromotionDecision
from friday.learning.optimizer import SkillOptimizer
from friday.learning.trajectory import Trajectory
from friday.skills.loader import SkillLoader
from friday.skills.registry import SkillRegistry


@dataclass
class BenchmarkConfig:
    """Configuration for skill benchmarking."""
    min_runs: int = 5
    max_runs: int = 20
    min_success_rate: float = 0.85
    max_avg_execution_time_ms: float = 30000.0  # 30 seconds
    min_verification_rate: float = 0.90
    max_regression_threshold: float = 0.10  # 10% drop


@dataclass
class BenchmarkResult:
    """Results of a skill benchmark run."""
    skill_name: str
    runs_completed: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    avg_execution_time_ms: float
    verification_rate: float
    avg_tokens_used: float = 0.0
    passed: bool = False
    details: list[str] = field(default_factory=list)


class SkillBenchmarkRunner:
    """Runs benchmarks on skills to evaluate promotion readiness."""

    def __init__(
        self,
        config: BenchmarkConfig | None = None,
        skill_registry: SkillRegistry | None = None,
        orchestrator_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.config = config or BenchmarkConfig()
        self.skill_registry = skill_registry or SkillRegistry()
        self.orchestrator_factory = orchestrator_factory

    def run_benchmark(self, skill_name: str, test_inputs: list[dict[str, Any]]) -> BenchmarkResult:
        """Run benchmark on a skill with given test inputs."""
        skill = self._load_skill(skill_name)
        if not skill:
            return BenchmarkResult(
                skill_name=skill_name,
                runs_completed=0,
                successful_runs=0,
                failed_runs=0,
                success_rate=0.0,
                avg_execution_time_ms=0.0,
                verification_rate=0.0,
                passed=False,
                details=[f"Skill '{skill_name}' not found in registry"]
            )

        if not self.orchestrator_factory:
            return BenchmarkResult(
                skill_name=skill_name,
                runs_completed=0,
                successful_runs=0,
                failed_runs=0,
                success_rate=0.0,
                avg_execution_time_ms=0.0,
                verification_rate=0.0,
                passed=False,
                details=["No orchestrator factory provided for benchmarking"]
            )

        orchestrator = self.orchestrator_factory()
        runs = min(self.config.max_runs, len(test_inputs))
        if runs < self.config.min_runs:
            runs = self.config.min_runs

        successful = 0
        total_time = 0.0
        verification_passes = 0
        details: list[str] = []

        for i in range(runs):
            test_input = test_inputs[i % len(test_inputs)]
            start = time.perf_counter()

            try:
                result = self._run_skill(skill, test_input)
                duration = time.perf_counter() - start

                if result.get("success", False):
                    successful += 1
                    total_time += duration * 1000  # ms
                    if result.get("verified", False):
                        verification_passes += 1
                    details.append(f"Run {i+1}: PASS ({duration*1000:.1f}ms)")
                else:
                    details.append(f"Run {i+1}: FAIL - {result.get('error', 'Unknown error')}")
            except Exception as e:
                details.append(f"Run {i+1}: EXCEPTION - {e}")

        runs_completed = runs
        successful_runs = successful
        failed_runs = runs_completed - successful
        success_rate = successful_runs / runs_completed if runs_completed > 0 else 0.0
        avg_time = total_time / successful_runs if successful_runs > 0 else 0.0
        verification_rate = verification_passes / runs_completed if runs_completed > 0 else 0.0

        passed = (
            success_rate >= self.config.min_success_rate
            and avg_time <= self.config.max_avg_execution_time_ms
            and verification_rate >= self.config.min_verification_rate
        )

        return BenchmarkResult(
            skill_name=skill_name,
            runs_completed=runs_completed,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            success_rate=success_rate,
            avg_execution_time_ms=avg_time,
            verification_rate=verification_rate,
            passed=passed,
            details=details
        )

    def _load_skill(self, skill_name: str) -> Any:
        if self.skill_registry:
            return self.skill_registry.get(skill_name)
        loader = SkillLoader()
        return loader.load_skill(f"skills/learned/{skill_name}.md")

    def _run_skill(self, skill: Any, inputs: dict) -> dict:
        """Run a skill via orchestrator and return structured result."""
        if not self.orchestrator_factory:
            return {"success": False, "error": "No orchestrator factory"}

        orchestrator = self.orchestrator_factory()
        try:
            task = orchestrator.run(f"Run skill {skill.name} with {inputs}")
            return {
                "success": task.status.value in ("COMPLETED", "DONE", "SUCCESS"),
                "verified": task.actions[-1].get("verified", False) if task.actions else False,
                "error": task.last_message if task.status.value not in ("COMPLETED", "DONE") else None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class AutoPromotionManager:
    """Manages automatic skill promotion based on benchmark results."""

    def __init__(
        self,
        promotion_manager: Any,
        benchmark_runner: "SkillBenchmarkRunner",
        config: BenchmarkConfig | None = None,
    ) -> None:
        self.promotion_manager = promotion_manager
        self.benchmark_runner = benchmark_runner
        self.config = config or BenchmarkConfig()

    def evaluate_and_promote(self, skill_name: str, test_inputs: list[dict]) -> tuple[PromotionDecision, str]:
        """Run benchmark and auto-promote if criteria met."""
        from friday.learning.promotion import PromotionDecision

        # Allow skill to be provided directly for testing
        skill = getattr(self, '_test_skill', None)
        if skill is None:
            # First check standard promotion criteria
            from friday.skills.loader import SkillLoader
            loader = SkillLoader()
            skill = loader.load_skill(f"skills/learned/{skill_name}.md")

        if not skill:
            return PromotionDecision.REJECTED, f"Skill '{skill_name}' not found"

        # Create candidate from skill
        from friday.skills.learner import SkillCandidate
        candidate = self._skill_to_candidate(skill)

        decision = self.promotion_manager.check_promotion_criteria(candidate)
        if decision != PromotionDecision.APPROVED:
            return decision, f"Standard promotion check failed: {decision.value}"

        # Run benchmark
        benchmark_result = self.benchmark_runner.run_benchmark(skill_name, [])

        if benchmark_result.passed:
            # Promote the skill
            promoted_skill = self.promotion_manager.promote(candidate)
            return PromotionDecision.APPROVED, f"Promoted to v{promoted_skill.version} (benchmark passed)"
        else:
            return PromotionDecision.REJECTED, f"Benchmark failed: success_rate={benchmark_result.success_rate:.2f}, time={benchmark_result.avg_execution_time_ms:.0f}ms"

    def _skill_to_candidate(self, skill: Any) -> Any:
        """Convert loaded Skill to SkillCandidate for promotion."""
        from friday.skills.learner import SkillCandidate
        return SkillCandidate(
            proposed_name=skill.name,
            purpose=skill.purpose,
            triggers=[skill.trigger] if skill.trigger else ["run"],
            procedure=skill.procedure,
            required_capabilities=skill.required_capabilities,
            risk_profile=skill.risk_profile,
        )


__all__ = [
    "BenchmarkConfig",
    "BenchmarkResult",
    "SkillBenchmarkRunner",
    "AutoPromotionManager",
]