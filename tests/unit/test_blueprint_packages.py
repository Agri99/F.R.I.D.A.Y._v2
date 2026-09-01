from friday.context.budget import ContextBudget
from friday.context.selector import ContextItem, ContextSelector
from friday.hardware.budget import ResourceBudget, ResourcePressure
from friday.hardware.telemetry import TelemetrySnapshot
from friday.models.base import ModelFormat, ModelSpec, Quantization
from friday.plugins.lifecycle import PluginLifecycle, PluginRecord, PluginState
from friday.plugins.manifest import PluginManifest
from friday.plugins.trust import PluginTrustValidator


def test_context_selector_respects_budget_and_deduplicates():
    selector = ContextSelector(ContextBudget(max_tokens=20, reserved_tokens=0, chars_per_token=1))
    selected = selector.select([
        ContextItem("important", "memory", 1.0, 1.0),
        ContextItem("important", "memory", 0.9, 1.0),
        ContextItem("also", "skill", 0.8, 1.0),
        ContextItem("too-long-for-budget", "memory", 0.7, 1.0),
    ])
    assert [item.content for item in selected] == ["important", "also"]


def test_resource_budget_reports_pressure():
    budget = ResourceBudget(max_cpu_percent=80, max_ram_percent=80, max_disk_percent=90)
    assert budget.evaluate(TelemetrySnapshot(cpu_percent=20, ram_percent=20, disk_percent=20)) == ResourcePressure.NORMAL
    assert budget.evaluate(TelemetrySnapshot(cpu_percent=70, ram_percent=20, disk_percent=20)) == ResourcePressure.ELEVATED
    assert budget.evaluate(TelemetrySnapshot(cpu_percent=90, ram_percent=20, disk_percent=20)) == ResourcePressure.CRITICAL


def test_model_spec_estimates_memory_by_quantization():
    q4 = ModelSpec("qwen", 8, ModelFormat.GGUF, Quantization.Q4_K_M, "llama.cpp", 32768, "reasoning")
    q6 = ModelSpec("qwen", 8, ModelFormat.GGUF, Quantization.Q6_K, "llama.cpp", 32768, "reasoning")
    assert q4.estimated_memory_gb < q6.estimated_memory_gb


def test_manifest_and_trust_reject_protected_capability():
    manifest = PluginManifest.from_dict({
        "name": "unsafe_plugin",
        "version": "1.0.0",
        "api_version": 1,
        "entrypoint": "plugin:create",
        "risk": "YELLOW",
        "capabilities": ["secrets.read"],
    })
    manifest.validate()
    decision = PluginTrustValidator({"secrets.read"}).validate(manifest)
    assert not decision.approved


def test_plugin_lifecycle_rejects_skipped_validation():
    manifest = PluginManifest("sample", "1.0.0", 1, "plugin:create", "GREEN", ("filesystem.read",))
    record = PluginRecord(manifest)
    try:
        PluginLifecycle.transition(record, PluginState.ACTIVE)
    except ValueError:
        pass
    else:
        raise AssertionError("Lifecycle allowed an unsafe transition")
