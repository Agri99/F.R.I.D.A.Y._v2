"""
src/friday/agent/executor.py

WHAT THIS IS FOR:
Isolated execution environment that constructs ActionRequest objects, runs tools,
enforces retry/time budgets, and returns structured ExecutionResult (blueprint §9, §37).
"""

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
        retry_policy = getattr(step, "retry_policy", "default")
        if retry_policy == "aggressive":
            retry_limit = 3
        elif retry_policy == "none":
            retry_limit = 1
        else:
            retry_limit = 1

        args = getattr(step, "arguments", getattr(step, "args", {})) or {}
        last_error = None

        for attempt in range(retry_limit):
            if time.time() - start_time > max_time_budget:
                return ExecutionResult(result=None, observation="Execution timed out.", verification_passed=False, error="timeout")

            try:
                # Construct ActionRequest
                req = ActionRequest.from_tool(tool, args, step_id=getattr(step, "intent", ""))

                # Execute tool
                if hasattr(tool, "run"):
                    res = tool.run(**req.arguments)
                elif hasattr(tool, "handler") and callable(tool.handler):
                    res = tool.handler(**req.arguments)
                elif callable(tool):
                    res = tool(**req.arguments)
                else:
                    raise ValueError(f"Tool {tool} is not callable")

                obs = str(res)
                return ExecutionResult(result=res, observation=obs, verification_passed=True)
            except Exception as e:
                last_error = str(e)
                if attempt < retry_limit - 1:
                    time.sleep(0.5)

        return ExecutionResult(
            result=None,
            observation=f"Failed after {retry_limit} attempts: {last_error}",
            verification_passed=False,
            error=last_error
        )
