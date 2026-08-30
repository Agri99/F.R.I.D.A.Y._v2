"""
src/friday/agent/evaluator.py

WHAT THIS IS FOR:
Post-step observation evaluation and verification scoring (Blueprint §9, §10).
Enhanced with LLM-based semantic verification for complex outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from .task import Task, Step
from .executor import ExecutionResult
from .planner import Planner
from friday.models.base import ModelMessage


@dataclass
class EvaluationResult:
    passed: bool
    confidence: float
    reason: str
    observation_summary: str
    needs_replan: bool


class Evaluator:
    """Verifies that an execution step achieved its intended outcome."""

    def __init__(self, model_router: Any = None):
        self.model_router = model_router
        self._semantic_verification_prompt = """You are an evaluation engine. Given an expected outcome and actual observation, determine if the step succeeded.

Expected: {expected}
Actual observation: {actual}

Consider:
- Semantic equivalence (different words, same meaning)
- Partial success (some progress toward goal)
- Contextual clues (UI state, error messages, confirmations)

Respond with ONLY a JSON object:
{{"passed": true/false, "confidence": 0.0-1.0, "reason": "explanation"}}"""

    def evaluate(self, task: Task, step: Step, result: ExecutionResult, tool: Any = None) -> EvaluationResult:
        """Determines pass/fail for a step, tries a few strategies in order,
        and records the outcome in task.verification_results exactly once
        regardless of which strategy decided it (this used to repeat the
        same append block after every return branch - five copies of the
        same four lines, easy to update three of five and miss the other
        two)."""
        step.observation = result.observation
        if not hasattr(task, "verification_results"):
            task.verification_results = []

        eval_result = self._decide(task, step, result, tool)

        step.verified = eval_result.passed
        task.verification_results.append({
            "step": step.action,
            "passed": eval_result.passed,
            "confidence": eval_result.confidence,
            "reason": eval_result.reason,
        })
        return eval_result

    def _decide(self, task: Task, step: Step, result: ExecutionResult, tool: Any) -> EvaluationResult:
        """The actual strategy chain, tried in order. Each branch just
        returns its EvaluationResult - recording it is evaluate()'s job,
        done once, in one place."""

        # Strategy 1: the controller already did verification (e.g. WindowsComputerController)
        if hasattr(result, "verification_passed") and result.verification_passed is not None:
            passed = result.verification_passed
            return EvaluationResult(
                passed=passed,
                confidence=0.9,
                reason=result.verification_reason or ("Controller verification passed" if passed else "Controller verification failed"),
                observation_summary=result.observation,
                needs_replan=not passed,
            )

        # Strategy 2: outright execution failure
        if not result.verification_passed or result.error:
            return EvaluationResult(
                passed=False,
                confidence=1.0,
                reason=f"Execution failed: {result.error}",
                observation_summary=result.observation,
                needs_replan=True,
            )

        # Strategy 3: semantic verification via LLM for complex expectations
        if self.model_router and self._should_use_semantic_verification(step, result):
            semantic_result = self._semantic_verify(step, result)
            if semantic_result:
                return semantic_result

        # Strategy 4: substring / success-indicator matching
        exp = (step.expected_observation or "").strip().lower()
        actual = (result.observation or "").strip().lower()

        if exp and exp not in actual:
            success_indicators = ("success", "opened", "created", "saved", "done", "written", "ok", "true", "200")
            if any(ind in actual for ind in success_indicators):
                return EvaluationResult(
                    passed=True,
                    confidence=0.85,
                    reason="Success verified by observation indicators.",
                    observation_summary=result.observation,
                    needs_replan=False,
                )
            return EvaluationResult(
                passed=False,
                confidence=0.6,
                reason=f"Actual observation did not match expected '{step.expected_observation}'.",
                observation_summary=result.observation,
                needs_replan=True,
            )

        # Strategy 5: expected observation was present (or none was required) - pass
        return EvaluationResult(
            passed=True,
            confidence=1.0,
            reason="Step successfully executed and verified.",
            observation_summary=result.observation,
            needs_replan=False,
        )

    def _should_use_semantic_verification(self, step: Step, result: ExecutionResult) -> bool:
        """Determine if semantic verification is warranted."""
        exp = step.expected_observation or ""
        return len(exp) > 20 or " and " in exp.lower() or "then" in exp.lower()

    def _semantic_verify(self, step: Step, result: ExecutionResult) -> EvaluationResult | None:
        """Use LLM to semantically verify outcome."""
        if not self.model_router:
            return None

        try:
            provider = self.model_router.get("reasoning") if hasattr(self.model_router, "get") else self.model_router
            if not provider or not hasattr(provider, "generate"):
                return None

            prompt = self._semantic_verification_prompt.format(
                expected=step.expected_observation,
                actual=result.observation
            )
            messages = [ModelMessage(role="user", content=prompt)]
            response = provider.generate(messages=messages, tools=None)

            import json
            try:
                data = json.loads(response.text.strip())
                passed = data.get("passed", False)
                confidence = float(data.get("confidence", 0.5))
                reason = data.get("reason", "Semantic verification")
                return EvaluationResult(
                    passed=passed,
                    confidence=confidence,
                    reason=reason,
                    observation_summary=result.observation,
                    needs_replan=not passed,
                )
            except json.JSONDecodeError:
                return None
        except Exception:
            return None
