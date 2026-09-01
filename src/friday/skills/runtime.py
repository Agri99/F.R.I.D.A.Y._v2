"""Skill execution engine with full authorization and verification."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from friday.security.action_request import ActionRequest
from friday.security.authorization import authorize


@dataclass
class SkillResult:
    success: bool
    data: Any
    error: str | None = None
    step_results: list[dict[str, Any]] = field(default_factory=list)


class SkillRuntime:
    """Executes skills by turning procedure steps into authorized ActionRequests."""

    def __init__(self, tool_registry: Any, policy_engine: Any, capability_registry: Any, skill_registry: Any | None = None) -> None:
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.capability_registry = capability_registry
        self.skill_registry = skill_registry

    def run(self, skill_name: str, inputs: dict[str, Any] | None = None) -> SkillResult:
        inputs = inputs or {}
        skill = self._load_skill(skill_name)
        if not skill:
            return SkillResult(success=False, data=None, error=f"Skill '{skill_name}' not found")

        if not self._check_prerequisites(skill, inputs):
            return SkillResult(success=False, data=None, error="Prerequisites not met")

        steps = self._extract_steps(skill)
        if not steps:
            return SkillResult(success=False, data=None, error="Skill has no executable steps")

        results: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            action = step.get("action", "")
            tool = self.tool_registry.get(action) if hasattr(self.tool_registry, "get") else None
            if tool is None:
                return SkillResult(success=False, data=results, error=f"Tool '{action}' not found", step_results=results)

            raw_args = step.get("args", step.get("arguments", {}))
            if isinstance(raw_args, str):
                import json
                try:
                    raw_args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    raw_args = {}
            merged_args = self._interpolate(raw_args, inputs)

            tier = getattr(tool, "tier", getattr(tool, "risk_tier", "GREEN"))
            cap_scope = getattr(tool, "capability_scope", None)
            required_scopes = [cap_scope] if cap_scope else []
            policy_result = self.policy_engine.evaluate(action, tier=tier, required_scopes=required_scopes)
            decision = authorize(
                tool_name=action,
                tool_args=merged_args,
                policy_result=policy_result,
                capability_registry=self.capability_registry,
            )
            if not decision.is_authorized:
                return SkillResult(
                    success=False,
                    data=results,
                    error=f"Step {index + 1} blocked by policy: {decision.reason}",
                    step_results=results,
                )

            req = ActionRequest.from_tool(
                tool=tool,
                arguments=merged_args,
                task_id=f"skill:{skill_name}",
                step_id=str(index),
                requester=f"skill:{skill_name}",
                context_source="skill_runtime",
            )

            try:
                if hasattr(tool, "run"):
                    res = tool.run(**req.arguments)
                elif hasattr(tool, "handler") and callable(tool.handler):
                    res = tool.handler(**req.arguments)
                elif callable(tool):
                    res = tool(**req.arguments)
                else:
                    raise ValueError(f"Tool '{action}' is not callable")

                obs = str(res)
                expected = step.get("expected", step.get("expected_observation", ""))
                if expected and expected.lower() not in obs.lower():
                    indicators = ("success", "opened", "created", "saved", "done", "written", "ok", "true", "200")
                    if not any(item in obs.lower() for item in indicators):
                        return SkillResult(
                            success=False,
                            data=results,
                            error=f"Step {index + 1} observation did not match expected '{expected}'",
                            step_results=results,
                        )

                results.append({"step": action, "result": res, "observation": obs})
            except Exception as exc:
                return SkillResult(
                    success=False,
                    data=results,
                    error=f"Step {index + 1} execution failed: {exc}",
                    step_results=results,
                )

        return SkillResult(success=True, data=results, error=None, step_results=results)

    def _load_skill(self, name: str) -> Any | None:
        if self.skill_registry and hasattr(self.skill_registry, "get"):
            return self.skill_registry.get(name)
        return None

    def _check_prerequisites(self, skill: Any, inputs: dict[str, Any]) -> bool:
        required_vars = getattr(skill, "variables", {}) or {}
        for var_name, meta in required_vars.items():
            if isinstance(meta, dict) and meta.get("required", True):
                if var_name not in inputs and meta.get("default") is None:
                    return False
        return True

    def _extract_steps(self, skill: Any) -> list[dict[str, Any]]:
        if hasattr(skill, "procedure_steps") and skill.procedure_steps:
            return list(skill.procedure_steps)
        proc = getattr(skill, "procedure", None)
        if isinstance(proc, list):
            return list(proc)
        if isinstance(proc, dict):
            return [proc]
        return []

    def _interpolate(self, template: Any, inputs: dict[str, Any]) -> Any:
        if isinstance(template, str):
            for k, v in inputs.items():
                template = template.replace(f"{{{k}}}", str(v))
            return template
        if isinstance(template, dict):
            return {k: self._interpolate(v, inputs) for k, v in template.items()}
        if isinstance(template, list):
            return [self._interpolate(item, inputs) for item in template]
        return template


__all__ = ["SkillResult", "SkillRuntime"]
