"""
tests/integration/test_job_scheduling.py

WHAT THIS IS FOR:
Integration test for job registry persistence, scheduler triggering, and execution.
"""

from __future__ import annotations

import tempfile
from datetime import time as dt_time

from friday.jobs.scheduler import (
    Job, JobScheduler, JobBudget, ExecutionWindow,
    FailurePolicy, NotificationPolicy, VerificationType
)
from friday.jobs.registry import JobRegistry
from friday.jobs.executor import JobExecutor


def test_job_persistence_and_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = JobRegistry(storage_dir=tmpdir)
        executor = JobExecutor()
        scheduler = JobScheduler(jobs=[])

        job = Job(
            id="daily_healthcheck",
            name="Daily System Diagnostics",
            trigger="daily",
            context="system status",
            skill="Check system status and report disk usage",
            capabilities=["system"],
            budget=JobBudget(max_time_seconds=300),
            window=ExecutionWindow(start_time=dt_time(0, 0), end_time=dt_time(23, 59), days=list(range(7))),
            verification=VerificationType.ORCHESTRATOR,
            failure_policy=FailurePolicy.RETRY,
            notification=NotificationPolicy.VOICE,
            enabled=True,
        )

        # 1. Save and load
        registry.save(job)
        loaded_jobs = registry.load_all()
        assert len(loaded_jobs) == 1
        assert loaded_jobs[0].id == "daily_healthcheck"

        # 2. Execute job
        result = executor.execute(job)
        assert result.success is True

        # 3. Delete job
        assert registry.delete("daily_healthcheck") is True
        assert len(registry.load_all()) == 0
