"""
src/friday/jobs/scheduler.py

WHAT THIS IS FOR:
Cron-like job scheduler to manage background proactive tasks.
"""

from __future__ import annotations

import os
import sched
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from croniter import croniter

@dataclass
class Job:
    """Represents a scheduled or event-driven proactive task."""
    id: str
    name: str
    trigger: str             # 'cron:0 7 * * *' | 'event:network_online' | 'interval:3600'
    context_prime: str       # priming query for context engine
    skill_or_task: str       # skill name or natural language task
    permissions: list[str]   # required capabilities
    retry_policy: dict = field(default_factory=lambda: {'max_retries': 2, 'backoff_seconds': 60})
    notification: str = 'voice'  # 'voice' | 'silent' | 'log'
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    fail_count: int = 0

class JobScheduler:
    """Manages scheduling and triggering of Jobs."""
    
    def __init__(self, jobs_dir: Path | str):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        self._scheduler = sched.scheduler(time.time, time.sleep)

    def register(self, job: Job) -> None:
        """Register a job with the scheduler."""
        self.jobs[job.id] = job
        if job.enabled and job.trigger.startswith("cron:"):
            self._schedule_next(job)

    def unregister(self, job_id: str) -> None:
        """Unregister a job from the scheduler."""
        if job_id in self.jobs:
            del self.jobs[job_id]

    def get_due_jobs(self) -> list[Job]:
        """Return jobs that are due for execution right now."""
        now = datetime.now()
        due = []
        for job in self.jobs.values():
            if job.enabled and job.next_run and job.next_run <= now:
                due.append(job)
        return due

    def mark_completed(self, job_id: str, success: bool) -> None:
        """Update job statistics after execution."""
        job = self.jobs.get(job_id)
        if not job:
            return
            
        job.last_run = datetime.now()
        if success:
            job.run_count += 1
            job.fail_count = 0
        else:
            job.fail_count += 1
            
        self._schedule_next(job)
        self.save_job(job)

    def load_jobs(self) -> list[Job]:
        """Load all jobs from the jobs directory."""
        # This will interact with Registry in real usage, stubbed out for now
        return list(self.jobs.values())

    def save_job(self, job: Job) -> None:
        """Persist a job."""
        pass # Stub, handled by JobRegistry in actual implementation

    def parse_trigger(self, trigger: str) -> datetime | None:
        """Parse the trigger string and calculate the next execution time."""
        if trigger.startswith("cron:"):
            expr = trigger.split(":", 1)[1]
            try:
                base = datetime.now()
                cron = croniter(expr, base)
                return cron.get_next(datetime)
            except Exception:
                return None
        return None

    def _schedule_next(self, job: Job) -> None:
        """Calculate and set the next_run time based on the trigger."""
        job.next_run = self.parse_trigger(job.trigger)
