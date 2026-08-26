"""
src/friday/jobs/__init__.py

WHAT THIS IS FOR:
Exports key classes for the proactive jobs subsystem, allowing scheduled
and event-driven execution of tasks in the background.
"""

from __future__ import annotations

from friday.jobs.scheduler import Job, JobScheduler
from friday.jobs.registry import JobRegistry
from friday.jobs.executor import JobExecutor

__all__ = ["Job", "JobScheduler", "JobRegistry", "JobExecutor"]
