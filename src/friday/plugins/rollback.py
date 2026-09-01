"""Plugin rollback support."""
from __future__ import annotations

from friday.plugins.lifecycle import PluginLifecycle, PluginRecord, PluginState
from friday.plugins.registry import PluginRegistry


class PluginRollbackManager:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry

    def rollback(self, failed: PluginRecord, previous: PluginRecord) -> PluginRecord:
        if failed.instance is not None:
            try:
                failed.instance.deactivate()
            except Exception:
                pass
        if failed.state not in {PluginState.FAILED, PluginState.ACTIVE, PluginState.CANARY}:
            raise ValueError(f"Cannot roll back plugin from {failed.state.value}")
        PluginLifecycle.transition(failed, PluginState.ROLLED_BACK)
        if previous.state == PluginState.DISABLED:
            PluginLifecycle.transition(previous, PluginState.VALIDATING)
            PluginLifecycle.transition(previous, PluginState.SANDBOXED)
            PluginLifecycle.transition(previous, PluginState.TESTED)
            PluginLifecycle.transition(previous, PluginState.CANARY)
            PluginLifecycle.transition(previous, PluginState.ACTIVE)
        self.registry.register(previous)
        return previous
