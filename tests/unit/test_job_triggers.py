"""Job trigger tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from friday.jobs.scheduler import (
    Job, JobScheduler, JobBudget, ExecutionWindow,
    TriggerType, FailurePolicy, VerificationType
)
from friday.jobs.triggers import TriggerMonitor


class FakeJob:
    def __init__(self, trigger="idle", enabled=True):
        self.id = "test_job"
        self.name = "Test Job"
        self.trigger = trigger
        self.enabled = enabled
        self.capabilities = []

    def get_active_window(self):
        class Win:
            title = "Test"
        return Win()


class FakeScheduler:
    def __init__(self, jobs=None):
        self.jobs = {job.id: job for job in (jobs or [])}
        self.orchestrator_factory = None


@patch("friday.jobs.triggers.psutil.cpu_percent", return_value=2.0)
def test_idle_trigger(mock_cpu):
    mock_scheduler = FakeScheduler([
        FakeJob(trigger="idle", enabled=True),
        FakeJob(trigger="online", enabled=True),
    ])

    monitor = TriggerMonitor(mock_scheduler)
    # Just test that the monitor can be created and started/stopped
    monitor.start()
    monitor.stop()


@patch("friday.jobs.triggers.NetworkMonitor")
@patch("friday.jobs.triggers.psutil.cpu_percent", return_value=2.0)
def test_network_change_trigger(mock_cpu, MockNetworkMonitor):
    mock_network = MagicMock()
    mock_network.is_online.side_effect = [True, False]  # State change
    MockNetworkMonitor.return_value = mock_network

    mock_scheduler = FakeScheduler([
        FakeJob(trigger="network_change", enabled=True),
    ])

    monitor = TriggerMonitor(mock_scheduler)
    monitor.start()
    # Simulate one loop iteration
    monitor._check_network_change()
    monitor.stop()


@patch("friday.jobs.triggers.psutil.cpu_percent", return_value=90.0)
@patch("friday.jobs.triggers.psutil.virtual_memory")
@patch("friday.jobs.triggers.psutil.disk_usage")
def test_resource_condition_trigger(mock_disk, mock_mem, mock_cpu):
    mock_mem.return_value.percent = 90.0
    mock_disk.return_value.percent = 50.0

    mock_scheduler = FakeScheduler([
        FakeJob(trigger="resource_condition", enabled=True),
    ])

    monitor = TriggerMonitor(FakeScheduler([
        FakeJob(trigger="resource_condition", enabled=True),
    ]))
    monitor._resource_thresholds = {"cpu_percent": 80.0, "ram_percent": 85.0, "disk_percent": 90.0}
    monitor._last_resource_check = 0
    monitor._check_resource_conditions()


def test_trigger_type_enum_values():
    assert TriggerType.STARTUP.value == "startup"
    assert TriggerType.IDLE.value == "idle"
    assert TriggerType.NETWORK_CHANGE.value == "network_change"
    assert TriggerType.RESOURCE_CONDITION.value == "resource_condition"
    assert TriggerType.APPLICATION_EVENT.value == "application_event"
    assert TriggerType.CALENDAR_LEAD_TIME.value == "calendar_lead_time"