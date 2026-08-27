import sqlite3
from pathlib import Path

db_path = Path("data/friday.db")
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in tables:
        if t in ("messages", "conversation_turns", "trajectories", "interactions"):
            conn.execute(f"DELETE FROM {t}")
            print(f"Cleared table: {t}")
    conn.commit()
    conn.close()
    print("Conversation history wiped cleanly.")
else:
    print("Database does not exist yet.")

