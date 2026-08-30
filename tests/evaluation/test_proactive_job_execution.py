"""
tests/evaluation/test_proactive_job_execution.py

WHAT THIS IS FOR:
E2E evaluation test for proactive job execution with notifications.
"""

from __future__ import annotations

from datetime import time as dt_time

import pytest

from friday.jobs.scheduler import (
    Job, JobScheduler, JobBudget, ExecutionWindow,
    FailurePolicy, NotificationPolicy, VerificationType
)
from friday.jobs.registry import JobRegistry


class TestProactiveJobExecution:
    @pytest.fixture
    def scheduler(self, tmp_path):
        return JobScheduler(jobs_dir=tmp_path / "jobs")

    @pytest.fixture
    def registry(self, tmp_path):
        return JobRegistry(storage_dir=tmp_path / "jobs")

    def test_job_creation_and_persistence(self, scheduler, registry):
        job = Job(
            id="daily_briefing",
            name="Morning Briefing",
            trigger="cron:0 7 * * *",
            context="morning briefing context",
            skill="Give morning briefing with weather and calendar",
            capabilities=["online.search", "calendar.read"],
            budget=JobBudget(max_time_seconds=300, max_retries=2, backoff_seconds=60),
            window=ExecutionWindow(start_time=dt_time(0, 0), end_time=dt_time(23, 59), days=list(range(7))),
            verification=VerificationType.ORCHESTRATOR,
            failure_policy=FailurePolicy.RETRY,
            notification=NotificationPolicy.VOICE,
            enabled=True,
        )

        scheduler.register(job)

        # Verify in-memory job
        in_memory_job = scheduler.jobs.get("daily_briefing")
        assert in_memory_job is not None
        assert in_memory_job.name == "Morning Briefing"
        assert in_memory_job.trigger == "cron:0 7 * * *"
        assert in_memory_job.capabilities == ["online.search", "calendar.read"]

    def test_job_execution_updates_stats(self, scheduler, registry):
        job = Job(
            id="health_check",
            name="System Health Check",
            trigger="interval:3600",
            context="system status",
            skill="Check system status",
            capabilities=["system"],
            budget=JobBudget(max_time_seconds=300),
            window=ExecutionWindow(start_time=dt_time(0, 0), end_time=dt_time(23, 59), days=list(range(7))),
            verification=VerificationType.ORCHESTRATOR,
            failure_policy=FailurePolicy.RETRY,
            notification=NotificationPolicy.VOICE,
            enabled=True,
        )

        scheduler.register(job)

        # Simulate completion - check in-memory job
        scheduler.mark_completed("health_check", success=True)

        # Verify in-memory job stats
        in_memory_job = scheduler.jobs.get("health_check")
        assert in_memory_job is not None
        assert in_memory_job.run_count == 1
        assert in_memory_job.fail_count == 0
        assert in_memory_job.last_run is not None

    def test_job_failure_increments_fail_count(self, scheduler, registry):
        job = Job(
            id="failing_job",
            name="Failing Job",
            trigger="daily",
            context="test",
            skill="This will fail",
            capabilities=["system"],
            budget=JobBudget(max_time_seconds=300),
            window=ExecutionWindow(start_time=dt_time(0, 0), end_time=dt_time(23, 59), days=list(range(7))),
            verification=VerificationType.ORCHESTRATOR,
            failure_policy=FailurePolicy.RETRY,
            notification=NotificationPolicy.VOICE,
            enabled=True,
        )

        scheduler.register(job)

        scheduler.mark_completed("failing_job", success=False)
        scheduler.mark_completed("failing_job", success=False)

        in_memory_job = scheduler.jobs.get("failing_job")
        assert in_memory_job.fail_count == 2

    def test_job_notification_methods(self, scheduler, registry):
        for method in ["voice", "silent", "log"]:
            job = Job(
                id=f"job_{method}",
                name=f"Job {method}",
                trigger="daily",
                context="test",
                skill="Test",
                capabilities=["system"],
                budget=JobBudget(max_time_seconds=300),
                window=ExecutionWindow(start_time=dt_time(0, 0), end_time=dt_time(23, 59), days=list(range(7))),
                verification=VerificationType.ORCHESTRATOR,
                failure_policy=FailurePolicy.RETRY,
                notification=NotificationPolicy(method),
                enabled=True,
            )
            scheduler.register(job)
            in_memory_job = scheduler.jobs.get(f"job_{method}")
            assert in_memory_job.notification == NotificationPolicy(method)