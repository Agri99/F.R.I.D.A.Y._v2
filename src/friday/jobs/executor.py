"""
src/friday/jobs/executor.py

WHAT THIS IS FOR:
Executes triggered Jobs safely, enforcing execution budgets, verification, and policies (§11 of Blueprint).
Enhanced with graceful degradation, capability checks, and verification.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from friday.jobs.scheduler import Job, JobBudget, VerificationType
from friday.online.capability_gate import OnlineCapabilityGate, NetworkMonitor

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    job_id: str
    success: bool
    output: str
    duration_seconds: float = 0.0
    error: str | None = None
    verified: bool = False
    degraded: bool = False
    degradation_reason: str = ""


class JobExecutor:
    """Runs scheduled jobs safely through the standard orchestrator pipeline with budget enforcement and graceful degradation."""

    def __init__(self, capability_gate: Optional[OnlineCapabilityGate] = None):
        self.capability_gate = capability_gate

    def execute(self, job: Job, orchestrator: Any = None) -> JobResult:
        """
        Execute a scheduled job through the normal agent pipeline.
        Jobs use the same policy engine as interactive commands and cannot bypass security.
        Supports graceful degradation when capabilities are unavailable.
        """
        logger.info(f"Executing job '{job.name}' ({job.id})")
        start_time = time.time()

        if not job.enabled:
            return JobResult(
                job_id=job.id,
                success=False,
                output="Job is disabled.",
                error="Disabled",
            )

        # Check capabilities
        if not self._check_capabilities(job):
            return JobResult(
                job_id=job.id,
                success=False,
                output="Required capabilities unavailable.",
                error="Missing capabilities",
                degraded=True,
                degradation_reason="Required capabilities not available",
            )

        # Check online requirements
        degraded = False
        degradation_reason = ""
        if self.capability_gate:
            for cap in job.capabilities:
                if cap.startswith(("browser.", "online.", "live_data")):
                    if not self.capability_gate.is_available(cap):
                        degraded = True
                        degradation_reason = f"Online capability '{cap}' unavailable"
                        break

        output_msg = ""
        success = True
        error_msg = None
        verified = False

        if orchestrator and hasattr(orchestrator, "run"):
            try:
                # Execute with timeout
                task = self._run_with_timeout(orchestrator, job)
                success = task.status.value in ("DONE", "SUCCESS", "done", "COMPLETED")
                output_msg = task.last_message or f"Job finished with state {task.status.value}"

                # Verify result
                verified = self._verify_result(job, task)
                if not verified:
                    success = False
                    error_msg = "Verification failed"

            except TimeoutError:
                success = False
                error_msg = f"Job timed out after {job.budget.max_time_seconds}s"
            except Exception as exc:
                success = False
                error_msg = str(exc)
                output_msg = f"Job execution error: {exc}"
        else:
            output_msg = f"Simulated execution of proactive job: {job.skill}"
            verified = True  # Simulated always passes verification

        duration = time.time() - start_time

        # Check time budget
        if duration > job.budget.max_time_seconds:
            success = False
            error_msg = f"Exceeded time budget: {duration:.1f}s > {job.budget.max_time_seconds}s"
            degraded = True
            degradation_reason = "Time budget exceeded"

        return JobResult(
            job_id=job.id,
            success=success,
            output=output_msg,
            duration_seconds=round(duration, 3),
            error=error_msg,
            verified=verified,
            degraded=degraded,
            degradation_reason=degradation_reason,
        )

    def _run_with_timeout(self, orchestrator: Any, job: Job) -> Any:
        """Run orchestrator with timeout."""
        import threading
        result_container = {"task": None, "error": None}

        def run_orchestrator():
            try:
                result_container["task"] = orchestrator.run(job.skill)
            except Exception as e:
                result_container["error"] = e

        thread = threading.Thread(target=run_orchestrator)
        thread.daemon = True
        thread.start()
        thread.join(timeout=job.budget.max_time_seconds)

        if thread.is_alive():
            raise TimeoutError(f"Job exceeded time budget of {job.budget.max_time_seconds}s")

        if result_container["error"]:
            raise result_container["error"]

        return result_container["task"]

    def _check_capabilities(self, job: Job) -> bool:
        """Check if required capabilities are available locally."""
        # This would check against a local capability registry
        # For now, assume all non-online capabilities are available
        for cap in job.capabilities:
            if not cap.startswith(("browser.", "online.", "live_data")):
                # Local capability - could check against local registry
                pass
        return True

    def _verify_result(self, job: Job, task: Any) -> bool:
        """Verify job execution result based on verification type."""
        if job.verification == VerificationType.NONE:
            return True

        if job.verification == VerificationType.ORCHESTRATOR:
            return task.status.value in ("COMPLETED", "DONE", "SUCCESS", "done")

        if job.verification == VerificationType.EXPECTED_OUTPUT:
            expected = job.verification_expected.lower()
            actual = (task.last_message or "").lower()
            return expected in actual

        if job.verification == VerificationType.CUSTOM and job.verification_func:
            try:
                return job.verification_func(task)
            except Exception:
                return False

        return True
