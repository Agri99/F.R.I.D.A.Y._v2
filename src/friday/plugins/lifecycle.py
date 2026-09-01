"""Plugin lifecycle state definitions."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from friday.plugins.manifest import PluginManifest


class PluginState(str, Enum):
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    SANDBOXED = "SANDBOXED"
    TESTED = "TESTED"
    CANARY = "CANARY"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    DISABLED = "DISABLED"
    ROLLED_BACK = "ROLLED_BACK"


_ALLOWED_TRANSITIONS = {
    PluginState.DISCOVERED: {PluginState.VALIDATING, PluginState.DISABLED},
    PluginState.VALIDATING: {PluginState.SANDBOXED, PluginState.FAILED},
    PluginState.SANDBOXED: {PluginState.TESTED, PluginState.FAILED},
    PluginState.TESTED: {PluginState.CANARY, PluginState.FAILED},
    PluginState.CANARY: {PluginState.ACTIVE, PluginState.FAILED, PluginState.ROLLED_BACK},
    PluginState.ACTIVE: {PluginState.DISABLED, PluginState.FAILED, PluginState.ROLLED_BACK},
    PluginState.FAILED: {PluginState.DISABLED, PluginState.ROLLED_BACK},
    PluginState.DISABLED: {PluginState.VALIDATING, PluginState.ROLLED_BACK},
    PluginState.ROLLED_BACK: {PluginState.DISABLED, PluginState.VALIDATING},
}


@dataclass
class PluginRecord:
    manifest: PluginManifest
    state: PluginState = PluginState.DISCOVERED
    instance: Any = None
    path: str = ""
    previous_version: str | None = None
    last_error: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PluginLifecycle:
    @staticmethod
    def transition(record: PluginRecord, target: PluginState, error: str | None = None) -> PluginRecord:
        if target not in _ALLOWED_TRANSITIONS[record.state]:
            raise ValueError(f"Invalid plugin transition: {record.state.value} -> {target.value}")
        record.state = target
        record.last_error = error
        record.updated_at = datetime.now(timezone.utc)
        return record
