"""Bounded context assembly for planner priming."""

from friday.context.budget import ContextBudget
from friday.context.selector import ContextItem, ContextSelector
from friday.context.sources import ContextSource, MemorySource, PreferenceSource, SkillSource

__all__ = [
    "ContextBudget",
    "ContextItem",
    "ContextSelector",
    "ContextSource",
    "MemorySource",
    "PreferenceSource",
    "SkillSource",
]


def __getattr__(name):
    if name in {"ContextPrimingEngine", "PrimedContext", "TaskType"}:
        from friday.context import primer

        return getattr(primer, name)
    raise AttributeError(name)
