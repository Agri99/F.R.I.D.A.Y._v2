from __future__ import annotations

from dataclasses import dataclass
from .task import Task, Step
from .executor import ExecutionResult

@dataclass
class EvaluationResult:
    success: bool
    needs_retry: bool = False
    needs_recovery: bool = False
    should_fail: bool = False
    message: str = ""

class Evaluator:
    """Verifies that an execution actually achieved its expected outcome."""
    
    def evaluate(self, task: Task, step: Step, result: ExecutionResult, tool=None) -> EvaluationResult:
        if not result.success:
            return EvaluationResult(success=False, needs_recovery=True, message=f"Execution failed: {result.error}")
            
        if tool and getattr(tool, "verify", None) is not None:
            try:
                verification = tool.verify(step.args, result.result)

                if not verification.passed:
                    return EvaluationResult(
                        success=False, 
                        needs_retry=True, 
                        message=f"Verification failed: {verification.message}"
                    )
            except Exception as e:
                return EvaluationResult(
                    success=False, 
                    should_fail=True, 
                    message=f"Verifier raised exception: {e}"
                )
                
        # If no explicit verifier or it passed
        return EvaluationResult(success=True, message="Success")
