"""In-memory plugin registry."""
from __future__ import annotations

from friday.plugins.lifecycle import PluginRecord, PluginState


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginRecord] = {}

    def register(self, record: PluginRecord) -> None:
        key = record.manifest.name.lower()
        existing = self._plugins.get(key)
        if existing and existing.state == PluginState.ACTIVE:
            record.previous_version = existing.manifest.version
        self._plugins[key] = record

    def get(self, name: str) -> PluginRecord | None:
        return self._plugins.get(name.lower())

    def list_all(self) -> list[PluginRecord]:
        return list(self._plugins.values())

    def list_active(self) -> list[PluginRecord]:
        return [record for record in self._plugins.values() if record.state == PluginState.ACTIVE]

    def remove(self, name: str) -> PluginRecord | None:
        return self._plugins.pop(name.lower(), None)
