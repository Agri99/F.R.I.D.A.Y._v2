"""Plugin runtime health monitoring."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from friday.plugins.lifecycle import PluginRecord, PluginState


@dataclass(frozen=True)
class PluginHealth:
    healthy: bool
    checked_at: datetime
    detail: str = ""


class PluginHealthMonitor:
    def check(self, record: PluginRecord) -> PluginHealth:
        if record.state != PluginState.ACTIVE or record.instance is None:
            return PluginHealth(False, datetime.now(timezone.utc), "Plugin is not active")
        try:
            healthy = bool(record.instance.health())
            return PluginHealth(healthy, datetime.now(timezone.utc), "ok" if healthy else "health returned false")
        except Exception as exc:
            return PluginHealth(False, datetime.now(timezone.utc), str(exc))
