"""Relevance-ranked context selection."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from friday.context.budget import ContextBudget


@dataclass
class ContextItem:
    content: str
    source: str
    relevance: float = 0.0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def score(self) -> float:
        return max(0.0, self.relevance) * max(0.0, self.confidence)


class ContextSelector:
    def __init__(self, budget: ContextBudget | None = None) -> None:
        self.budget = budget or ContextBudget()

    def select(self, items: Iterable[ContextItem]) -> list[ContextItem]:
        """Rank items and return the highest-value set that fits the context budget."""
        ranked = sorted(items, key=lambda item: item.score, reverse=True)
        selected: list[ContextItem] = []
        used = 0
        seen: set[str] = set()
        for item in ranked:
            content_str = str(item.content)
            identity = hash(content_str)
            if identity in seen:
                continue
            cost = self.budget.estimate_tokens(content_str)
            if used + cost > self.budget.available_tokens:
                continue
            selected.append(item)
            seen.add(identity)
            used += cost
        return selected
