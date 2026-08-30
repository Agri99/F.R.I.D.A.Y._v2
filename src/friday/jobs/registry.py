"""
src/friday/jobs/registry.py

WHAT THIS IS FOR:
Handles persistence and CRUD management for scheduled and proactive jobs (§11 of Blueprint).
Enhanced for new Job schema with budget, window, verification, failure_policy, notification.
"""

from __future__ import annotations

import logging
from pathlib import Path
import yaml
from datetime import time as dt_time

from friday.jobs.scheduler import (
    Job, JobBudget, ExecutionWindow,
    TriggerType, FailurePolicy, NotificationPolicy, VerificationType
)

logger = logging.getLogger(__name__)


class JobRegistry:
    """Store, retrieve, and manage scheduled proactive jobs."""

    def __init__(self, storage_dir: Path | str = "data/jobs"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save(self, job: Job) -> None:
        """Save a Job definition to YAML."""
        path = self.storage_dir / f"{job.id}.yaml"
        data = {
            "id": job.id,
            "name": job.name,
            "trigger": job.trigger,
            "context": job.context,
            "skill": job.skill,
            "capabilities": job.capabilities,
            "budget": {
                "max_time_seconds": job.budget.max_time_seconds,
                "max_tokens": job.budget.max_tokens,
                "max_retries": job.budget.max_retries,
                "backoff_seconds": job.budget.backoff_seconds,
            },
            "window": {
                "start_time": job.window.start_time.isoformat(),
                "end_time": job.window.end_time.isoformat(),
                "timezone": job.window.timezone,
                "days": job.window.days,
            },
            "verification": job.verification.value,
            "verification_expected": job.verification_expected,
            "failure_policy": job.failure_policy.value,
            "notification": job.notification.value,
            "enabled": job.enabled,
            "run_count": job.run_count,
            "fail_count": job.fail_count,
            "consecutive_failures": job.consecutive_failures,
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False)

    def get(self, job_id: str) -> Job | None:
        """Retrieve a single job by ID."""
        path = self.storage_dir / f"{job_id}.yaml"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    return self._deserialize_job(data)
        except Exception as exc:
            logger.error(f"Failed to load job {job_id}: {exc}")
        return None

    def _deserialize_job(self, data: dict) -> Job:
        """Deserialize YAML data into Job object."""
        budget = JobBudget(
            max_time_seconds=data.get("budget", {}).get("max_time_seconds", 300.0),
            max_tokens=data.get("budget", {}).get("max_tokens", 10000),
            max_retries=data.get("budget", {}).get("max_retries", 2),
            backoff_seconds=data.get("budget", {}).get("backoff_seconds", 60),
        )

        window_data = data.get("window", {})
        window = ExecutionWindow(
            start_time=dt_time.fromisoformat(window_data.get("start_time", "00:00:00")),
            end_time=dt_time.fromisoformat(window_data.get("end_time", "23:59:00")),
            timezone=window_data.get("timezone", "local"),
            days=window_data.get("days", list(range(7))),
        )

        return Job(
            id=data["id"],
            name=data["name"],
            trigger=data["trigger"],
            context=data.get("context", ""),
            skill=data.get("skill", ""),
            capabilities=data.get("capabilities", []),
            budget=budget,
            window=window,
            verification=VerificationType(data.get("verification", "orchestrator")),
            verification_expected=data.get("verification_expected", ""),
            failure_policy=FailurePolicy(data.get("failure_policy", "retry")),
            notification=NotificationPolicy(data.get("notification", "voice")),
            enabled=data.get("enabled", True),
            run_count=data.get("run_count", 0),
            fail_count=data.get("fail_count", 0),
            consecutive_failures=data.get("consecutive_failures", 0),
        )

    def delete(self, job_id: str) -> bool:
        """Delete a job by ID."""
        path = self.storage_dir / f"{job_id}.yaml"
        if path.exists():
            path.unlink()
            return True
        return False

    def load_all(self) -> list[Job]:
        """Load all Job YAML files in the storage directory."""
        jobs: list[Job] = []
        for file in self.storage_dir.glob("*.yaml"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and isinstance(data, dict):
                        jobs.append(self._deserialize_job(data))
            except Exception as exc:
                logger.warning(f"Skipping malformed job file {file}: {exc}")
        return jobs
