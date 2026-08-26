"""
PendingAction state machine for managing user confirmations.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from friday.security.policy import RiskTier


@dataclass
class PendingAction:
    tool: str
    arguments: dict[str, Any]
    risk: RiskTier
    target: str | None = None
    authorization_requirements: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    
    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + 60.0
            
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def get_hash(self) -> str:
        payload = json.dumps({"tool": self.tool, "args": self.arguments}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class ConfirmationManager:
    def __init__(self, default_ttl_seconds: int | None = None, ttl_seconds: int | None = None):
        self.default_ttl = ttl_seconds if ttl_seconds is not None else (default_ttl_seconds if default_ttl_seconds is not None else 60)
        self._pending_actions: dict[str, PendingAction] = {}

        
    def create_pending_action(self, tool: str, arguments: dict[str, Any], risk: RiskTier, target: str | None = None, requirements: list[str] = None) -> PendingAction:
        action = PendingAction(
            tool=tool,
            arguments=arguments,
            risk=risk,
            target=target,
            authorization_requirements=requirements or [],
            expires_at=time.time() + self.default_ttl
        )
        self._pending_actions[action.id] = action
        return action
        
    def get_action(self, action_id: str) -> PendingAction | None:
        action = self._pending_actions.get(action_id)
        if action and action.is_expired():
            self.remove_action(action_id)
            return None
        return action
        
    def remove_action(self, action_id: str) -> None:
        self._pending_actions.pop(action_id, None)
        
    def confirm_action(self, action_id: str) -> bool:
        action = self.get_action(action_id)
        if not action:
            return False
        # Remove after successful confirmation
        self.remove_action(action_id)
        return True
