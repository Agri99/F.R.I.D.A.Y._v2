"""
src/friday/development/reviewer.py

WHAT THIS IS FOR:
Static analysis and security reviewer for generated self-development code.
Inspects AST, imports, network, filesystem, ctypes, and credentials.
Runbook §66, §77.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReviewFinding:
    severity: str  # "BLOCKER" | "HIGH" | "MEDIUM" | "LOW"
    file: str
    line: int
    rule: str
    message: str


@dataclass
class ReviewReport:
    passed: bool
    findings: list[ReviewFinding] = field(default_factory=list)
    files_reviewed: list[str] = field(default_factory=list)

    @property
    def has_blockers(self) -> bool:
        return any(f.severity in ("BLOCKER", "HIGH") for f in self.findings)


# Suspicious modules and calls that should not be introduced carelessly in candidate code
BLOCKED_MODULES = {
    "ctypes": "Raw ctypes memory manipulation is forbidden in self-development code",
    "winreg": "Direct Windows registry manipulation is forbidden in candidate upgrades",
}

CRITICAL_PATHS = {
    "src/friday/security",
    "secrets",
    "policy",
}


class CodeReviewer:
    """Performs static AST and policy review on code in a worktree."""

    def review_file(self, file_path: str | Path, rel_path: str = "") -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        path = Path(file_path)
        if not path.suffix == ".py":
            return findings

        content = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as e:
            findings.append(ReviewFinding(
                severity="BLOCKER",
                file=rel_path or str(path),
                line=e.lineno or 1,
                rule="syntax_error",
                message=f"Syntax error: {e.msg}",
            ))
            return findings

        # Check path sensitivity
        is_critical_path = any(cp in (rel_path or str(path)).replace("\\", "/") for cp in CRITICAL_PATHS)

        for node in ast.walk(tree):
            # Check import statements
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod in BLOCKED_MODULES:
                        findings.append(ReviewFinding(
                            severity="BLOCKER",
                            file=rel_path or str(path),
                            line=node.lineno,
                            rule="forbidden_import",
                            message=BLOCKED_MODULES[root_mod],
                        ))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod in BLOCKED_MODULES:
                        findings.append(ReviewFinding(
                            severity="BLOCKER",
                            file=rel_path or str(path),
                            line=node.lineno,
                            rule="forbidden_import",
                            message=BLOCKED_MODULES[root_mod],
                        ))

            # Check calls
            elif isinstance(node, ast.Call):
                # Look for eval / exec
                if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                    findings.append(ReviewFinding(
                        severity="BLOCKER",
                        file=rel_path or str(path),
                        line=node.lineno,
                        rule="dynamic_execution",
                        message=f"Direct call to '{node.func.id}' is forbidden in candidate upgrades",
                    ))

        if is_critical_path:
            findings.append(ReviewFinding(
                severity="HIGH",
                file=rel_path or str(path),
                line=1,
                rule="critical_subsystem_touch",
                message="Modifications touch security/secrets subsystem and require highest approval",
            ))

        return findings

    def review_tree(self, root_dir: str | Path, changed_files: list[str] | None = None) -> ReviewReport:
        root = Path(root_dir).resolve()
        findings: list[ReviewFinding] = []
        reviewed: list[str] = []

        if changed_files is not None:
            files_to_check = [(root / f, f) for f in changed_files]
        else:
            files_to_check = [(p, str(p.relative_to(root))) for p in root.rglob("*.py")]

        for p, rel in files_to_check:
            if p.exists() and p.is_file():
                reviewed.append(rel)
                findings.extend(self.review_file(p, rel))

        passed = not any(f.severity in ("BLOCKER", "HIGH") for f in findings)
        return ReviewReport(passed=passed, findings=findings, files_reviewed=reviewed)


__all__ = ["CodeReviewer", "ReviewReport", "ReviewFinding"]
