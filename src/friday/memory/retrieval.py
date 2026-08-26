"""
Unified memory retrieval (§28).
"""
from __future__ import annotations

from dataclasses import dataclass
from friday.memory.database import MemoryDatabase
from friday.memory.conversation import ConversationMemory
from friday.memory.episodic import EpisodicMemory, Episode
from friday.memory.semantic import SemanticMemory, Fact
from friday.memory.preferences import PreferenceMemory, Preference

@dataclass
class RetrievalResult:
    conversations: list[dict]
    episodes: list[Episode]
    facts: list[Fact]
    preferences: list[Preference]
    skills: list[str]  # Just names for now

class MemoryRetriever:
    """Unified access to all memory stores."""
    
    def __init__(self, db: MemoryDatabase):
        self.db = db
        self.conversations = ConversationMemory(db)
        self.episodes = EpisodicMemory(db)
        self.semantic = SemanticMemory(db)
        self.preferences = PreferenceMemory(db)

    def retrieve_relevant(self, query: str, task_context: str | None = None) -> RetrievalResult:
        """Retrieve relevant context across all memory types before sending to LLM."""
        
        # In a real implementation, we'd use embedding search or FTS based on the query.
        # Here we just exercise the FTS layers.
        search_term = query
        if not search_term.strip():
            search_term = "default"
            
        # Clean query for simple FTS matching (alphanumeric only)
        clean_query = "".join(c for c in search_term if c.isalnum() or c.isspace()).strip()
        if not clean_query:
            clean_query = "nothing"
            
        episodes = []
        try:
            episodes = self.episodes.recall_similar(clean_query, limit=3)
        except Exception:
            pass # FTS syntax error
            
        facts = []
        try:
            facts = self.semantic.recall(clean_query, limit=5)
        except Exception:
            pass
            
        prefs = []
        
        # Load conversation memory, excluding system prompt for this aggregate
        conv_hist = self.conversations.load_context("", limit=10)[1:]
        
        return RetrievalResult(
            conversations=conv_hist,
            episodes=episodes,
            facts=facts,
            preferences=prefs,
            skills=[]
        )
