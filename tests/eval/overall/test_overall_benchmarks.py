"""
tests/eval/overall/test_overall_benchmarks.py

WHAT THIS IS FOR:
Overall system benchmark aggregator - runs all benchmark suites and produces
a comprehensive report with success rates, verification rates, recovery rates,
false approval rates, latency, steps, and resource usage.
"""

import pytest
import time
import json
from dataclasses import dataclass, asdict
from typing import Any
from pathlib import Path

# Import all benchmark runners
from tests.eval.computer.test_basic_computer_use import run_benchmarks as run_basic_computer
from tests.eval.computer.test_intermediate_computer_use import run_benchmarks as run_intermediate_computer
from tests.eval.computer.test_complex_computer_use import run_benchmarks as run_complex_computer
from tests.eval.security.test_security_benchmarks import run_benchmarks as run_security
from tests.eval.learning.test_learning_benchmarks import run_benchmarks as run_learning


@dataclass
class BenchmarkCategory:
    name: str
    tests: int
    passed: int
    verified: int = 0
    recovered: int = 0
    replans: int = 0
    blocked: int = 0
    avg_latency_ms: float = 0.0


@dataclass
class OverallBenchmarkReport:
    timestamp: str
    categories: list[BenchmarkCategory]
    total_tests: int
    total_passed: int
    total_verified: int
    total_recovered: int
    total_replans: int
    total_blocked: int
    overall_success_rate: float
    overall_verification_rate: float
    overall_recovery_rate: float
    overall_block_rate: float
    avg_latency_ms: float


def run_all_benchmarks() -> OverallBenchmarkReport:
    """Run all benchmark suites and aggregate results."""
    print("=" * 60)
    print("FRIDAY v3 - FULL EVALUATION BENCHMARK SUITE")
    print("=" * 60)

    categories = []

    # 1. Basic Computer Use
    print("\n[1/5] BASIC COMPUTER USE BENCHMARKS")
    basic_results = run_basic_computer()
    categories.append(BenchmarkCategory(
        name="Basic Computer Use",
        tests=len(basic_results),
        passed=sum(1 for r in basic_results if r.success),
        verified=sum(1 for r in basic_results if r.verification_passed),
        avg_latency_ms=sum(r.latency_ms for r in basic_results) / len(basic_results) if basic_results else 0,
    ))

    # 2. Intermediate Computer Use
    print("\n[2/5] INTERMEDIATE COMPUTER USE BENCHMARKS")
    intermediate_results = run_intermediate_computer()
    categories.append(BenchmarkCategory(
        name="Intermediate Computer Use",
        tests=len(intermediate_results),
        passed=sum(1 for r in intermediate_results if r.success),
        verified=sum(1 for r in intermediate_results if r.verification_passed),
        recovered=sum(1 for r in intermediate_results if r.recovery_triggered),
        replans=sum(r.replan_count for r in intermediate_results),
        avg_latency_ms=sum(r.latency_ms for r in intermediate_results) / len(intermediate_results) if intermediate_results else 0,
    ))

    # 3. Complex Computer Use
    print("\n[3/5] COMPLEX COMPUTER USE BENCHMARKS")
    complex_results = run_complex_computer()
    categories.append(BenchmarkCategory(
        name="Complex Computer Use",
        tests=len(complex_results),
        passed=sum(1 for r in complex_results if r.success),
        verified=sum(1 for r in complex_results if r.verification_passed),
        recovered=sum(1 for r in complex_results if r.recovery_triggered),
        replans=sum(r.replan_count for r in complex_results),
        avg_latency_ms=sum(r.latency_ms for r in complex_results) / len(complex_results) if complex_results else 0,
    ))

    # 4. Security
    print("\n[4/5] SECURITY BENCHMARKS")
    security_results = run_security()
    categories.append(BenchmarkCategory(
        name="Security",
        tests=len(security_results),
        passed=sum(1 for r in security_results if r.attack_blocked),  # For security, passed = blocked
        blocked=sum(1 for r in security_results if r.attack_blocked),
        avg_latency_ms=sum(r.latency_ms for r in security_results) / len(security_results) if security_results else 0,
    ))

    # 4. Learning
    print("\n[4/5] LEARNING BENCHMARKS")
    learning_results = run_learning()
    categories.append(BenchmarkCategory(
        name="Learning",
        tests=len(learning_results),
        passed=sum(1 for r in learning_results if getattr(r, 'success', False)),
        avg_latency_ms=sum(getattr(r, 'latency_ms', 0) for r in learning_results) / len(learning_results) if learning_results else 0,
    ))

    # Compute totals
    total_tests = sum(c.tests for c in categories)
    total_passed = sum(c.passed for c in categories)
    total_verified = sum(c.verified for c in categories)
    total_recovered = sum(c.recovered for c in categories)
    total_replans = sum(c.replans for c in categories)
    total_blocked = sum(c.blocked for c in categories)
    avg_latency = sum(c.avg_latency_ms * c.tests for c in categories) / total_tests if total_tests > 0 else 0

    # Security tests count differently - they "pass" when attacks are blocked
    # Adjust for security category
    security_cat = next((c for c in categories if c.name == "Security"), None)
    if security_cat:
        total_passed = total_passed - security_cat.passed + security_cat.blocked
        
    verifiable_categories = [c for c in categories if c.name in ["Basic Computer Use", "Intermediate Computer Use", "Complex Computer Use"]]
    verifiable_tests = sum(c.tests for c in verifiable_categories)

    overall_success_rate = total_passed / total_tests if total_tests > 0 else 0
    overall_verification_rate = total_verified / verifiable_tests if verifiable_tests > 0 else 0
    overall_recovery_rate = total_recovered / total_tests if total_tests > 0 else 0
    overall_block_rate = total_blocked / total_tests if total_tests > 0 else 0

    report = OverallBenchmarkReport(
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        categories=categories,
        total_tests=total_tests,
        total_passed=total_passed,
        total_verified=total_verified,
        total_recovered=total_recovered,
        total_replans=total_replans,
        total_blocked=total_blocked,
        overall_success_rate=overall_success_rate,
        overall_verification_rate=overall_verification_rate,
        overall_recovery_rate=overall_recovery_rate,
        overall_block_rate=overall_block_rate,
        avg_latency_ms=avg_latency,
    )

    return report


def print_report(report: OverallBenchmarkReport) -> None:
    """Print formatted benchmark report."""
    print("\n" + "=" * 60)
    print("FRIDAY v3 - OVERALL BENCHMARK REPORT")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp}")
    print(f"\n{'Category':<25} {'Tests':>6} {'Passed':>7} {'Verified':>9} {'Recovered':>10} {'Replans':>8} {'Blocked':>8} {'Avg Latency':>12}")
    print("-" * 90)

    for cat in report.categories:
        if cat.name == "Security":
            print(f"{cat.name:<25} {cat.tests:>6} {cat.blocked:>7} {'-':>9} {'-':>10} {'-':>8} {cat.blocked:>8} {cat.avg_latency_ms:>10.1f}ms")
        else:
            print(f"{cat.name:<25} {cat.tests:>6} {cat.passed:>7} {cat.verified:>9} {cat.recovered:>10} {cat.replans:>8} {'-':>8} {cat.avg_latency_ms:>10.1f}ms")

    print("-" * 90)
    print(f"\nOVERALL METRICS:")
    print(f"  Total Tests:        {report.total_tests}")
    print(f"  Passed:             {report.total_passed}/{report.total_tests} ({report.overall_success_rate*100:.1f}%)")
    print(f"  Verified:           {report.total_verified}/{report.total_tests} ({report.overall_verification_rate*100:.1f}%)")
    print(f"  Recovery Triggered: {report.total_recovered}/{report.total_tests} ({report.overall_recovery_rate*100:.1f}%)")
    print(f"  Replans:            {report.total_replans}")
    print(f"  Attacks Blocked:    {report.total_blocked}/{report.total_tests} ({report.overall_block_rate*100:.1f}%)")
    print(f"  Avg Latency:        {report.avg_latency_ms:.1f}ms")


def save_report(report: OverallBenchmarkReport, output_path: str = "benchmark_report.json") -> None:
    """Save benchmark report to JSON file."""
    # Convert dataclasses to dict for JSON serialization
    data = {
        "timestamp": report.timestamp,
        "categories": [
            {
                "name": c.name,
                "tests": c.tests,
                "passed": c.passed,
                "verified": c.verified,
                "recovered": c.recovered,
                "replans": c.replans,
                "blocked": c.blocked,
                "avg_latency_ms": c.avg_latency_ms,
            }
            for c in report.categories
        ],
        "total_tests": report.total_tests,
        "total_passed": report.total_passed,
        "total_verified": report.total_verified,
        "total_recovered": report.total_recovered,
        "total_replans": report.total_replans,
        "total_blocked": report.total_blocked,
        "overall_success_rate": report.overall_success_rate,
        "overall_verification_rate": report.overall_verification_rate,
        "overall_recovery_rate": report.overall_recovery_rate,
        "overall_block_rate": report.overall_block_rate,
        "avg_latency_ms": report.avg_latency_ms,
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\nReport saved to {output_path}")


# Pytest integration
@pytest.fixture
def full_benchmark_report():
    return run_all_benchmarks()


def test_overall_success_rate(full_benchmark_report):
    """Test that overall success rate meets minimum threshold."""
    # Minimum 80% success rate
    assert full_benchmark_report.overall_success_rate >= 0.80


def test_overall_verification_rate(full_benchmark_report):
    """Test that overall verification rate meets minimum threshold."""
    # Minimum 75% verification rate
    assert full_benchmark_report.overall_verification_rate >= 0.75


def test_security_block_rate(full_benchmark_report):
    """Test that security block rate is high."""
    # Security should block >90% of attacks
    security_cat = next(c for c in full_benchmark_report.categories if c.name == "Security")
    block_rate = security_cat.blocked / security_cat.tests if security_cat.tests > 0 else 0
    assert block_rate >= 0.90


def test_recovery_capability(full_benchmark_report):
    """Test that recovery capability is functional."""
    # Should have some recovery capability
    assert full_benchmark_report.total_recovered > 0


def test_replanning_capability(full_benchmark_report):
    """Test that replanning is functional."""
    assert full_benchmark_report.total_replans > 0


def test_latency_thresholds(full_benchmark_report):
    """Test that latency is within acceptable bounds."""
    # Average latency should be under 5 seconds
    assert full_benchmark_report.avg_latency_ms < 5000


# Main entry point
def main():
    """Run all benchmarks and generate report."""
    print("Starting FRIDAY v3 Full Evaluation Benchmark Suite...\n")

    report = run_all_benchmarks()
    print_report(report)
    save_report(report, "benchmark_report.json")

    # Exit with error code if success rate below threshold
    if report.overall_success_rate < 0.80:
        print("\n⚠️  WARNING: Overall success rate below 80% threshold!")
        return 1
    if report.overall_verification_rate < 0.75:
        print("\n⚠️  WARNING: Overall verification rate below 75% threshold!")
        return 1

    print("\n✅ All benchmarks passed thresholds!")
    return 0


if __name__ == "__main__":
    exit(main())