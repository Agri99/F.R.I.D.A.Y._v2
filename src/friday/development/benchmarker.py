"""
src/friday/development/benchmarker.py

WHAT THIS IS FOR:
Compares test execution, latency, and verification between candidate and base.
Rejects regressions automatically.
Runbook §59, §63, §84.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenchmarkComparison:
    passed: bool
    candidate_score: float
    base_score: float
    regression_detected: bool
    reason: str
    metrics: dict[str, Any] = field(default_factory=dict)


class UpgradeBenchmarker:
    """Benchmarks an upgrade candidate against baseline thresholds."""

    def __init__(self, min_success_rate: float = 0.95, max_latency_regression_pct: float = 15.0):
        self.min_success_rate = min_success_rate
        self.max_latency_regression_pct = max_latency_regression_pct

    def compare(
        self,
        candidate_passed_tests: int,
        candidate_total_tests: int,
        candidate_duration_s: float,
        base_passed_tests: int = 10,
        base_total_tests: int = 10,
        base_duration_s: float = 5.0,
    ) -> BenchmarkComparison:
        candidate_rate = candidate_passed_tests / max(candidate_total_tests, 1)
        base_rate = base_passed_tests / max(base_total_tests, 1)

        # 1. Did it drop below absolute minimum?
        if candidate_rate < self.min_success_rate:
            return BenchmarkComparison(
                passed=False,
                candidate_score=candidate_rate,
                base_score=base_rate,
                regression_detected=True,
                reason=f"Candidate success rate {candidate_rate:.2%} is below minimum {self.min_success_rate:.2%}",
            )

        # 2. Did it regress compared to base?
        if candidate_rate < base_rate:
            return BenchmarkComparison(
                passed=False,
                candidate_score=candidate_rate,
                base_score=base_rate,
                regression_detected=True,
                reason=f"Candidate success rate {candidate_rate:.2%} regressed from base {base_rate:.2%}",
            )

        # 3. Check extreme latency regression
        if base_duration_s > 0:
            pct_change = ((candidate_duration_s - base_duration_s) / base_duration_s) * 100
            if pct_change > self.max_latency_regression_pct and candidate_duration_s > 10.0:
                return BenchmarkComparison(
                    passed=False,
                    candidate_score=candidate_rate,
                    base_score=base_rate,
                    regression_detected=True,
                    reason=f"Execution time regressed by {pct_change:.1f}% (limit: {self.max_latency_regression_pct}%)",
                )

        return BenchmarkComparison(
            passed=True,
            candidate_score=candidate_rate,
            base_score=base_rate,
            regression_detected=False,
            reason="All benchmarks and regression checks passed",
            metrics={
                "candidate_rate": candidate_rate,
                "base_rate": base_rate,
                "duration_s": candidate_duration_s,
            },
        )


__all__ = ["UpgradeBenchmarker", "BenchmarkComparison"]
