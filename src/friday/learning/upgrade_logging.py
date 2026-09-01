"""Durable, visible reports for trusted autonomous upgrades."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from friday.security.audit import AuditLogger


@dataclass
class UpgradeReport:
    upgrade_id: str
    task_id: str
    component: str
    old_version: str
    new_version: str
    reason: str
    observed_limitation: str = ""
    changes: list[str] = field(default_factory=list)
    tests: dict[str, str] = field(default_factory=dict)
    security: str = "PASS"
    performance_before: dict[str, Any] = field(default_factory=dict)
    performance_after: dict[str, Any] = field(default_factory=dict)
    rollback: str = "available"
    status: str = "PROMOTED"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class UpgradeLogger:
    def __init__(self, root: str | Path = "data/upgrades", audit: AuditLogger | None = None) -> None:
        self.root = Path(root)
        self.audit = audit or AuditLogger()

    def write(self, report: UpgradeReport, open_editor: bool = True) -> tuple[Path, Path]:
        date_dir = self.root / report.timestamp[:10]
        date_dir.mkdir(parents=True, exist_ok=True)
        timestamp = report.timestamp.replace(":", "-").replace("+", "_").replace(".", "-")
        json_path = date_dir / f"upgrade_{timestamp}.json"
        md_path = date_dir / f"upgrade_{timestamp}.md"

        # Atomic write: render both, flush both to disk, fsync, then notify.
        json_blob = json.dumps(asdict(report), indent=2, default=str)
        md_blob = self._render_markdown(report)
        with open(json_path, "w", encoding="utf-8") as fh:
            fh.write(json_blob)
            fh.flush()
            os.fsync(fh.fileno())
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(md_blob)
            fh.flush()
            os.fsync(fh.fileno())

        notification = "not requested"
        if open_editor:
            try:
                notification = "opened" if open_report_in_editor(md_path) else "failed"
            except Exception as exc:
                notification = f"failed: {exc}"
        self.audit.log_tool_execution(
            task_id=report.task_id,
            tool="upgrade.report_notification",
            risk="GREEN",
            arguments={"upgrade_id": report.upgrade_id, "report": str(md_path)},
            result=notification,
            verification={"report_exists": md_path.exists(), "notification": notification},
        )
        return json_path, md_path

    @staticmethod
    def _render_markdown(report: UpgradeReport) -> str:
        changes = "\n".join(f"- {change}" for change in report.changes) or "- none"
        tests = "\n".join(f"- {name}: {result}" for name, result in report.tests.items()) or "- not recorded"
        return f"""# FRIDAY Autonomous Upgrade

Upgrade ID: {report.upgrade_id}
Task ID: {report.task_id}
Timestamp: {report.timestamp}

Component: {report.component}
Old version: {report.old_version}
New version: {report.new_version}

Reason: {report.reason}
Observed limitation: {report.observed_limitation}

Changes:
{changes}

Tests:
{tests}

Security:
{report.security}

Performance:
before: {json.dumps(report.performance_before, default=str)}
after: {json.dumps(report.performance_after, default=str)}

Rollback:
{report.rollback}

Status:
{report.status}
"""


def open_report_in_editor(path: str | Path, editor: str | None = None) -> bool:
    """Open an upgrade report after it has been fully flushed to disk."""
    target = Path(path).resolve()
    if not target.exists():
        return False
    try:
        configured = editor or os.environ.get("FRIDAY_EDITOR") or os.environ.get("EDITOR")
        if configured:
            subprocess.Popen([configured, str(target)])
        elif os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return True
    except Exception:
        return False


__all__ = ["UpgradeLogger", "UpgradeReport", "open_report_in_editor"]
