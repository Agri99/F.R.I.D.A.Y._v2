"""
Episodic memory (§13.1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from friday.memory.database import MemoryDatabase

@dataclass
class Episode:
    task_id: str
    goal: str
    steps: list[dict]
    outcome: str
    duration: float
    created_at: str

class EpisodicMemory:
    """Manages episodic memory of past tasks."""
    
    def __init__(self, db: MemoryDatabase):
        self.db = db

    def record_episode(self, task_id: str, goal: str, steps: list[dict], outcome: str, duration: float) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        steps_json = json.dumps(steps)
        with self.db.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO episodes (task_id, goal, steps, outcome, duration, created_at) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, goal, steps_json, outcome, duration, now)
            )
            row_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO episodes_fts (rowid, goal, steps, outcome) VALUES (?, ?, ?, ?)",
                (row_id, goal, steps_json, outcome)
            )

    def recall_similar(self, goal: str, limit: int = 5) -> list[Episode]:
        """Recall episodes similar to current goal using FTS5."""
        with self.db.connection() as conn:
            rows = conn.execute(
                """SELECT e.task_id, e.goal, e.steps, e.outcome, e.duration, e.created_at
                   FROM episodes_fts f
                   JOIN episodes e ON f.rowid = e.id
                   WHERE episodes_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (goal, limit)
            ).fetchall()
            
        return [
            Episode(
                task_id=r["task_id"],
                goal=r["goal"],
                steps=json.loads(r["steps"]),
                outcome=r["outcome"],
                duration=r["duration"],
                created_at=r["created_at"]
            )
            for r in rows
        ]
