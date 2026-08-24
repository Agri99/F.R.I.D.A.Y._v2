"""
main.py

WHAT THIS IS FOR:
The wiring script. Loads config, builds every subsystem, hands them
to the orchestrator, runs one goal. This is intentionally thin — all
real logic lives in core/. This file should never grow past "assemble
and call".
"""

from config.settings import Settings
from core.models.router import ModelRouter
from core.security.policy import PolicyEngine
from core.tasks.state_machine import TaskManager
from core.tools.registry import ToolRegistry
from core.tools.base_tools import register_base_tools
from core.orchestrator import AgentOrchestrator


def build_orchestrator(config_path: str = "config/default.yaml") -> AgentOrchestrator:
    settings = Settings.load(config_path)
    settings.ensure_dirs()

    model_router = ModelRouter(settings)
    policy_engine = PolicyEngine(settings)

    tool_registry = ToolRegistry()
    register_base_tools(tool_registry)

    task_manager = TaskManager()

    return AgentOrchestrator(
        settings=settings,
        model_router=model_router,
        policy_engine=policy_engine,
        tool_registry=tool_registry,
        task_manager=task_manager,
    )


if __name__ == "__main__":
    orch = build_orchestrator()
    reasoning = orch.models.get("reasoning")
    print(f"Reasoning model available: {reasoning.is_available()}")

    if not reasoning.is_available():
        print("Ollama not reachable at localhost:11434 — start Ollama and pull the model to run a real task.")
    else:
        task = orch.run("What time is it right now?")
        print(f"Task {task.id} ended in state {task.state.value}")
        for state, reason in task.history:
            print(f"  {state.value}: {reason}")
