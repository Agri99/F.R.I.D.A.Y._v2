from tools.registry import register_tool, TOOL_REGISTRY
from security.policy import RiskClass, requires_confirmation
from memory.skills import save_skill, get_skill, list_skills


@register_tool(risk=RiskClass.YELLOW)
def remember_as_skill(name: str) -> dict:
    """Save the tool calls made in the previous action as a reusable named skill.

    Args:
        name: A short name for this skill, e.g. 'morning briefing'.

    Returns:
        dict: status of the save
    """
    from llm import LAST_TOOL_CALLS
    if not LAST_TOOL_CALLS:
        return {"status": "error", "message": "Nothing recent to save as a skill."}
    save_skill(name, LAST_TOOL_CALLS)
    return {"status": "ok", "message": f"Saved skill '{name}'."}


@register_tool(risk=RiskClass.GREEN)
def list_saved_skills() -> dict:
    """List all saved skill names."""
    return {"status": "ok", "skills": list_skills()}


@register_tool(risk=RiskClass.YELLOW)
def run_skill(name: str) -> dict:
    """Run a previously saved skill by name.

    Args:
        name: The skill's name.

    Returns:
        dict: results of each step, or an error
    """
    steps = get_skill(name)
    if not steps:
        return {"status": "error", "message": f"No skill named '{name}'."}

    results = []
    for step in steps:
        tool_def = TOOL_REGISTRY.get(step["tool"])
        if tool_def is None:
            results.append({"tool": step["tool"], "status": "error", "message": "Tool no longer exists."})
            continue
        if requires_confirmation(tool_def.risk):
            results.append({"tool": step["tool"], "status": "skipped", "message": "Requires confirmation, run individually."})
            continue
        try:
            result = tool_def.func(**step["arguments"])
            results.append({"tool": step["tool"], "status": "ok", "result": result})
        except Exception as exc:  # noqa: BLE001
            results.append({"tool": step["tool"], "status": "error", "message": str(exc)})

    return {"status": "ok", "steps_run": results}