"""Compatibility facade for the context priming engine."""

__all__ = ["ContextPrimingEngine", "PrimedContext", "TaskType"]


def __getattr__(name: str):
    if name in {"ContextPrimingEngine", "PrimedContext", "TaskType"}:
        from friday.memory.priming import ContextPrimingEngine, PrimedContext, TaskType

        return {"ContextPrimingEngine": ContextPrimingEngine, "PrimedContext": PrimedContext, "TaskType": TaskType}[name]
    raise AttributeError(name)
