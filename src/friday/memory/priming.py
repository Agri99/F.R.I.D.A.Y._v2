"""Context Priming Engine (§13).

Builds task-specific context bundles before planning.

Pipeline: User request → Task classification → Relevant memory → Project knowledge → Preferences → Relevant skills → Known failures → Bounded context → Planner
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from friday.context.budget import ContextBudget
from friday.context.selector import ContextItem, ContextSelector


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
    def __init__(
        self,
        memory_db: Any,
        skill_registry: Any,
        preference_store: Any,
        episodic_memory: Any | None = None,
        budget: ContextBudget | None = None,
    ) -> None:
        self.memory_db = memory_db
        self.skill_registry = skill_registry
        self.preference_store = preference_store
        self.episodic_memory = episodic_memory
        self.budget = budget or ContextBudget()
        self.selector = ContextSelector(self.budget)
        self._task_keywords = {
            TaskType.COMPUTER_USE: ["click", "type", "open", "close", "window", "app", "screen", "ui"],
            TaskType.WEB_SEARCH: ["search", "find", "look up", "google", "web", "online"],
            TaskType.FILE_OPERATION: ["file", "folder", "directory", "read", "write", "delete", "copy", "move"],
            TaskType.SYSTEM_CONTROL: ["shutdown", "restart", "lock", "volume", "audio", "system"],
            TaskType.COMMUNICATION: ["email", "send", "message", "calendar", "meeting", "contact"],
            TaskType.CODING: ["code", "script", "program", "debug", "run", "python", "javascript", "terminal"],
        }

    def prime(self, user_goal: str, conversation_history: list[dict] | None = None) -> PrimedContext:
        task_type = self._classify_task(user_goal)
        keywords = self._extract_keywords(user_goal, task_type)
        items: list[ContextItem] = []

        items.extend(self._search_semantic_memory_items(user_goal, keywords))
        items.extend(self._search_project_knowledge_items(user_goal, keywords))
        items.extend(self._preference_items(keywords))
        items.extend(self._skill_items(user_goal, task_type))
        items.extend(self._known_failure_items(user_goal))

        selected = self.selector.select(items)

        sections: dict[str, list[ContextItem]] = {name: [] for name in
            ("memories", "projects", "preferences", "skills", "failures")}
        for item in selected:
            kind = item.metadata.get("kind", "memory")
            sections.setdefault(kind, []).append(item)

        context = PrimedContext(
            relevant_memories=[item.metadata.get("raw", item.content) for item in sections["memories"]],
            relevant_projects=[item.content for item in sections["projects"]],
            relevant_preferences=[item.metadata.get("raw", item.content) for item in sections["preferences"]],
            relevant_skills=[item.content for item in sections["skills"]],
            known_failures=[item.content for item in sections["failures"]],
            task_type=task_type,
        )
        context.required_capabilities = self._determine_capabilities(user_goal, context.relevant_skills, task_type)
        context.bounded_context_tokens = sum(self.budget.estimate_tokens(str(item.content)) for item in selected)
        context.confidence = self._compute_overall_confidence(context)
        context.summary = self._build_summary(context, user_goal)
        return context

    def _classify_task(self, goal: str) -> TaskType:
        goal_lower = goal.lower()
        scores: dict[TaskType, int] = {}
        for task_type, keywords in self._task_keywords.items():
            score = sum(1 for kw in keywords if kw in goal_lower)
            if score > 0:
                scores[task_type] = score
        if scores:
            return max(scores, key=scores.get)
        return TaskType.GENERAL_QUERY

    def _extract_keywords(self, goal: str, task_type: TaskType) -> list[str]:
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
            "by", "from", "as", "is", "was", "are", "were", "be", "been", "being", "have", "has",
            "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must",
            "can", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
            "my", "your", "his", "its", "our", "their", "mine", "yours", "hers", "ours", "theirs",
            "this", "that", "these", "those", "am",
        }
        goal_lower = goal.lower()
        words = goal_lower.split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        if task_type in self._task_keywords:
            keywords.extend(kw for kw in self._task_keywords[task_type] if kw in goal_lower)
        return list(dict.fromkeys(keywords))

    def _search_semantic_memory_items(self, query: str, keywords: list[str]) -> list[ContextItem]:
        if not hasattr(self.memory_db, "search_by_relevance"):
            return []
        results = self.memory_db.search_by_relevance(query, limit=8)
        for kw in keywords[:3]:
            results.extend(self.memory_db.search_by_relevance(kw, limit=3))
        seen: set[str] = set()
        items: list[ContextItem] = []
        for result in results:
            content = f"{result.get('subject')} {result.get('predicate')} {result.get('value')}"
            identity = result.get("subject", "") + result.get("predicate", "") + result.get("value", "")
            if identity in seen:
                continue
            seen.add(identity)
            items.append(ContextItem(
                content=content,
                source="memory.semantic",
                relevance=float(result.get("confidence", 0.5)),
                confidence=float(result.get("confidence", 0.5)),
                metadata={"kind": "memories", "raw": result},
            ))
        return items

    def _search_project_knowledge_items(self, query: str, keywords: list[str]) -> list[ContextItem]:
        if not hasattr(self.memory_db, "search_by_relevance"):
            return []
        seen: set[str] = set()
        items: list[ContextItem] = []
        for term in ["project"] + keywords[:2]:
            for result in self.memory_db.search_by_relevance(f"project {term}", limit=5):
                if not str(result.get("subject", "")).startswith("project:"):
                    continue
                identity = f"{result['subject']}{result.get('value')}"
                if identity in seen:
                    continue
                seen.add(identity)
                items.append(ContextItem(
                    content=f"{result['subject']}: {result.get('value')}",
                    source="memory.project",
                    relevance=float(result.get("confidence", 0.5)) * 1.1,
                    confidence=float(result.get("confidence", 0.5)),
                    metadata={"kind": "projects"},
                ))
        return items

    def _preference_items(self, keywords: list[str]) -> list[ContextItem]:
        if not hasattr(self.preference_store, "list_preferences"):
            return []
        items: list[ContextItem] = []
        for pref in self.preference_store.list_preferences():
            matched = any(kw in pref.key.lower() for kw in keywords)
            if not (matched or pref.confidence > 0.8):
                continue
            items.append(ContextItem(
                content=f"{pref.key}: {pref.value}",
                source="memory.preference",
                relevance=1.0 if matched else 0.6,
                confidence=pref.confidence,
                metadata={"kind": "preferences", "raw": {"key": pref.key, "value": pref.value, "confidence": pref.confidence}},
            ))
        return items

    def _skill_items(self, goal: str, task_type: TaskType) -> list[ContextItem]:
        if self.skill_registry is None:
            return []
        search = getattr(self.skill_registry, "search_skills", None)
        if not callable(search):
            return []
        items: list[ContextItem] = []
        for skill in search(goal):
            items.append(ContextItem(
                content=skill,
                source="skills",
                relevance=1.0 if skill.get("trigger_match") else 0.5,
                confidence=0.8,
                metadata={"kind": "skills"},
            ))
        return items

    def _known_failure_items(self, goal: str) -> list[ContextItem]:
        if self.episodic_memory is None or not hasattr(self.episodic_memory, "recall_similar"):
            return []
        items: list[ContextItem] = []
        try:
            episodes = self.episodic_memory.recall_similar(goal, limit=5)
        except Exception:
            return []
        for episode in episodes:
            if episode.outcome in {"SUCCESS", "COMPLETED"}:
                continue
            items.append(ContextItem(
                content=f"Known failure for similar goal: {episode.outcome} — {episode.goal}",
                source="memory.episodic",
                relevance=0.7,
                confidence=0.6,
                metadata={"kind": "failures"},
            ))
        return items

    def _determine_capabilities(self, goal: str, skills: list[dict], task_type: TaskType) -> list[str]:
        caps: set[str] = set()
        for skill in skills:
            caps.update(skill.get("required_capabilities", []) if isinstance(skill, dict) else [])
        type_caps = {
            TaskType.COMPUTER_USE: ["computer", "accessibility"],
            TaskType.WEB_SEARCH: ["browser", "online"],
            TaskType.FILE_OPERATION: ["filesystem"],
            TaskType.SYSTEM_CONTROL: ["system"],
            TaskType.COMMUNICATION: ["gmail", "calendar"],
            TaskType.CODING: ["terminal", "filesystem"],
        }
        caps.update(type_caps.get(task_type, []))
        return sorted(caps)

    def _compute_overall_confidence(self, context: PrimedContext) -> float:
        confidences = [0.5]
        weights = [1.0]
        for memory in context.relevant_memories:
            confidences.append(float(memory.get("confidence", 0.5)))
            weights.append(1.0)
        for pref in context.relevant_preferences:
            confidences.append(float(pref.get("confidence", 0.5)))
            weights.append(0.8)
        if context.relevant_skills:
            confidences.append(0.8)
            weights.append(0.6)
        return sum(c * w for c, w in zip(confidences, weights)) / sum(weights)

    def _build_summary(self, context: PrimedContext, goal: str) -> str:
        return (
            f"Goal: {goal} | Task: {context.task_type.value} | "
            f"Memories: {len(context.relevant_memories)} | Projects: {len(context.relevant_projects)} | "
            f"Prefs: {len(context.relevant_preferences)} | Skills: {len(context.relevant_skills)} | "
            f"Failures: {len(context.known_failures)} | Capabilities: {', '.join(context.required_capabilities) or 'none'} | "
            f"Confidence: {context.confidence:.1%} | Tokens: ~{context.bounded_context_tokens}"
        )
