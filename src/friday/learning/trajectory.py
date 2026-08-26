"""
Trajectory recording (§14.1).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class Trajectory:
    task_id: str
    goal: str
    steps: list[dict] = field(default_factory=list)
    outcome: str = "UNKNOWN"
    duration: float = 0.0

class TrajectoryRecorder:
    """Records agent execution trajectories."""
    
    def __init__(self, data_dir: str | Path | None = None, trajectories_dir: str | Path | None = None):
        target_dir = trajectories_dir or data_dir or "data/trajectories"
        self.data_dir = Path(target_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._current: Trajectory | None = None
        self._start_time: float = 0.0


    def start(self, task_id: str, goal: str) -> None:
        self._current = Trajectory(task_id=task_id, goal=goal)
        self._start_time = time.time()

    def record_step(self, action: Any, observation: Any, result: Any) -> None:
        if not self._current:
            return
            
        self._current.steps.append({
            "action": action,
            "observation": observation,
            "result": result
        })

    def finish(self, outcome: str) -> Trajectory | None:
        if not self._current:
            return None
            
        self._current.outcome = outcome
        self._current.duration = time.time() - self._start_time
        
        # Save to JSONL
        out_file = self.data_dir / f"{self._current.task_id}.jsonl"
        with out_file.open("w", encoding="utf-8") as f:
            f.write(json.dumps({
                "task_id": self._current.task_id,
                "goal": self._current.goal,
                "outcome": self._current.outcome,
                "duration": self._current.duration,
                "steps": self._current.steps
            }) + "\n")
            
        result = self._current
        self._current = None
        return result
