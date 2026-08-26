from __future__ import annotations

from dataclasses import dataclass
from .task import Task, Step
from .executor import ExecutionResult

@dataclass
class EvaluationResult:
    passed: bool
    confidence: float
    reason: str
    observation_summary: str
    needs_replan: bool

class Evaluator:
    """Verifies that an execution actually achieved its expected outcome."""
    
    def evaluate(self, task: Task, step: Step, result: ExecutionResult, tool=None) -> EvaluationResult:
        step.observation = result.observation
        
        if not result.verification_passed or result.error:
            step.verified = False
            return EvaluationResult(
                passed=False, 
                confidence=1.0, 
                reason=f"Execution failed: {result.error}",
                observation_summary=result.observation,
                needs_replan=True
            )
            
        # Compare expected observation with actual observation
        if step.expected_observation and step.expected_observation not in result.observation:
            # Simplistic check for demo; in real system would use a model
            step.verified = False
            return EvaluationResult(
                passed=False,
                confidence=0.5,
                reason="Actual observation does not match expected.",
                observation_summary=result.observation,
                needs_replan=True
            )
            
        step.verified = True
        return EvaluationResult(
            passed=True, 
            confidence=1.0, 
            reason="Success",
            observation_summary=result.observation,
            needs_replan=False
        )
