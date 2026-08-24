import json
import time
from pathlib import Path

AUDIT_LOG_PATH = Path("audit_log.jsonl")


def log_action(tool_name: str, risk: str, arguments: dict, result, confirmed: bool = False) -> None:
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tool": tool_name,
        "risk": risk,
        "arguments": arguments,
        "result": str(result),
        "confirmed": confirmed,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")