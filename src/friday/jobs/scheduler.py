"""
src/friday/jobs/scheduler.py

WHAT THIS IS FOR:
Cron-like job scheduler to manage background proactive tasks.
Enhanced with full job schema: trigger, context, skill, capabilities, budget, window, verification, failure_policy, notification.
"""

from __future__ import annotations

import sched
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as dt_time
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from croniter import croniter
except ImportError:
    croniter = None


class TriggerType(Enum):
    CRON = "cron"
    INTERVAL = "interval"
    EVENT = "event"
    ONCE = "once"


class FailurePolicy(Enum):
    RETRY = "retry"
    SKIP = "skip"
    DISABLE = "disable"
    ALERT = "alert"


class NotificationPolicy(Enum):
    VOICE = "voice"
    SILENT = "silent"
    LOG = "log"
    NONE = "none"


class VerificationType(Enum):
    NONE = "none"
    ORCHESTRATOR = "orchestrator"      # Use orchestrator verification
    CUSTOM = "custom"                  # Custom verification function
    EXPECTED_OUTPUT = "expected_output" # Check expected output contains string


@dataclass
class JobBudget:
    """Execution budget constraints for a job."""
    max_time_seconds: float = 300.0      # 5 minutes default
    max_tokens: int = 10000              # Token budget
    max_retries: int = 2
    backoff_seconds: int = 60


@dataclass
class ExecutionWindow:
    """Time window when job is allowed to execute."""
    start_time: dt_time = dt_time(0, 0)   # 00:00
    end_time: dt_time = dt_time(23, 59)   # 23:59
    timezone: str = "local"                # "local" or IANA timezone
    days: list[int] = field(default_factory=lambda: list(range(7)))  # 0=Mon, 6=Sun


@dataclass
class Job:
    """Represents a scheduled or event-driven proactive task.

    Schema:
    - trigger: cron:0 7 * * * | interval:3600 | event:network_online | once:2024-01-01
    - context: priming query for context engine
    - skill: skill name or natural language task
    - capabilities: required capabilities (terminal.build, browser.navigate, etc.)
    - budget: JobBudget with time/token/retry limits
    - window: ExecutionWindow with time/day restrictions
    - verification: VerificationType + expected output for validation
    - failure_policy: FailurePolicy
    - notification: NotificationPolicy
    """
    id: str
    name: str
    trigger: str
    context: str = ""                    # Context priming query
    skill: str = ""                      # Skill name or task description
    capabilities: list[str] = field(default_factory=list)
    budget: JobBudget | dict = field(default_factory=JobBudget)
    window: ExecutionWindow | dict = field(default_factory=ExecutionWindow)
    verification: VerificationType | str = VerificationType.ORCHESTRATOR
    verification_expected: str = ""      # Expected output string for verification
    verification_func: Callable[[Any], bool] | None = None  # Custom verification
    failure_policy: FailurePolicy | str = FailurePolicy.RETRY
    notification: NotificationPolicy | str = NotificationPolicy.VOICE
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    fail_count: int = 0
    consecutive_failures: int = 0
    last_result: Any = None

    def __post_init__(self):
        """Convert dict inputs to proper objects."""
        if isinstance(self.budget, dict):
            self.budget = JobBudget(**self.budget)
        if isinstance(self.window, dict):
            # Convert time strings to dt_time objects
            window_data = self.window.copy()
            if "start_time" in window_data and isinstance(window_data["start_time"], str):
                from datetime import time as dt_time
                window_data["start_time"] = dt_time.fromisoformat(window_data["start_time"])
            if "end_time" in window_data and isinstance(window_data["end_time"], str):
                from datetime import time as dt_time
                window_data["end_time"] = dt_time.fromisoformat(window_data["end_time"])
            self.window = ExecutionWindow(**window_data)
        if isinstance(self.verification, str):
            self.verification = VerificationType(self.verification)
        if isinstance(self.failure_policy, str):
            self.failure_policy = FailurePolicy(self.failure_policy)
        if isinstance(self.notification, str):
            self.notification = NotificationPolicy(self.notification)


class JobScheduler:
    """Manages scheduling and triggering of Jobs with execution windows and graceful degradation."""

    def __init__(self, jobs_dir: Path | str = "data/jobs", jobs: list[Job] | None = None,
                 capability_registry: Any = None, orchestrator_factory: Callable[[], Any] | None = None):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        self._scheduler = sched.scheduler(time.time, time.sleep)
        self.capability_registry = capability_registry
        self.orchestrator_factory = orchestrator_factory
        self._running = False
        self._thread: Any = None

        if jobs:
            for j in jobs:
                self.register(j)

    def register(self, job: Job) -> None:
        """Register a job with the scheduler."""
        self.jobs[job.id] = job
        if job.enabled:
            self._schedule_next(job)

    def unregister(self, job_id: str) -> None:
        """Unregister a job from the scheduler."""
        if job_id in self.jobs:
            del self.jobs[job_id]

    def get_due_jobs(self) -> list[Job]:
        """Return jobs that are due for execution right now, respecting execution windows."""
        now = datetime.now()
        due = []
        for job in self.jobs.values():
            if not job.enabled:
                continue
            if job.next_run and job.next_run <= now:
                if self._in_execution_window(job, now):
                    due.append(job)
                else:
                    # Outside window - reschedule to next window
                    self._schedule_next_in_window(job, now)
        return due

    def _in_execution_window(self, job: Job, now: datetime) -> bool:
        """Check if current time is within job's execution window."""
        window = job.window
        current_time = now.time()
        current_day = now.weekday()  # 0=Monday

        # Check day
        if current_day not in window.days:
            return False

        # Check time window (handle midnight crossing)
        if window.start_time <= window.end_time:
            return window.start_time <= current_time <= window.end_time
        else:
            # Window crosses midnight (e.g., 22:00 to 06:00)
            return current_time >= window.start_time or current_time <= window.end_time

    def _schedule_next_in_window(self, job: Job, from_time: datetime) -> None:
        """Schedule next run at the start of the next valid window."""
        next_run = self.parse_trigger(job.trigger)
        if next_run and not self._in_execution_window(job, next_run):
            # Move to start of next valid window
            next_run = self._next_window_start(job, next_run)
        job.next_run = next_run

    def _next_window_start(self, job: Job, from_time: datetime) -> datetime:
        """Find the next window start time."""
        window = job.window
        current = from_time

        # If we're before window start today, use today
        if current.time() < window.start_time and current.weekday() in window.days:
            return datetime.combine(current.date(), window.start_time)

        # Otherwise, find next valid day
        days_ahead = 1
        while days_ahead <= 7:
            next_day = current + timedelta(days=days_ahead)
            if next_day.weekday() in window.days:
                return datetime.combine(next_day.date(), window.start_time)
            days_ahead += 1

        return from_time + timedelta(days=1)  # Fallback

    def mark_completed(self, job_id: str, success: bool, result: Any = None) -> None:
        """Update job statistics after execution."""
        job = self.jobs.get(job_id)
        if not job:
            return

        job.last_run = datetime.now()
        job.last_result = result

        if success:
            job.run_count += 1
            job.fail_count = 0
            job.consecutive_failures = 0
        else:
            job.fail_count += 1
            job.consecutive_failures += 1

            # Apply failure policy
            if job.failure_policy == FailurePolicy.DISABLE and job.consecutive_failures >= 3:
                job.enabled = False
                logger.warning(f"Job {job.id} disabled after {job.consecutive_failures} consecutive failures")
            elif job.failure_policy == FailurePolicy.SKIP:
                # Leave next_run unchanged; scheduler will reschedule on next iteration
                self._schedule_next(job)
                return
            elif job.failure_policy == FailurePolicy.RETRY:
                backoff = job.budget.backoff_seconds if hasattr(job.budget, "backoff_seconds") else 60
                from datetime import timedelta
                job.next_run = datetime.now() + timedelta(seconds=backoff)
                if job.consecutive_failures >= job.budget.max_retries:
                    job.enabled = False
                    logger.warning(f"Job {job.id} exceeded retry budget ({job.budget.max_retries}); disabling")
                return

        self._schedule_next(job)

        self._schedule_next(job)

    def load_jobs(self) -> list[Job]:
        """Load all jobs from the jobs directory."""
        return list(self.jobs.values())

    def save_job(self, job: Job) -> None:
        """Persist a job."""
        # Handled by JobRegistry in actual implementation

    def parse_trigger(self, trigger: str, base: datetime | None = None) -> datetime | None:
        """Parse the trigger string and calculate the next execution time."""
        from datetime import timedelta
        base = base or datetime.now()

        if trigger.startswith("cron:") and croniter is not None:
            expr = trigger.split(":", 1)[1]
            try:
                cron = croniter(expr, base)
                return cron.get_next(datetime)
            except Exception:
                return base + timedelta(hours=24)

        if trigger.startswith("interval:"):
            try:
                seconds = int(trigger.split(":", 1)[1])
                return base + timedelta(seconds=seconds)
            except ValueError:
                return base + timedelta(hours=1)

        if trigger.startswith("event:"):
            # Event triggers don't have a predictable next run
            return None

        if trigger.startswith("once:"):
            try:
                date_str = trigger.split(":", 1)[1]
                return datetime.fromisoformat(date_str)
            except Exception:
                return base + timedelta(hours=24)

        if trigger == "daily":
            return base + timedelta(days=1)
        if trigger == "hourly":
            return base + timedelta(hours=1)

        return base + timedelta(hours=24)

    def _schedule_next(self, job: Job) -> None:
        """Calculate and set the next_run time based on the trigger."""
        if job.trigger.startswith("event:"):
            job.next_run = None  # Event-driven, no scheduled next run
        else:
            next_run = self.parse_trigger(job.trigger)
            if next_run:
                # Ensure it's in an execution window
                if self._in_execution_window(job, next_run):
                    job.next_run = next_run
                else:
                    self._schedule_next_in_window(job, next_run)
            else:
                job.next_run = None

    def start(self) -> None:
        """Start the scheduler background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run_loop(self) -> None:
        """Background loop to execute due jobs."""
        while self._running:
            due_jobs = self.get_due_jobs()
            for job in due_jobs:
                self._execute_job(job)
            time.sleep(10)  # Check every 10 seconds

    def _execute_job(self, job: Job) -> None:
        """Execute a job with budget enforcement and verification."""
        if self.orchestrator_factory is None:
            logger.warning(f"No orchestrator factory configured, skipping job {job.id}")
            return

        orchestrator = self.orchestrator_factory()
        start_time = time.time()

        try:
            # Check capability availability
            if not self._check_capabilities(job):
                logger.warning(f"Job {job.id} missing required capabilities: {job.capabilities}")
                self.mark_completed(job.id, False, {"error": "Missing capabilities"})
                return

            # Execute with budget
            budget = job.budget
            task = orchestrator.run(job.skill)

            # Verify result
            verified = self._verify_result(job, task)

            # Check budget
            duration = time.time() - start_time
            if duration > budget.max_time_seconds:
                logger.warning(f"Job {job.id} exceeded time budget: {duration:.1f}s > {budget.max_time_seconds}s")
                verified = False

            success = task.status.value in ("COMPLETED", "DONE", "SUCCESS", "done") and verified
            self.mark_completed(job.id, success, task.last_message)

        except Exception as exc:
            logger.error(f"Job {job.id} execution failed: {exc}")
            self.mark_completed(job.id, False, {"error": str(exc)})

    def _check_capabilities(self, job: Job) -> bool:
        """Check if required capabilities are available."""
        if not self.capability_registry:
            return True  # No registry = no restriction
        for cap in job.capabilities:
            if not self.capability_registry.is_enabled(cap):
                return False
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

        return False


# Helper imports
import logging
import threading
from datetime import timedelta

logger = logging.getLogger(__name__)
