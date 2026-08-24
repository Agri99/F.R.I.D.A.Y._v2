import hashlib
import json
import time
import uuid


class PendingConfirmation:
    def __init__(self, tool_name: str, arguments: dict, ttl_seconds: int = 60):
        self.id = str(uuid.uuid4())
        self.tool_name = tool_name
        self.arguments = arguments
        self.parameters_hash = self._hash(tool_name, arguments)
        self.created_at = time.time()
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _hash(tool_name: str, arguments: dict) -> str:
        payload = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds