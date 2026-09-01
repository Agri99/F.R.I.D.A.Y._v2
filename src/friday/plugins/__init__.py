"""Hot-swappable plugin lifecycle with trusted-core validation."""

from friday.plugins.api import Plugin, PluginContext
from friday.plugins.lifecycle import PluginLifecycle, PluginRecord, PluginState
from friday.plugins.loader import PluginLoader
from friday.plugins.manifest import PluginManifest
from friday.plugins.registry import PluginRegistry

__all__ = [
    "Plugin",
    "PluginContext",
    "PluginLifecycle",
    "PluginLoader",
    "PluginManifest",
    "PluginRecord",
    "PluginRegistry",
    "PluginState",
]
