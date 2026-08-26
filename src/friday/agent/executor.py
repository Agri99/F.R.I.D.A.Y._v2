from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from friday.security.action_request import ActionRequest

@dataclass
class ExecutionResult:
    result: Any
    observation: str
    verification_passed: bool
    error: str | None = None

class Executor:
    """Isolated execution environment that runs tools and captures errors."""
    
    def execute(self, tool, step: Any, max_time_budget: float = 120.0) -> ExecutionResult:
        """Runs the tool safely, catching and classifying exceptions."""
        start_time = time.time()
        
        # Enforce step retry limits
        retry_limit = 1
        if step.retry_policy == "aggressive":
            retry_limit = 3
        elif step.retry_policy == "none":
            retry_limit = 1
            
        last_error = None
        for attempt in range(retry_limit):
            if time.time() - start_time > max_time_budget:
                return ExecutionResult(result=None, observation="Execution timed out.", verification_passed=False, error="timeout")
            
            try:
                # Construct ActionRequest
                req = ActionRequest(action=step.action, arguments=step.arguments)
                
                # Execute tool
                if hasattr(tool, "run"):
                    res = tool.run(**req.arguments)
                else:
                    res = tool(**req.arguments)
                
                obs = str(res)
                return ExecutionResult(result=res, observation=obs, verification_passed=True)
            except Exception as e:
                last_error = str(e)
                time.sleep(1) # Simple backoff
                
        return ExecutionResult(result=None, observation=f"Failed after {retry_limit} attempts: {last_error}", verification_passed=False, error=last_error)
