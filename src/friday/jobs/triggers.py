"""Event trigger monitors for proactive jobs."""
from __future__ import annotations

import time
import threading
import psutil
from datetime import datetime
from typing import Callable, Optional
from dataclasses import dataclass

from friday.jobs.scheduler import Job, TriggerType, JobScheduler
from friday.online.network import NetworkMonitor


@dataclass
class TriggerContext:
    """Context passed to trigger handlers."""
    trigger_type: str
    timestamp: datetime
    metadata: dict = None


class TriggerMonitor:
    """Monitors system events and triggers jobs based on conditions."""

    def __init__(self, scheduler: JobScheduler):
        self.scheduler = scheduler
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._network_monitor: Optional[NetworkMonitor] = None
        self._last_network_state: Optional[bool] = None
        self._last_idle_check: float = 0
        self._idle_threshold_seconds = 60  # seconds of inactivity before considered idle
        self._last_resource_check: float = 0
        self._resource_thresholds = {
            "cpu_percent": 80.0,
            "ram_percent": 85.0,
            "disk_percent": 90.0,
        }

    def start(self) -> None:
        """Start the trigger monitoring thread."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

        # Initialize network monitor for network change detection
        self._network_monitor = NetworkMonitor()
        self._network_monitor.start_background_probing()

    def stop(self) -> None:
        """Stop the trigger monitoring thread."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        if self._network_monitor:
            self._network_monitor.stop_background_probing()

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while not self._stop_event.is_set():
            try:
                self._check_idle_trigger()
                self._check_network_change()
                self._check_resource_conditions()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.exception("Error in trigger monitor loop: %s", e)

            self._stop_event.wait(5.0)  # Check every 5 seconds

    def _check_idle_trigger(self) -> None:
        """Check if system has been idle long enough to trigger idle jobs."""
        try:
            # Check CPU and input activity as proxy for user activity
            cpu_percent = psutil.cpu_percent(interval=0.1)
            current_time = time.time()

            if cpu_percent < 5.0:  # Low CPU usage indicates potential idle
                if self._last_idle_check == 0:
                    self._last_idle_check = time.time()
                elif time.time() - self._last_idle_check >= self._idle_threshold_seconds:
                    self._trigger_jobs(TriggerType.IDLE)
                    self._last_idle_check = time.time()  # Reset to avoid repeated triggers
            else:
                self._last_idle_check = 0
        except Exception:
            pass

    def _check_network_change(self) -> None:
        """Check for network connectivity changes."""
        if not self._network_monitor:
            return

        try:
            current_online = self._network_monitor.is_online()
            if self._last_network_state is None:
                self._last_network_state = current_online
            elif current_online != self._last_network_state:
                self._trigger_jobs(TriggerType.NETWORK_CHANGE)
                self._last_network_state = current_online
        except Exception:
            pass

    def _check_resource_conditions(self) -> None:
        """Check for resource condition triggers (CPU, RAM, disk thresholds)."""
        try:
            current_time = time.time()
            if current_time - self._last_resource_check < 30:  # Check every 30 seconds
                return
            self._last_resource_check = current_time

            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\")

            triggered = False
            metadata = {}

            if cpu >= self._resource_thresholds["cpu_percent"]:
                triggered = True
                metadata["cpu_percent"] = cpu

            if mem.percent >= self._resource_thresholds["ram_percent"]:
                triggered = True
                metadata["ram_percent"] = mem.percent

            if disk.percent >= self._resource_thresholds["disk_percent"]:
                triggered = True
                metadata["disk_percent"] = disk.percent

            if triggered:
                self._trigger_jobs(TriggerType.RESOURCE_CONDITION, metadata)
        except Exception:
            pass

    def _trigger_jobs(self, trigger_type: TriggerType, metadata: dict = None) -> None:
        """Find and execute jobs matching the trigger type."""
        for job in self.scheduler.jobs.values():
            if not job.enabled:
                continue
            if job.trigger == trigger_type.value:
                # Check if job has appropriate capabilities
                if not self._check_job_capabilities(job):
                    continue

                # Execute job
                try:
                    from friday.jobs.executor import JobExecutor
                    executor = JobExecutor()
                    # Get orchestrator if available
                    orchestrator = None
                    if hasattr(self.scheduler, "orchestrator_factory") and self.scheduler.orchestrator_factory:
                        orchestrator = self.scheduler.orchestrator_factory()

                    result = executor.execute(job, orchestrator)
                    self.scheduler.mark_completed(job.id, result.success, result)

                    # Log trigger
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"Triggered job {job.id} ({job.name}) by {trigger_type.value}")
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.exception(f"Failed to trigger job {job.id}: {e}")

    def _check_job_capabilities(self, job) -> bool:
        """Check if job has required capabilities available."""
        # Simple check - could be enhanced with actual capability registry
        for cap in job.capabilities:
            if cap.startswith(("browser.", "online.", "live_data")):
                # Check if online - simplified check
                try:
                    import urllib.request
                    urllib.request.urlopen("http://www.google.com", timeout=2)
                except Exception:
                    return False
        return True