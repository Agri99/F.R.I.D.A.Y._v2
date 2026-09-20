"""
src/friday/lifecycle/crash_recovery.py

WHAT THIS IS FOR:
Crash recovery (Runbook §42 — Phase T3).

On restart:
  1. Detect incomplete task
  2. Reconcile task state
  3. Avoid blindly repeating dangerous actions
  4. Restore memory/config
  5. Restore jobs
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """Task execution state."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class IncompleteTask:
    """Represents a task that was interrupted."""
    task_id: str
    state: TaskState
    name: str
    start_time: float
    last_update_time: float
    action: str
    arguments: dict[str, Any]
    step: int
    total_steps: int
    observation: Optional[str] = None


class CrashRecoveryManager:
    """Detects and recovers from crashes."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.checkpoint_file = data_dir / "incomplete_tasks.json"
        self.recovery_file = data_dir / "recovery_state.json"

    def detect_incomplete_tasks(self) -> list[IncompleteTask]:
        """Find tasks that were incomplete at last shutdown."""
        tasks = []

        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file) as f:
                    data = json.load(f)

                for task_data in data.get("tasks", []):
                    if task_data["state"] in ["pending", "running", "interrupted"]:
                        task = IncompleteTask(
                            task_id=task_data["task_id"],
                            state=TaskState(task_data["state"]),
                            name=task_data["name"],
                            start_time=task_data["start_time"],
                            last_update_time=task_data["last_update_time"],
                            action=task_data["action"],
                            arguments=task_data["arguments"],
                            step=task_data["step"],
                            total_steps=task_data["total_steps"],
                            observation=task_data.get("observation"),
                        )
                        tasks.append(task)
                        logger.warning(
                            f"Found incomplete task: {task.name} "
                            f"(step {task.step}/{task.total_steps})"
                        )
            except Exception as e:
                logger.error(f"Error reading checkpoint: {e}")

        return tasks

    def should_retry_task(self, task: IncompleteTask) -> bool:
        """Determine if a task should be retried.

        Do not retry:
          - Destructive actions (delete, drop, remove)
          - Financial/payment actions
          - SendEmail/SendSMS actions
          - Any action that requires explicit confirmation
        """
        dangerous_actions = {
            "delete",
            "drop",
            "remove",
            "unlink",
            "send_email",
            "send_sms",
            "payment",
            "transfer",
            "publish",
            "deploy",
        }

        # Check if action name contains dangerous keyword
        action_lower = task.action.lower()
        for dangerous in dangerous_actions:
            if dangerous in action_lower:
                logger.warning(f"Refusing to auto-retry destructive action: {task.action}")
                return False

        # Check if task has been running too long
        import time
        elapsed = time.time() - task.start_time
        if elapsed > 3600:  # 1 hour
            logger.warning(f"Task {task.name} has been running for {elapsed}s, not retrying")
            return False

        return True

    def reconcile_task_state(self, task: IncompleteTask) -> dict[str, Any]:
        """Reconcile the task's state with the current system state.

        Returns:
          dict with 'action' (retry, skip, ask), 'reason', 'safe_to_retry'
        """
        try:
            # Check if the action was partially completed
            observation = task.observation or ""

            # If we have a positive observation, action may have succeeded
            if "success" in observation.lower() or "completed" in observation.lower():
                return {
                    "action": "skip",
                    "reason": "Task appears to have completed before crash",
                    "safe_to_retry": False,
                }

            # If we have a clear error, don't retry
            if "error" in observation.lower() or "failed" in observation.lower():
                return {
                    "action": "skip",
                    "reason": f"Task failed: {observation}",
                    "safe_to_retry": False,
                }

            # Check if task is destructive
            if not self.should_retry_task(task):
                return {
                    "action": "ask",
                    "reason": f"Destructive action ({task.action}), requires user confirmation",
                    "safe_to_retry": False,
                }

            # Safe to retry
            return {
                "action": "retry",
                "reason": f"Task interrupted at step {task.step}/{task.total_steps}",
                "safe_to_retry": True,
            }

        except Exception as e:
            logger.error(f"Error reconciling task state: {e}")
            return {
                "action": "ask",
                "reason": f"Error during reconciliation: {e}",
                "safe_to_retry": False,
            }

    def restore_memory(self, data_dir: Path) -> dict[str, Any]:
        """Restore memory from last checkpoint."""
        memory = {
            "episodic": {},
            "semantic": {},
            "procedural": {},
        }

        memory_file = data_dir / "memory_checkpoint.json"
        if memory_file.exists():
            try:
                with open(memory_file) as f:
                    saved = json.load(f)
                memory.update(saved)
                logger.info(f"Restored memory with {len(saved)} entries")
            except Exception as e:
                logger.error(f"Error restoring memory: {e}")

        return memory

    def restore_jobs(self, data_dir: Path) -> list[dict[str, Any]]:
        """Restore scheduled jobs."""
        jobs = []

        jobs_file = data_dir / "jobs_checkpoint.json"
        if jobs_file.exists():
            try:
                with open(jobs_file) as f:
                    jobs = json.load(f)
                logger.info(f"Restored {len(jobs)} scheduled jobs")
            except Exception as e:
                logger.error(f"Error restoring jobs: {e}")

        return jobs

    def checkpoint_task(self, task: IncompleteTask) -> None:
        """Save task state for crash recovery."""
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        tasks_data = []
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file) as f:
                    data = json.load(f)
                tasks_data = data.get("tasks", [])
            except Exception:
                pass

        # Update or add task
        task_dict = {
            "task_id": task.task_id,
            "state": task.state.value,
            "name": task.name,
            "start_time": task.start_time,
            "last_update_time": task.last_update_time,
            "action": task.action,
            "arguments": task.arguments,
            "step": task.step,
            "total_steps": task.total_steps,
            "observation": task.observation,
        }

        # Replace existing or add new
        tasks_data = [t for t in tasks_data if t["task_id"] != task.task_id]
        tasks_data.append(task_dict)

        with open(self.checkpoint_file, "w") as f:
            json.dump({"tasks": tasks_data}, f, indent=2)

    def clear_recovery_checkpoint(self) -> None:
        """Clear checkpoint after successful recovery."""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
            logger.info("Cleared recovery checkpoint")


class RecoveryPlan:
    """Represents a recovery action plan."""

    def __init__(self, incomplete_tasks: list[IncompleteTask]):
        self.tasks = incomplete_tasks
        self.decisions: dict[str, dict[str, Any]] = {}
        self.recovery_manager = CrashRecoveryManager(Path("data"))

    def build_plan(self) -> dict[str, Any]:
        """Build recovery plan for all incomplete tasks."""
        plan = {
            "total_tasks": len(self.tasks),
            "actions": [],
            "requires_user_input": False,
        }

        for task in self.tasks:
            decision = self.recovery_manager.reconcile_task_state(task)
            self.decisions[task.task_id] = decision

            plan["actions"].append({
                "task_id": task.task_id,
                "name": task.name,
                "action": decision["action"],
                "reason": decision["reason"],
                "safe_to_retry": decision["safe_to_retry"],
            })

            if decision["action"] == "ask":
                plan["requires_user_input"] = True

        return plan

    def execute_plan(self) -> dict[str, Any]:
        """Execute recovery plan."""
        results = {
            "retried": [],
            "skipped": [],
            "awaiting_user": [],
        }

        for task in self.tasks:
            decision = self.decisions.get(task.task_id)
            if not decision:
                continue

            if decision["action"] == "retry":
                results["retried"].append({
                    "task_id": task.task_id,
                    "name": task.name,
                    "step": task.step,
                })
                logger.info(f"Will retry: {task.name}")

            elif decision["action"] == "skip":
                results["skipped"].append({
                    "task_id": task.task_id,
                    "name": task.name,
                    "reason": decision["reason"],
                })
                logger.info(f"Skipping: {task.name} ({decision['reason']})")

            else:  # ask
                results["awaiting_user"].append({
                    "task_id": task.task_id,
                    "name": task.name,
                    "reason": decision["reason"],
                })
                logger.warning(f"Awaiting user decision: {task.name}")

        return results


__all__ = [
    "TaskState",
    "IncompleteTask",
    "CrashRecoveryManager",
    "RecoveryPlan",
]
