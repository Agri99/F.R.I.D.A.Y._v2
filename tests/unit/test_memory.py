"""
Test memory.
"""
from friday.memory.database import MemoryDatabase
from friday.memory.conversation import ConversationMemory
from friday.memory.episodic import EpisodicMemory
from friday.memory.semantic import SemanticMemory

def test_memory_conversation_persistence(tmp_path):
    db = MemoryDatabase(tmp_path / "test.db")
    conv = ConversationMemory(db)
    conv.append("user", "hello")
    msgs = conv.load_context("system prompt")
    assert len(msgs) == 2

def test_memory_episodic_recall(tmp_path):
    db = MemoryDatabase(tmp_path / "test.db")
    ep = EpisodicMemory(db)
    ep.record_episode("1", "test goal", [], "DONE", 1.0)
    res = ep.recall_similar("test")
    assert len(res) == 1

def test_memory_fact_storage_and_search(tmp_path):
    db = MemoryDatabase(tmp_path / "test.db")
    sem = SemanticMemory(db)
    sem.store_fact("sky", "is", "blue")
    res = sem.recall("sky")
    assert len(res) == 1
