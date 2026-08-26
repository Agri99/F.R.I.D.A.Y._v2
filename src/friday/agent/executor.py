from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

@dataclass
class ExecutionResult:
    success: bool
    result: Any
    error: str | None = None
    error_type: str | None = None
    duration_ms: float = 0.0

class Executor:
    """Isolated execution environment that runs tools and captures errors."""
    
    def execute(self, tool, args: dict[str, Any], timeout: float = 30.0) -> ExecutionResult:
        """Runs the tool safely, catching and classifying exceptions."""
        start_time = time.time()
        try:
            # We assume tool has a run method or is callable
            if hasattr(tool, "run"):
                res = tool.run(**args)
            else:
                res = tool(**args)
            duration = (time.time() - start_time) * 1000
            return ExecutionResult(success=True, result=res, duration_ms=duration)
        except PermissionError as e:
            duration = (time.time() - start_time) * 1000
            return ExecutionResult(success=False, result=None, error=str(e), error_type="permission", duration_ms=duration)
        except ValueError as e:
            duration = (time.time() - start_time) * 1000
            return ExecutionResult(success=False, result=None, error=str(e), error_type="invalid_input", duration_ms=duration)
        except TimeoutError as e:
            duration = (time.time() - start_time) * 1000
            return ExecutionResult(success=False, result=None, error=str(e), error_type="transient", duration_ms=duration)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ExecutionResult(success=False, result=None, error=str(e), error_type="unknown", duration_ms=duration)
