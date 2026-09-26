"""
src/friday/development/generator.py

WHAT THIS IS FOR:
Proposes and generates upgrade candidates for FRIDAY.
Assigns unique IDs in format upgrade-YYYYMMDD-NNN.
Runbook §63, §64.
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class UpgradeCandidate:
    upgrade_id: str
    goal: str
    base_commit: str
    proposed_files: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    risk_tier: str = "ORANGE"  # Upgrades default to ORANGE; touching security is RED
    approved: bool = False
    status: str = "PENDING"


class ProposalGenerator:
    """Generates structured upgrade proposals and tracks ID sequencing."""

    def __init__(self, candidates_dir: str | Path = "workspace/self_development/candidates"):
        self.candidates_dir = Path(candidates_dir).resolve()
        self.candidates_dir.mkdir(parents=True, exist_ok=True)

    def next_upgrade_id(self) -> str:
        """Generate next upgrade ID for today: upgrade-YYYYMMDD-NNN."""
        today = datetime.date.today().strftime("%Y%m%d")
        existing = list(self.candidates_dir.glob(f"upgrade-{today}-*.json"))
        idx = len(existing) + 1
        return f"upgrade-{today}-{idx:03d}"

    def create_candidate(
        self,
        goal: str,
        base_commit: str,
        files: dict[str, str],
        risk_tier: str = "ORANGE",
    ) -> UpgradeCandidate:
        upgrade_id = self.next_upgrade_id()
        candidate = UpgradeCandidate(
            upgrade_id=upgrade_id,
            goal=goal,
            base_commit=base_commit,
            proposed_files=files,
            risk_tier=risk_tier,
        )
        file_path = self.candidates_dir / f"{upgrade_id}.json"
        file_path.write_text(json.dumps(asdict(candidate), indent=2), encoding="utf-8")
        return candidate


__all__ = ["ProposalGenerator", "UpgradeCandidate"]
