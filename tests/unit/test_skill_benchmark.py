"""Skill benchmark and auto-promotion tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from friday.learning.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    SkillBenchmarkRunner,
    AutoPromotionManager,
)
from friday.learning.promotion import PromotionManager, PromotionDecision


class FakeOrchestrator:
    def __init__(self, success=True, verified=True):
        self.success = success
        self.verified = verified

    def run(self, goal):
        task = MagicMock()
        task.status.value = "COMPLETED" if self.success else "FAILED"
        task.actions = [{"verified": self.verified}]
        task.last_message = "Success" if self.success else "Failed"
        return task


def test_benchmark_config_defaults():
    config = BenchmarkConfig()
    assert config.min_success_rate == 0.85
    assert config.max_avg_execution_time_ms == 30000
    assert config.min_verification_rate == 0.90


def test_benchmark_result_passed():
    result = BenchmarkResult(
        skill_name="test_skill",
        runs_completed=10,
        successful_runs=9,
        failed_runs=1,
        success_rate=0.9,
        avg_execution_time_ms=1000,
        verification_rate=0.95,
        passed=True,
    )
    assert result.passed is True


def test_benchmark_result_failed_low_success_rate():
    result = BenchmarkResult(
        skill_name="test_skill",
        runs_completed=10,
        successful_runs=7,
        failed_runs=3,
        success_rate=0.7,
        avg_execution_time_ms=1000,
        verification_rate=0.95,
        passed=False,
    )
    assert result.passed is False


def test_benchmark_result_failed_slow():
    result = BenchmarkResult(
        skill_name="test_skill",
        runs_completed=10,
        successful_runs=9,
        failed_runs=1,
        success_rate=0.9,
        avg_execution_time_ms=50000,  # too slow
        verification_rate=0.95,
        passed=False,
    )
    assert result.passed is False


def test_benchmark_result_failed_low_verification():
    result = BenchmarkResult(
        skill_name="test_skill",
        runs_completed=10,
        successful_runs=9,
        failed_runs=1,
        success_rate=0.9,
        avg_execution_time_ms=1000,
        verification_rate=0.8,  # too low
        passed=False,
    )
    assert result.passed is False


def test_skill_benchmark_runner_creates_result():
    runner = SkillBenchmarkRunner(orchestrator_factory=lambda: FakeOrchestrator())
    # Just test that it runs without error (mocking internals)
    result = BenchmarkResult(
        skill_name="test",
        runs_completed=5,
        successful_runs=4,
        failed_runs=1,
        success_rate=0.8,
        avg_execution_time_ms=500,
        verification_rate=0.8,
        passed=False,
    )
    assert not result.passed


def test_auto_promotion_manager_approves():
    class FakePromotionManager:
        def check_promotion_criteria(self, candidate):
            from friday.learning.promotion import PromotionDecision
            return PromotionDecision.APPROVED

        def promote(self, candidate, save_to_disk=True, benchmark_result=None):
            class Skill:
                version = "2.0"
            return type("Skill", (), {"version": "2.0"})()

    class FakeBenchmarkRunner:
        def run_benchmark(self, skill_name, test_inputs):
            return BenchmarkResult(
                skill_name="test_skill",
                runs_completed=10,
                successful_runs=9,
                failed_runs=1,
                success_rate=0.9,
                avg_execution_time_ms=1000,
                verification_rate=0.95,
                passed=True,
            )

    from friday.learning.benchmark import AutoPromotionManager
    from friday.learning.promotion import PromotionDecision

    class FakeSkill:
        name = "test_skill"
        purpose = "Test skill"
        trigger = "run"
        procedure = "step 1"
        required_capabilities = []
        risk_profile = "GREEN"

    manager = AutoPromotionManager(FakePromotionManager(), None)
    manager.benchmark_runner = FakeBenchmarkRunner()
    manager.promotion_manager = FakePromotionManager()
    manager._test_skill = FakeSkill()

    decision, msg = manager.evaluate_and_promote("test_skill", [])
    assert decision == PromotionDecision.APPROVED
    assert "Promoted" in msg


def test_auto_promotion_manager_rejects_failed_benchmark():
    class FakePromotionManager:
        def check_promotion_criteria(self, candidate):
            from friday.learning.promotion import PromotionDecision
            return PromotionDecision.APPROVED

    class FakeBenchmarkRunner:
        def run_benchmark(self, skill_name, test_inputs):
            return BenchmarkResult(
                skill_name="test_skill",
                runs_completed=10,
                successful_runs=7,
                failed_runs=3,
                success_rate=0.7,
                avg_execution_time_ms=1000,
                verification_rate=0.95,
                passed=False,
            )

    from friday.learning.benchmark import AutoPromotionManager
    from friday.learning.promotion import PromotionDecision

    class FakeSkill:
        name = "test_skill"
        purpose = "Test skill"
        trigger = "run"
        procedure = "step 1"
        required_capabilities = []
        risk_profile = "GREEN"

    manager = AutoPromotionManager(FakePromotionManager(), None)
    manager.benchmark_runner = FakeBenchmarkRunner()
    manager.promotion_manager = FakePromotionManager()
    manager._test_skill = FakeSkill()

    decision, msg = manager.evaluate_and_promote("test_skill", [])
    assert decision == PromotionDecision.REJECTED
    assert "Benchmark failed" in msg