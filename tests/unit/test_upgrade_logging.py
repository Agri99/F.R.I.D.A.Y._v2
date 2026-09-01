from pathlib import Path

from friday.learning.upgrade_logging import UpgradeLogger, UpgradeReport


def test_upgrade_logger_writes_json_markdown_and_audit(tmp_path: Path):
    upgrades = tmp_path / "upgrades"
    audit = tmp_path / "audit"
    from friday.security.audit import AuditLogger

    logger = UpgradeLogger(upgrades, AuditLogger(audit))
    json_path, md_path = logger.write(UpgradeReport(
        upgrade_id="upgrade-1",
        task_id="task-1",
        component="plugin.sample",
        old_version="1.0.0",
        new_version="1.1.0",
        reason="Improve reliability",
        changes=["Added verification"],
        tests={"unit": "PASS", "sandbox": "PASS"},
    ), open_editor=False)

    assert json_path.exists()
    assert md_path.exists()
    assert "Status:\nPROMOTED" in md_path.read_text(encoding="utf-8")
    assert list(audit.glob("audit_*.jsonl"))
