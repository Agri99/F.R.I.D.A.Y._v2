"""
src/friday/jobs/registry.py

WHAT THIS IS FOR:
Handles YAML serialization and persistence of Job definitions.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from friday.jobs.scheduler import Job

class JobRegistry:
    """Store and load job definitions."""
    
    def __init__(self, storage_dir: Path | str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
    def save(self, job: Job) -> None:
        """Save a Job to YAML."""
        path = self.storage_dir / f"{job.id}.yaml"
        data = {
            "id": job.id,
            "name": job.name,
            "trigger": job.trigger,
            "context_prime": job.context_prime,
            "skill_or_task": job.skill_or_task,
            "permissions": job.permissions,
            "retry_policy": job.retry_policy,
            "notification": job.notification,
            "enabled": job.enabled,
            "run_count": job.run_count,
            "fail_count": job.fail_count
        }
        with open(path, "w") as f:
            yaml.dump(data, f)
            
    def load_all(self) -> list[Job]:
        """Load all Job YAML files in the storage directory."""
        jobs = []
        for file in self.storage_dir.glob("*.yaml"):
            with open(file, "r") as f:
                data = yaml.safe_load(f)
                if data:
                    jobs.append(Job(**data))
        return jobs
