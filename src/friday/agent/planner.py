from __future__ import annotations

import json
from enum import Enum
from typing import Any

from friday.models.base import ModelMessage
from .task import Step, Task


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

    def plan(
        self,
        goal: str,
        available_tools: list[dict],
        memories: list[dict] | None = None,
        model_router: Any = None,
        observations: list[dict] | None = None
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
            
        sys_prompt = (
            "You are FRIDAY's planning engine. Given a user goal and available tools, "
            "call the appropriate tool(s) to fulfill the request. If no tool is needed, "
            "provide a direct answer.\n"
            "For each tool, you must populate the arguments along with intent, expected_observation, "
            "verification_strategy, risk_scope, reversible, retry_policy, etc."
        )
        
        messages = [
            ModelMessage(role="system", content=sys_prompt),
            ModelMessage(role="user", content=goal),
        ]
        
        if observations:
            obs_str = json.dumps(observations)
            messages.append(ModelMessage(role="user", content=f"Recent observations: {obs_str}"))

        try:
            response = provider.generate(messages=messages, tools=available_tools)
        except Exception as exc:
            return [Step(action="error", arguments={"message": str(exc)}, expected_observation="Error reported")]

        if not response.tool_calls:
            return [Step(action="direct_answer", arguments={"text": response.text}, expected_observation=response.text)]

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
                intent = tool_args.pop("intent", f"Execute {tool_name}")
                expected_observation = tool_args.pop("expected_observation", f"Executed {tool_name}")
                verification_strategy = tool_args.pop("verification_strategy", "auto")
                risk_scope = tool_args.pop("risk_scope", "")
                reversible = tool_args.pop("reversible", True)
                retry_policy = tool_args.pop("retry_policy", "default")
                
                steps.append(Step(
                    action=tool_name, 
                    arguments=tool_args,
                    intent=intent,
                    expected_observation=expected_observation,
                    verification_strategy=verification_strategy,
                    risk_scope=risk_scope,
                    reversible=reversible,
                    retry_policy=retry_policy
                ))

        return steps

    def create_plan(
        self,
        goal: str,
        available_tools: list[dict],
        memories: list[dict] | None = None,
        model_router: Any = None,
    ) -> list[Step]:
        """Legacy method pointing to plan."""
        return self.plan(goal, available_tools, memories, model_router)
        
    def replan(self, task: Task, observations: list[dict]) -> list[Step]:
        task.plan_version += 1
        return self.plan(
            goal=task.goal,
            available_tools=[], # Ideally passed in, but signature doesn't specify. Real logic would inject schemas.
            memories=[],
            model_router=None, # Should be bound, but keeping interface simple per spec.
            observations=observations
        )
