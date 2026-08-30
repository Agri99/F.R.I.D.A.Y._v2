"""
Context Priming Engine (§13).
Builds task-specific context bundles before planning.

Pipeline: User request → Task classification → Relevant memory → Project knowledge → Preferences → Relevant skills → Bounded context → Planner

Context is: relevant, bounded, ranked, source-aware, confidence-aware.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum


class TaskType(Enum):
    COMPUTER_USE = "computer_use"
    WEB_SEARCH = "web_search"
    FILE_OPERATION = "file_operation"
    SYSTEM_CONTROL = "system_control"
    COMMUNICATION = "communication"
    CODING = "coding"
    GENERAL_QUERY = "general_query"
    UNKNOWN = "unknown"


@dataclass
class PrimedContext:
    relevant_memories: list[dict] = field(default_factory=list)
    relevant_projects: list[dict] = field(default_factory=list)
    relevant_preferences: list[dict] = field(default_factory=list)
    relevant_skills: list[dict] = field(default_factory=list)
    known_failures: list[dict] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    summary: str = ""
    task_type: TaskType = TaskType.UNKNOWN
    confidence: float = 0.0
    bounded_context_tokens: int = 0


class ContextPrimingEngine:
    def __init__(self, memory_db: Any, skill_registry: Any, preference_store: Any):
        self.memory_db = memory_db
        self.skill_registry = skill_registry
        self.preference_store = preference_store
        self._task_keywords = {
            TaskType.COMPUTER_USE: ["click", "type", "open", "close", "window", "app", "screen", "ui"],
            TaskType.WEB_SEARCH: ["search", "find", "look up", "google", "web", "online"],
            TaskType.FILE_OPERATION: ["file", "folder", "directory", "read", "write", "delete", "copy", "move"],
            TaskType.SYSTEM_CONTROL: ["shutdown", "restart", "lock", "volume", "audio", "system"],
            TaskType.COMMUNICATION: ["email", "send", "message", "calendar", "meeting", "contact"],
            TaskType.CODING: ["code", "script", "program", "debug", "run", "python", "javascript", "terminal"],
        }

    def prime(self, user_goal: str, conversation_history: list[dict] | None = None) -> PrimedContext:
        """Build task-specific context bundle from all memory sources."""

        # 1. Task Classification
        task_type = self._classify_task(user_goal)

        # 2. Extract keywords for search
        keywords = self._extract_keywords(user_goal, task_type)

        # 3. Search semantic memory (relevant, ranked by confidence)
        relevant_memories = self._search_semantic_memory(user_goal, keywords, limit=8)

        # 4. Search project knowledge
        relevant_projects = self._search_project_knowledge(user_goal, keywords, limit=5)

        # 5. Look up user preferences (source-aware)
        relevant_preferences = self._get_relevant_preferences(keywords)

        # 6. Find matching skills (bounded, ranked)
        relevant_skills = self._find_relevant_skills(user_goal, task_type, limit=5)

        # 7. Find known failures for similar tasks
        known_failures = self._find_known_failures(user_goal, task_type, limit=3)

        # 8. Determine required capabilities
        required_capabilities = self._determine_capabilities(user_goal, relevant_skills, task_type)

        # 9. Build bounded, ranked context
        context = PrimedContext(
            relevant_memories=relevant_memories,
            relevant_projects=relevant_projects,
            relevant_preferences=relevant_preferences,
            relevant_skills=relevant_skills,
            known_failures=known_failures,
            required_capabilities=required_capabilities,
            task_type=task_type,
        )

        # 10. Rank and bound context
        self._rank_and_bound_context(context, max_tokens=2000)

        # 11. Build summary
        context.summary = self._build_summary(context, user_goal)

        return context

    def _classify_task(self, goal: str) -> TaskType:
        """Classify task type from goal text."""
        goal_lower = goal.lower()
        scores = {}
        for task_type, keywords in self._task_keywords.items():
            score = sum(1 for kw in keywords if kw in goal_lower)
            if score > 0:
                scores[task_type] = score

        if scores:
            return max(scores, key=scores.get)
        return TaskType.GENERAL_QUERY

    def _extract_keywords(self, goal: str, task_type: TaskType) -> list[str]:
        """Extract relevant keywords for search."""
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "is", "was", "are", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "can", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them", "my", "your", "his", "its", "our", "their", "mine", "yours", "hers", "ours", "theirs", "this", "that", "these", "those", "am", "is", "are", "was", "were"}

        goal_lower = goal.lower()
        words = goal_lower.split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        # Add task-type specific keywords
        if task_type in self._task_keywords:
            keywords.extend([kw for kw in self._task_keywords[task_type] if kw in goal_lower])

        return list(set(keywords))

    def _search_semantic_memory(self, query: str, keywords: list[str], limit: int) -> list[dict]:
        """Search semantic memory, ranked by confidence."""
        if not hasattr(self.memory_db, 'search_by_relevance'):
            return []

        # Search with full query
        results = self.memory_db.search_by_relevance(query, limit=limit)

        # Also search with individual keywords for broader coverage
        for kw in keywords[:3]:
            kw_results = self.memory_db.search_by_relevance(kw, limit=3)
            for r in kw_results:
                if r not in results:
                    results.append(r)

        # Deduplicate and rank by confidence
        seen = set()
        unique = []
        for r in results:
            key = (r.get("subject"), r.get("predicate"), r.get("value"))
            if key not in seen:
                seen.add(key)
                unique.append(r)

        unique.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return unique[:limit]

    def _search_project_knowledge(self, query: str, keywords: list[str], limit: int) -> list[dict]:
        """Search project-specific knowledge."""
        if not hasattr(self.memory_db, 'search_by_relevance'):
            return []

        # Search for project facts
        project_results = []
        for kw in ["project", "repo", "repository", "codebase"] + keywords[:2]:
            results = self.memory_db.search_by_relevance(f"project {kw}", limit=limit)
            for r in results:
                if r.get("subject", "").startswith("project:"):
                    if r not in project_results:
                        project_results.append(r)

        project_results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return project_results[:limit]

    def _get_relevant_preferences(self, keywords: list[str]) -> list[dict]:
        """Get user preferences matching keywords, ranked by confidence."""
        if not hasattr(self.preference_store, 'list_preferences'):
            return []

        prefs = self.preference_store.list_preferences()
        relevant = []

        for pref in prefs:
            confidence = pref.confidence
            # Check keyword match
            matched = any(kw in pref.key.lower() for kw in keywords)
            if matched or confidence > 0.8:  # High confidence prefs always relevant
                relevant.append({
                    "key": pref.key,
                    "value": pref.value,
                    "confidence": confidence,
                    "source": "user_explicit",
                    "matched": matched
                })

        # Rank: matched + high confidence first
        relevant.sort(key=lambda x: (x["matched"], x["confidence"]), reverse=True)
        return relevant[:5]

    def _find_relevant_skills(self, goal: str, task_type: TaskType, limit: int) -> list[dict]:
        """Find skills relevant to the task."""
        if not hasattr(self.skill_registry, 'search_skills'):
            # Fallback: load from skill directory if available
            return self._load_skills_from_directory(goal, task_type, limit)

        skills = self.skill_registry.search_skills(goal)

        # Filter and rank by relevance
        ranked = []
        for skill in skills:
            skill_type = skill.get("risk_profile", "GREEN")
            triggers = skill.get("triggers", [])
            trigger_match = any(goal.lower() in t.lower() or t.lower() in goal.lower() for t in triggers)

            ranked.append({
                "name": skill.get("name", ""),
                "purpose": skill.get("purpose", ""),
                "triggers": triggers,
                "required_capabilities": skill.get("required_capabilities", []),
                "risk_profile": skill_type,
                "trigger_match": trigger_match,
                "source": "skill_registry",
            })

        ranked.sort(key=lambda x: (x["trigger_match"], -len(x.get("required_capabilities", []))), reverse=True)
        return ranked[:limit]

    def _load_skills_from_directory(self, goal: str, task_type: TaskType, limit: int) -> list[dict]:
        """Fallback: load skills from disk."""
        # Placeholder - would scan skills/ directory
        return []

    def _find_known_failures(self, goal: str, task_type: TaskType, limit: int) -> list[dict]:
        """Find known failures for similar tasks."""
        # Would query episodic memory for failed trajectories
        # Placeholder implementation
        return []

    def _determine_capabilities(self, goal: str, skills: list[dict], task_type: TaskType) -> list[str]:
        """Determine required capabilities from skills and task type."""
        caps = set()

        for skill in skills:
            caps.update(skill.get("required_capabilities", []))

        # Add task-type defaults
        type_caps = {
            TaskType.COMPUTER_USE: ["computer", "accessibility"],
            TaskType.WEB_SEARCH: ["browser", "online"],
            TaskType.FILE_OPERATION: ["filesystem"],
            TaskType.SYSTEM_CONTROL: ["system"],
            TaskType.COMMUNICATION: ["gmail", "calendar"],
            TaskType.CODING: ["terminal", "filesystem"],
        }

        if task_type in type_caps:
            caps.update(type_caps[task_type])

        return sorted(list(caps))

    def _rank_and_bound_context(self, context: PrimedContext, max_tokens: int = 2000) -> None:
        """Rank all context items by confidence/relevance and bound to token limit."""
        # Already ranked during retrieval, just track approximate token count
        # Estimate: 1 token ≈ 4 chars
        total_chars = 0

        for section in ["relevant_memories", "relevant_projects", "relevant_preferences", "relevant_skills", "known_failures"]:
            items = getattr(context, section)
            for item in items:
                total_chars += len(str(item))

        context.bounded_context_tokens = total_chars // 4
        context.confidence = self._compute_overall_confidence(context)

    def _compute_overall_confidence(self, context: PrimedContext) -> float:
        """Compute weighted confidence across all context items."""
        confidences = []
        weights = []

        for item in context.relevant_memories:
            confidences.append(item.get("confidence", 0.5))
            weights.append(1.0)

        for item in context.relevant_preferences:
            confidences.append(item.get("confidence", 0.5))
            weights.append(0.8)

        for item in context.relevant_skills:
            confidences.append(0.8 if item.get("trigger_match") else 0.5)
            weights.append(0.6)

        if not confidences:
            return 0.0

        return sum(c * w for c, w in zip(confidences, weights)) / sum(weights)

    def _build_summary(self, context: PrimedContext, goal: str) -> str:
        """Build concise context summary."""
        parts = [
            f"Goal: {goal}",
            f"Task: {context.task_type.value}",
            f"Memories: {len(context.relevant_memories)}",
            f"Projects: {len(context.relevant_projects)}",
            f"Prefs: {len(context.relevant_preferences)}",
            f"Skills: {len(context.relevant_skills)}",
            f"Failures: {len(context.known_failures)}",
            f"Capabilities: {', '.join(context.required_capabilities) or 'none'}",
            f"Confidence: {context.confidence:.1%}",
            f"Tokens: ~{context.bounded_context_tokens}",
        ]
        return " | ".join(parts)
