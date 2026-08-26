"""
Context Priming Engine (§13).
Builds task-specific context bundles before planning.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass
class PrimedContext:
    relevant_memories: list[dict]
    relevant_projects: list[dict]
    relevant_preferences: list[dict]
    relevant_skills: list[dict]
    known_failures: list[dict]
    required_capabilities: list[str]
    summary: str

class ContextPrimingEngine:
    def __init__(self, memory_db: Any, skill_registry: Any, preference_store: Any):
        self.memory_db = memory_db
        self.skill_registry = skill_registry
        self.preference_store = preference_store

    def prime(self, user_goal: str, conversation_history: list[dict] | None = None) -> PrimedContext:
        """Build task-specific context bundle from all memory sources."""
        
        # 1. Extract keywords/intent from user_goal
        keywords = user_goal.lower().split()
        
        # 2. Search semantic memory for relevant knowledge
        # (Assuming memory_db has semantic attribute, or is SemanticMemory directly)
        # Using a mock-like implementation to fit the required structure
        relevant_memories = []
        if hasattr(self.memory_db, 'search_by_relevance'):
            relevant_memories = self.memory_db.search_by_relevance(user_goal, limit=5)
            
        # 3. Search episodic memory for similar past tasks
        # 4. Look up user preferences
        relevant_preferences = []
        if hasattr(self.preference_store, 'list_preferences'):
            for pref in self.preference_store.list_preferences():
                if any(kw in pref.key.lower() for kw in keywords):
                    relevant_preferences.append({"key": pref.key, "value": pref.value})
        
        # 5. Find matching skills
        relevant_skills = []
        if hasattr(self.skill_registry, 'search_skills'):
            relevant_skills = self.skill_registry.search_skills(user_goal)
            
        # 6. Find known failures for similar tasks
        known_failures = []
        
        # 7. Determine required capabilities
        required_capabilities = []
        
        # 8. Build concise summary
        summary = f"Primed context for goal: '{user_goal}'. Found {len(relevant_memories)} memories, {len(relevant_preferences)} preferences, {len(relevant_skills)} skills."

        return PrimedContext(
            relevant_memories=relevant_memories,
            relevant_projects=[],
            relevant_preferences=relevant_preferences,
            relevant_skills=relevant_skills,
            known_failures=known_failures,
            required_capabilities=required_capabilities,
            summary=summary
        )
