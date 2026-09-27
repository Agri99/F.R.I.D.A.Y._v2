"""
tests/unit/test_development_tools.py

WHAT THIS IS FOR:
Proves the actual bug is fixed: FRIDAY had zero path from conversation
into the self-development/Docker subsystem, because no tool file existed
and build_orchestrator() never registered one. This checks the tools are
registered with the right safety tier, AND that build_orchestrator()
actually wires them in - not just that the module exists in isolation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from friday.tools.registry import ToolRegistry
from friday.tools.development import register_all_tools, _list_recent_reports


def test_propose_upgrade_tool_registers_as_red_and_critical():
    registry = ToolRegistry()
    register_all_tools(registry)

    tool = registry.get("development.propose_and_validate_upgrade")
    assert tool is not None
    assert tool.tier == "RED"
    assert tool.critical is True


def test_list_recent_reports_tool_registers_as_green():
    registry = ToolRegistry()
    register_all_tools(registry)

    tool = registry.get("development.list_recent_reports")
    assert tool is not None
    assert tool.tier == "GREEN"


def test_propose_upgrade_has_preview_and_verify():
    """Confirmation flow depends on these - without them, the ORANGE/RED
    confirmation step can't show what's about to happen or check it
    actually ran."""
    registry = ToolRegistry()
    register_all_tools(registry)

    tool = registry.get("development.propose_and_validate_upgrade")
    assert tool.preview is not None
    assert tool.verify is not None


def test_build_orchestrator_actually_registers_development_tools(tmp_path, monkeypatch):
    """The core bug: the module could exist perfectly and still never be
    reachable if build_orchestrator() didn't call register_all_tools()
    for it. This proves the real wiring, not just the module in isolation."""
    monkeypatch.chdir(tmp_path)
    from friday.app import build_orchestrator

    orch = build_orchestrator()
    names = orch.tool_registry.list_names()
    assert "development.propose_and_validate_upgrade" in names
    assert "development.list_recent_reports" in names


def test_list_recent_reports_empty_when_no_reports_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = _list_recent_reports()
    assert result == {"status": "ok", "reports": []}


def test_list_recent_reports_reads_real_report_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import json
    reports_dir = tmp_path / "workspace" / "self_development" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "upgrade-20260101-001_report.json").write_text(
        json.dumps({"upgrade_id": "upgrade-20260101-001", "stage": "ACTIVE", "passed": True, "error": None}),
        encoding="utf-8",
    )

    result = _list_recent_reports()
    assert result["status"] == "ok"
    assert len(result["reports"]) == 1
    assert result["reports"][0]["upgrade_id"] == "upgrade-20260101-001"
    assert result["reports"][0]["passed"] is True


def test_propose_upgrade_rejects_empty_proposed_files():
    from friday.tools.development import _propose_and_validate_upgrade
    result = _propose_and_validate_upgrade(goal="do nothing", proposed_files={})
    assert result["status"] == "error"
