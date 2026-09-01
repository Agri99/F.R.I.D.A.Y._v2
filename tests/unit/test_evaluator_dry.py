"""
tests/unit/test_evaluator_dry.py

WHAT THIS IS FOR:
Regression guard for a DRY fix: Evaluator.evaluate() used to repeat the
same four-line task.verification_results.append({...}) block after every
one of five return branches - easy to update three of five and silently
miss the other two. Refactored into a single _decide() that returns an
EvaluationResult, with evaluate() recording it exactly once. This test
proves exactly one entry is recorded per call, across each strategy
branch, not that the branches happen to still produce the right verdict
(that's covered by exercising each branch's pass/fail outcome too).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from friday.agent.task import Task, Step
from friday.agent.evaluator import Evaluator
from friday.agent.executor import ExecutionResult


def _result(**kwargs):
    defaults = dict(observation="", error=None, verification_passed=True, result=None)
    defaults.update(kwargs)
    return ExecutionResult(**defaults)


def test_exactly_one_verification_entry_per_evaluate_call_on_success():
    task = Task(goal="test")
    step = Step(action="do.thing", expected_observation="done successfully")
    evaluator = Evaluator()

    evaluator.evaluate(task, step, _result(observation="done successfully"))

    assert len(task.verification_results) == 1
    assert task.verification_results[0]["passed"] is True


def test_exactly_one_verification_entry_per_evaluate_call_on_execution_failure():
    task = Task(goal="test")
    step = Step(action="do.thing", expected_observation="")
    evaluator = Evaluator()

    evaluator.evaluate(task, step, _result(error="boom", verification_passed=False))

    assert len(task.verification_results) == 1
    assert task.verification_results[0]["passed"] is False


def test_exactly_one_verification_entry_per_evaluate_call_on_controller_verification():
    task = Task(goal="test")
    step = Step(action="do.thing", expected_observation="")
    evaluator = Evaluator()

    result = _result(observation="clicked")
    result.verification_passed = False  # controller says it failed
    result.verification_reason = "element not found"

    evaluator.evaluate(task, step, result)

    assert len(task.verification_results) == 1
    assert task.verification_results[0]["passed"] is False
    assert task.verification_results[0]["reason"] == "element not found"


def test_multiple_calls_accumulate_one_entry_each():
    task = Task(goal="test")
    evaluator = Evaluator()

    evaluator.evaluate(task, Step(action="a", expected_observation="ok"), _result(observation="ok success"))
    evaluator.evaluate(task, Step(action="b", expected_observation="ok"), _result(observation="ok success"))
    evaluator.evaluate(task, Step(action="c", expected_observation="ok"), _result(observation="ok success"))

    assert len(task.verification_results) == 3


def test_step_verified_flag_matches_eval_result():
    task = Task(goal="test")
    step = Step(action="do.thing", expected_observation="expected text")
    evaluator = Evaluator()

    evaluator.evaluate(task, step, _result(observation="something unrelated", verification_passed=None))

    assert step.verified is False


def test_missing_expected_observation_is_not_success():
    """A tool returning without error must not be treated as success when no
    verification or expected outcome is provided (false-success guard)."""
    task = Task(goal="test")
    step = Step(action="do.thing", expected_observation="")
    evaluator = Evaluator()

    result = evaluator.evaluate(task, step, _result(observation="returned", verification_passed=None))

    assert result.passed is False
    assert result.needs_replan is True
