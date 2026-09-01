"""Adapters for context retrieval sources."""
from __future__ import annotations

from typing import Any, Protocol

from friday.context.selector import ContextItem


class ContextSource(Protocol):
    def retrieve(self, query: str, limit: int = 5) -> list[ContextItem]: ...


class MemorySource:
    def __init__(self, memory: Any) -> None:
        self.memory = memory

    def retrieve(self, query: str, limit: int = 5) -> list[ContextItem]:
        search = getattr(self.memory, "search_by_relevance", None)
        if not callable(search):
            return []
        results = search(query, limit=limit) or []
        return [
            ContextItem(
                content=_render_record(result),
                source="memory",
                relevance=float(result.get("relevance", result.get("score", 0.5))),
                confidence=float(result.get("confidence", 1.0)),
                metadata=result,
            )
            for result in results
            if isinstance(result, dict)
        ]


class PreferenceSource:
    def __init__(self, store: Any) -> None:
        self.store = store

    def retrieve(self, query: str, limit: int = 5) -> list[ContextItem]:
        list_preferences = getattr(self.store, "list_preferences", None)
        if not callable(list_preferences):
            return []
        terms = {term.lower() for term in query.split() if len(term) > 2}
        items: list[ContextItem] = []
        for preference in list_preferences() or []:
            key = str(getattr(preference, "key", ""))
            value = str(getattr(preference, "value", ""))
            relevance = 1.0 if any(term in key.lower() for term in terms) else 0.3
            items.append(ContextItem(
                content=f"{key}: {value}",
                source="preference",
                relevance=relevance,
                confidence=float(getattr(preference, "confidence", 1.0)),
            ))
        return sorted(items, key=lambda item: item.score, reverse=True)[:limit]


class SkillSource:
    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def retrieve(self, query: str, limit: int = 5) -> list[ContextItem]:
        finder = getattr(self.registry, "list_by_trigger", None)
        if not callable(finder):
            return []
        skills = finder(query) or []
        return [
            ContextItem(
                content=f"{skill.name}: {getattr(skill, 'purpose', '')}",
                source="skill",
                relevance=1.0,
                confidence=1.0,
                metadata={"name": skill.name, "version": getattr(skill, "version", "")},
            )
            for skill in skills[:limit]
        ]


def _render_record(record: dict[str, Any]) -> str:
    if "content" in record:
        return str(record["content"])
    parts = [record.get("subject"), record.get("predicate"), record.get("value")]
    return " ".join(str(part) for part in parts if part is not None)
