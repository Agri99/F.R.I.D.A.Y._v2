"""Dynamic plugin loading and hot replacement."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from friday.plugins.api import Plugin, PluginContext
from friday.plugins.lifecycle import PluginLifecycle, PluginRecord, PluginState
from friday.plugins.manifest import PluginManifest
from friday.plugins.registry import PluginRegistry
from friday.plugins.trust import PluginTrustValidator


class PluginLoader:
    def __init__(self, registry: PluginRegistry, trust: PluginTrustValidator) -> None:
        self.registry = registry
        self.trust = trust

    def discover(self, plugin_dir: str | Path) -> PluginRecord:
        root = Path(plugin_dir).resolve()
        manifest = PluginManifest.load(root / "plugin.yaml")
        record = PluginRecord(manifest=manifest, path=str(root))
        self.registry.register(record)
        return record

    def load(self, record: PluginRecord, services: dict[str, Any] | None = None) -> PluginRecord:
        PluginLifecycle.transition(record, PluginState.VALIDATING)
        decision = self.trust.validate(record.manifest)
        if not decision.approved:
            PluginLifecycle.transition(record, PluginState.FAILED, decision.reason)
            return record
        try:
            instance = self._instantiate(record)
        except Exception as exc:
            PluginLifecycle.transition(record, PluginState.FAILED, f"Instantiation failed: {exc}")
            return record
        PluginLifecycle.transition(record, PluginState.SANDBOXED)
        sandbox_result = self._run_sandbox_tests(record)
        if not sandbox_result.passed:
            PluginLifecycle.transition(record, PluginState.FAILED, f"Sandbox tests failed: {sandbox_result.stderr or sandbox_result.stdout}")
            return record
        PluginLifecycle.transition(record, PluginState.TESTED)
        try:
            PluginLifecycle.transition(record, PluginState.CANARY)
            instance.activate(PluginContext(decision.granted_capabilities, services or {}))
            if not instance.health():
                raise RuntimeError("Plugin health check failed during canary")
            record.instance = instance
            PluginLifecycle.transition(record, PluginState.ACTIVE)
            return record
        except Exception as exc:
            PluginLifecycle.transition(record, PluginState.FAILED, str(exc))
            return record

    def _run_sandbox_tests(self, record: PluginRecord) -> SandboxResult:
        from friday.plugins.sandbox import PluginSandbox
        sandbox = PluginSandbox(Path(record.path).parent)
        return sandbox.run_tests(Path(record.path))

    def hot_swap(self, active: PluginRecord, candidate: PluginRecord, services: dict[str, Any] | None = None) -> PluginRecord:
        loaded = self.load(candidate, services)
        if loaded.state != PluginState.ACTIVE:
            return loaded
        try:
            if active.instance is not None:
                active.instance.deactivate()
        except Exception as exc:
            loaded.instance.deactivate() if loaded.instance else None
            PluginLifecycle.transition(loaded, PluginState.FAILED, f"Hot swap failed during deactivation: {exc}")
            return loaded
        PluginLifecycle.transition(active, PluginState.DISABLED)
        self.registry.register(loaded)
        return loaded

    def _instantiate(self, record: PluginRecord) -> Plugin:
        module_name, factory_name = record.manifest.entrypoint.split(":", 1)
        module_path = Path(record.path) / (module_name.replace(".", "/") + ".py")
        if not module_path.exists():
            package_init = Path(record.path) / module_name.replace(".", "/") / "__init__.py"
            module_path = package_init
        if not module_path.exists():
            raise FileNotFoundError(f"Plugin entrypoint module not found: {module_name}")
        unique_name = f"friday_plugin_{record.manifest.name}_{record.manifest.version.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(unique_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[unique_name] = module
        spec.loader.exec_module(module)
        factory = getattr(module, factory_name)
        instance = factory()
        if not isinstance(instance, Plugin):
            raise TypeError("Plugin factory must return a Plugin instance")
        return instance
