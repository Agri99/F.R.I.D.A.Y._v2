"""
Working memory (§13.1).
"""
from __future__ import annotations

from datetime import datetime
from friday.memory.database import MemoryDatabase

class ConversationMemory:
    """Manages short-term conversation context."""
    
    def __init__(self, db: MemoryDatabase | str | None = None, db_path: str | None = None, context_limit: int = 30):
        target_db = db or db_path
        if isinstance(target_db, str):
            self.db = MemoryDatabase(target_db)
        elif isinstance(target_db, MemoryDatabase):
            self.db = target_db
        else:
            self.db = MemoryDatabase()
        self.context_limit = context_limit
        self.default_session = "default"



    def load_context(self, system_prompt: str, session_id: str | None = None, limit: int = 30) -> list[dict]:
        """Load context window for model."""
        sid = session_id or self.default_session
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (sid, limit),
            ).fetchall()
            
        recent = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return [{"role": "system", "content": system_prompt}] + recent

    def append(self, role: str, content: str, session_id: str | None = None) -> None:
        sid = session_id or self.default_session
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (sid, role, content, datetime.now().isoformat(timespec="seconds")),
            )

    def clear_session(self, session_id: str | None = None) -> None:
        sid = session_id or self.default_session
        with self.db.connection() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
