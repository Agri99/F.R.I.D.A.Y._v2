import json
from pathlib import Path

HISTORY_PATH = Path("conversation_history.json")


def _to_serializable(messages: list) -> list[dict]:
    result = []
    for m in messages:
        if isinstance(m, dict):
            result.append(m)
        elif hasattr(m, "model_dump"):
            result.append(m.model_dump())
        else:
            result.append({"role": getattr(m, "role", "assistant"), "content": str(getattr(m, "content", m))})
    return result


def load_messages(system_prompt: str) -> list[dict]:
    if HISTORY_PATH.exists():
        try:
            with HISTORY_PATH.open("r", encoding="utf-8") as f:
                messages = json.load(f)
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = system_prompt  # always use the current prompt, never a stale saved one
            else:
                messages.insert(0, {"role": "system", "content": system_prompt})
            return _scrub_stale_orb_failures(messages)
        except (json.JSONDecodeError, OSError):
            pass
    return [{"role": "system", "content": system_prompt}]


def _scrub_stale_orb_failures(messages: list) -> list:
    """Drop past turns where FRIDAY claimed she could not hide — they teach the model the wrong behavior."""
    cleaned = []
    skip_next_user_confirm = False
    for message in messages:
        if not isinstance(message, dict):
            cleaned.append(message)
            continue
        content = str(message.get("content") or "").lower()
        if message.get("role") == "assistant" and ("cannot hide" in content or "can't hide" in content):
            skip_next_user_confirm = True
            continue
        if skip_next_user_confirm and message.get("role") == "user":
            skip_next_user_confirm = False
            continue
        skip_next_user_confirm = False
        cleaned.append(message)
    return cleaned


def save_messages(messages: list) -> None:
    try:
        with HISTORY_PATH.open("w", encoding="utf-8") as f:
            json.dump(_to_serializable(messages), f, indent=2)
    except (OSError, TypeError) as exc:
        print(f"[warning] Could not save conversation history: {exc}")