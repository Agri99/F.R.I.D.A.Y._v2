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
        observations: list[dict] | None = None,
        system_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
        primed_context: Any = None,
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

        # Build enhanced system prompt with primed context
        if system_prompt:
            sys_prompt = (
                f"{system_prompt}\n\n"
                "You are FRIDAY's planning engine. Given a user goal and available tools, "
                "call the appropriate tool(s) to fulfill the request. If no tool is needed, "
                "provide a direct answer in character adhering strictly to your persona rules.\n"
                "For each tool, you must populate the arguments along with intent, expected_observation, "
                "verification_strategy, risk_scope, reversible, retry_policy, etc."
            )
        else:
            sys_prompt = (
                "You are FRIDAY's planning engine. Given a user goal and available tools, "
                "call the appropriate tool(s) to fulfill the request. If no tool is needed, "
                "provide a direct answer.\n"
                "For each tool, you must populate the arguments along with intent, expected_observation, "
                "verification_strategy, risk_scope, reversible, retry_policy, etc."
            )

        # Add primed context to system prompt if available
        if primed_context:
            context_parts = []
            if primed_context.relevant_memories:
                context_parts.append("Relevant knowledge:\n" + "\n".join(
                    f"- {m.get('subject', '')}: {m.get('predicate', '')} {m.get('value', '')} (conf: {m.get('confidence', 0):.0%})"
                    for m in primed_context.relevant_memories[:5]
                ))
            if primed_context.relevant_preferences:
                context_parts.append("User preferences:\n" + "\n".join(
                    f"- {p.get('key', '')}: {p.get('value', '')} (conf: {p.get('confidence', 0):.0%})"
                    for p in primed_context.relevant_preferences[:3]
                ))
            if primed_context.relevant_skills:
                context_parts.append("Relevant skills:\n" + "\n".join(
                    f"- {s.get('name', '')}: {s.get('purpose', '')} (triggers: {s.get('triggers', [])})"
                    for s in primed_context.relevant_skills[:3]
                ))
            if primed_context.required_capabilities:
                context_parts.append(f"Required capabilities: {', '.join(primed_context.required_capabilities)}")
            if primed_context.known_failures:
                context_parts.append("Known failure patterns:\n" + "\n".join(
                    f"- {f.get('step', '')}: {f.get('error', '')}" for f in primed_context.known_failures[:3]
                ))

            if context_parts:
                sys_prompt += "\n\n--- PRIMED CONTEXT ---\n" + "\n\n".join(context_parts) + "\n--- END CONTEXT ---"

        messages = [ModelMessage(role="system", content=sys_prompt)]

        if memories:
            mem_lines = []
            for m in memories:
                mem_lines.append(f"- {m.get('content', m)}" if isinstance(m, dict) else f"- {m}")
            messages.append(ModelMessage(role="system", content="Relevant remembered facts:\n" + "\n".join(mem_lines)))

        if conversation_history:
            # conversation_history[0] is its own system entry (possibly stale/simpler
            # than sys_prompt above) - skip it, the elaborated sys_prompt supersedes it.
            # Every actual turn (user/assistant/tool) is preserved in full, in order,
            # ending with the current goal (already persisted before plan() is called).
            for m in conversation_history[1:]:
                messages.append(ModelMessage(role=m.get("role", "user"), content=m.get("content", "")))
        else:
            # No history available (e.g. a caller that doesn't pass one) - fall back
            # to just the current goal, same as the old behavior.
            messages.append(ModelMessage(role="user", content=goal))

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
        
    def replan(
        self,
        task: Task,
        observations: list[dict],
        available_tools: list[dict] | None = None,
        model_router: Any = None,
        system_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> list[Step]:
        """Replan using accumulated observations and failure history.

        FIXED BUG: this used to call self.plan(..., model_router=None,
        available_tools=[]) unconditionally - and plan()'s first line is
        `if not model_router: return []`. That meant EVERY replan attempt
        silently produced an empty plan, which made the orchestrator's
        execution loop exit immediately and report the task COMPLETED
        ("All steps completed") even though the step that triggered
        replanning had just FAILED. A failure silently became a false
        success. Now takes the same model_router/available_tools/
        system_prompt/conversation_history the caller already has, so
        replanning can actually call the model."""
        task.plan_version += 1

        # Build context from observations and failure history
        obs_context = []
        for obs in observations:
            if isinstance(obs, dict):
                step_name = obs.get("step", "unknown")
                observation = obs.get("observation", "")
                error = obs.get("error", "")
                if error:
                    obs_context.append(f"Step '{step_name}' failed: {error}. Observation: {observation}")
                else:
                    obs_context.append(f"Step '{step_name}' observation: {observation}")
            else:
                obs_context.append(str(obs))

        failure_context = []
        for failure in getattr(task, "failures", []):
            failure_context.append(f"Failed step '{failure.get('step')}': {failure.get('error')} (expected: {failure.get('verification_reason')})")

        verification_context = []
        for vr in getattr(task, "verification_results", []):
            if not vr.get("passed", True):
                verification_context.append(f"Verification failed for '{vr.get('step')}': {vr.get('reason')}")

        full_context = []
        if obs_context:
            full_context.append("Recent observations:\n" + "\n".join(obs_context))
        if failure_context:
            full_context.append("Failure history:\n" + "\n".join(failure_context))
        if verification_context:
            full_context.append("Verification failures:\n" + "\n".join(verification_context))

        context_str = "\n\n".join(full_context) if full_context else ""

        return self.plan(
            goal=task.goal,
            available_tools=available_tools or [],
            memories=[],
            model_router=model_router,
            system_prompt=system_prompt,
            conversation_history=conversation_history,
            observations=[{"context": context_str}] if context_str else [],
        )
