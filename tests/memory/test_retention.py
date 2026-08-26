from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from friday.memory.database import MemoryDatabase
from friday.memory.retention import RetentionManager, MemoryCandidate

@pytest.fixture
def memory_db(tmp_path):
    db_path = tmp_path / "test_memory.db"
    db = MemoryDatabase(db_path)
    return db

def test_should_retain():
    manager = RetentionManager(None)
    
    # Low confidence, not explicit
    c1 = MemoryCandidate(category="fact", content="foo", source="inferred", confidence=0.2, evidence_count=1, created_at=datetime.now(), updated_at=datetime.now())
    assert not manager.should_retain(c1)
    
    # Single mention >= 0.3
    c2 = MemoryCandidate(category="fact", content="bar", source="conversation", confidence=0.3, evidence_count=1, created_at=datetime.now(), updated_at=datetime.now())
    assert manager.should_retain(c2)
    
    # Explicit high confidence
    c3 = MemoryCandidate(category="fact", content="baz", source="user_explicit", confidence=0.95, evidence_count=1, created_at=datetime.now(), updated_at=datetime.now())
    assert manager.should_retain(c3)

def test_update_confidence(memory_db):
    manager = RetentionManager(memory_db)
    
    # Insert a dummy preference
    with memory_db.connection() as conn:
        conn.execute("INSERT INTO preferences (key, value, confidence, evidence_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                     ("color", "blue", 0.5, 1, "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        row_id = conn.execute("SELECT id FROM preferences WHERE key='color'").fetchone()["id"]
        
    # Update with new evidence
    new_conf = manager.update_confidence(str(row_id), "preference", True)
    assert new_conf > 0.5
    
    with memory_db.connection() as conn:
        row = conn.execute("SELECT evidence_count FROM preferences WHERE id=?", (row_id,)).fetchone()
        assert row["evidence_count"] == 2
        
    # Update with contradiction
    new_conf = manager.update_confidence(str(row_id), "preference", False)
    assert new_conf < 0.95 # should drop

def test_expire_stale(memory_db):
    manager = RetentionManager(memory_db)
    
    now = datetime.now()
    past = (now - timedelta(days=1)).isoformat()
    future = (now + timedelta(days=1)).isoformat()
    
    with memory_db.connection() as conn:
        # Expired fact
        conn.execute("INSERT INTO facts (subject, predicate, value, confidence, evidence_count, expiry, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     ("a", "is", "b", 0.8, 1, past, past))
        # Valid fact
        conn.execute("INSERT INTO facts (subject, predicate, value, confidence, evidence_count, expiry, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     ("c", "is", "d", 0.8, 1, future, past))
                     
    expired_count = manager.expire_stale()
    assert expired_count == 1
    
    with memory_db.connection() as conn:
        rows = conn.execute("SELECT confidence, expiry FROM facts ORDER BY id").fetchall()
        assert rows[0]["confidence"] == 0.0
        assert rows[1]["confidence"] == 0.8
