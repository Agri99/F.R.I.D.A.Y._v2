"""
src/friday/agent/planner.py

WHAT THIS IS FOR:
Decomposes user goals into actionable Step sequences using the ModelProvider
with tool schemas, or direct assessment for simple intents (§11.2).
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from friday.models.base import ModelMessage
from .task import Step


class PlanningDepth(str, Enum):
    DIRECT = "DIRECT"
    SINGLE_STEP = "SINGLE_STEP"
    MULTI_STEP = "MULTI_STEP"


class Planner:
    """Determines how to accomplish goals based on complexity and model outputs."""

    def assess_complexity(self, goal: str, context: dict | None = None) -> PlanningDepth:
        """Heuristic complexity assessment."""
        context = context or {}
        if context.get("is_direct_intent"):
            return PlanningDepth.DIRECT

        if " and then " in goal.lower() or " after that " in goal.lower():
            return PlanningDepth.MULTI_STEP

        return PlanningDepth.SINGLE_STEP

    def create_plan(
        self,
        goal: str,
        available_tools: list[dict],
        memories: list[dict] | None = None,
        model_router: Any = None,
    ) -> list[Step]:
        """Creates a step plan by querying the reasoning model with tool schemas."""
        if not model_router:
            return []

        provider = (
            model_router.get("reasoning")
            if hasattr(model_router, "get")
            else model_router
        )
        if not provider or not hasattr(provider, "generate"):
            return []

        messages = [
            ModelMessage(
                role="system",
                content=(
                    "You are FRIDAY's planning engine. Given a user goal and available tools, "
                    "call the appropriate tool(s) to fulfill the request. If no tool is needed, "
                    "provide a direct answer."
                ),
            ),
            ModelMessage(role="user", content=goal),
        ]

        try:
            response = provider.generate(messages=messages, tools=available_tools)
        except Exception as exc:
            return [Step(action="error", args={"message": str(exc)}, expected_outcome="Error reported")]

        if not response.tool_calls:
            # No tool call needed — return a special completion step or empty list
            return [Step(action="direct_answer", args={"text": response.text}, expected_outcome=response.text)]

        steps: list[Step] = []
        for call in response.tool_calls:
            tool_name = call.get("function", {}).get("name") if "function" in call else call.get("name")
            tool_args = call.get("function", {}).get("arguments", call.get("arguments", {}))
            if isinstance(tool_args, str):
                try:
                    tool_args = json.loads(tool_args)
                except Exception:
                    tool_args = {}

            if tool_name:
                steps.append(Step(action=tool_name, args=tool_args, expected_outcome=f"Executed {tool_name}"))

        return steps
