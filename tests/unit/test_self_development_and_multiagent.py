"""
tests/unit/test_self_development_and_multiagent.py

WHAT THIS IS FOR:
Unit tests for:
  - M8: Self-Development pipeline (worktree, patcher, reviewer, tester, simulator, benchmarker, canary, rollback, manager)
  - M9: Model registry, provisioning, and integrity
  - M11: Multi-Agent subsystem (coordinator, researcher, computer, coder, reviewer)
"""
import pytest
from pathlib import Path

from friday.development import (
    BenchmarkComparison,
    CanaryState,
    CodeReviewer,
    IsolatedTester,
    PatcherError,
    ProposalGenerator,
    SafePatcher,
    ScenarioSimulator,
    SelfDevelopmentManager,
    UpgradeBenchmarker,
    UpgradeCandidate,
    UpgradeRollback,
    UpgradeStage,
    WorktreeManager,
)
from friday.models import (
    IntegrityResult,
    ModelEntry,
    ModelProvisioner,
    ModelRegistry,
    compute_sha256,
    verify_file,
)
from friday.agent import (
    CoderSpecialist,
    ComputerSpecialist,
    MultiAgentCoordinator,
    ResearcherSpecialist,
    ReviewerSpecialist,
    SpecialistRole,
)


# ---------------------------------------------------------------------------
# M9: Models Registry & Integrity
# ---------------------------------------------------------------------------

def test_model_registry_crud(tmp_path):
    reg = ModelRegistry()
    entry = ModelEntry(
        id="test-model:1b",
        provider="ollama",
        role="fast",
        model="test-model:1b",
        ram_estimate_gb=2.0,
    )
    reg.register(entry)

    assert reg.get("test-model:1b") is not None
    assert len(reg.by_role("fast")) == 1

    reg.mark_installed("test-model:1b", True)
    reg.update_health("test-model:1b", "HEALTHY")
    assert reg.best_for_role("fast").id == "test-model:1b"

    save_file = tmp_path / "reg.json"
    reg.save(save_file)
    loaded = ModelRegistry.load(save_file)
    assert loaded.get("test-model:1b") is not None


def test_model_integrity_verification(tmp_path):
    test_file = tmp_path / "weights.bin"
    test_file.write_bytes(b"mock weights content 12345")

    sha = compute_sha256(test_file)
    assert len(sha) == 64

    # Matching sha
    res = verify_file(test_file, expected_sha256=sha, expected_size_bytes=len(b"mock weights content 12345"))
    assert res.ok is True

    # Mismatched sha
    res_bad = verify_file(test_file, expected_sha256="0" * 64)
    assert res_bad.ok is False

    # Non-existent file
    res_missing = verify_file(tmp_path / "absent.bin", expected_sha256=sha)
    assert res_missing.ok is False


# ---------------------------------------------------------------------------
# M8: Self-Development Components
# ---------------------------------------------------------------------------

def test_safe_patcher_path_traversal(tmp_path):
    patcher = SafePatcher(tmp_path)
    patcher.write_file("nested/code.py", "x = 1")
    assert patcher.read_file("nested/code.py") == "x = 1"

    # Path traversal must raise PatcherError
    with pytest.raises(PatcherError):
        patcher.write_file("../escape.py", "bad")


def test_code_reviewer_blocks_dangerous_patterns(tmp_path):
    reviewer = CodeReviewer()

    bad_file = tmp_path / "bad.py"
    bad_file.write_text("import ctypes\nctypes.c_int(42)", encoding="utf-8")
    findings = reviewer.review_file(bad_file)
    assert any(f.rule == "forbidden_import" for f in findings)

    eval_file = tmp_path / "dynamic.py"
    eval_file.write_text("eval('2 + 2')", encoding="utf-8")
    findings_eval = reviewer.review_file(eval_file)
    assert any(f.rule == "dynamic_execution" for f in findings_eval)

    good_file = tmp_path / "good.py"
    good_file.write_text("def add(a, b):\n    return a + b", encoding="utf-8")
    assert len(reviewer.review_file(good_file)) == 0


def test_canary_state_lifecycle():
    canary = CanaryState(upgrade_id="upgrade-001", min_canary_runs=2)
    assert canary.stage == UpgradeStage.CANDIDATE

    canary.transition(UpgradeStage.CANARY, "Starting canary")
    # Run 1 success
    canary.record_run(success=True)
    assert canary.stage == UpgradeStage.CANARY

    # Run 2 success -> should advance to ACTIVE
    canary.record_run(success=True)
    assert canary.stage == UpgradeStage.ACTIVE


def test_canary_rollback_on_failure():
    canary = CanaryState(upgrade_id="upgrade-002")
    canary.transition(UpgradeStage.CANARY, "Starting canary")
    ok = canary.record_run(success=False)
    assert ok is False
    assert canary.stage == UpgradeStage.ROLLED_BACK


def test_benchmarker_regression_detection():
    bench = UpgradeBenchmarker(min_success_rate=0.90, max_latency_regression_pct=20.0)

    # Good candidate
    cmp_good = bench.compare(candidate_passed_tests=10, candidate_total_tests=10, candidate_duration_s=2.0)
    assert cmp_good.passed is True
    assert cmp_good.regression_detected is False

    # Low success rate candidate
    cmp_bad = bench.compare(candidate_passed_tests=5, candidate_total_tests=10, candidate_duration_s=2.0)
    assert cmp_bad.passed is False
    assert cmp_bad.regression_detected is True


def test_scenario_simulator():
    sim = ScenarioSimulator()
    results = sim.run_all()
    assert len(results) >= 4
    assert all(r.passed for r in results)


# ---------------------------------------------------------------------------
# M11: Multi-Agent Subsystem
# ---------------------------------------------------------------------------

def test_multi_agent_coordinator_and_specialists():
    coord = MultiAgentCoordinator()

    # Route action to appropriate specialist
    researcher = coord.route_action("search_web", "web.search")
    assert researcher.role == SpecialistRole.RESEARCHER

    computer = coord.route_action("click", "mouse.click")
    assert computer.role == SpecialistRole.COMPUTER

    coder = coord.route_action("modify_file", "development.patch")
    assert coder.role == SpecialistRole.CODER

    # Reviewer specialist rejection
    reviewer = coord.reviewer
    ok, _ = reviewer.review_plan([{"action": "delete_all", "risk_tier": "RED", "authorized": False}])
    assert ok is False

    ok_approved, _ = reviewer.review_plan([{"action": "delete_all", "risk_tier": "RED", "authorized": True}])
    assert ok_approved is True

    # Reviewer diff check
    diff_ok, _ = reviewer.review_diff("def safe_func(): pass")
    assert diff_ok is True
    diff_bad, _ = reviewer.review_diff("ctypes.cast(ptr, c_char_p)")
    assert diff_bad is False

    # Delegated execution
    exec_res = coord.execute_delegated(SpecialistRole.CODER, "write_test", lambda x: x * 2, 21)
    assert exec_res.success is True
    assert exec_res.output == 42
