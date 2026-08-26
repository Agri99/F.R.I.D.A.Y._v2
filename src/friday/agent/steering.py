from __future__ import annotations

from enum import Enum
from dataclasses import dataclass

class AgentMode(Enum):
    NORMAL = 'normal'
    FAST = 'fast'
    DEEP_REASONING = 'deep'
    OFFLINE = 'offline'
    PAUSED = 'paused'

@dataclass
class SteeringCommand:
    mode: AgentMode

class SteeringController:
    """Manages voice control commands for agent mode management."""
    
    def parse_command(self, text: str) -> SteeringCommand | None:
        text = text.lower().strip()
        
        if any(phrase in text for phrase in ['use fast mode', 'be quick']):
            return SteeringCommand(mode=AgentMode.FAST)
            
        if any(phrase in text for phrase in ['use deep reasoning', 'think carefully']):
            return SteeringCommand(mode=AgentMode.DEEP_REASONING)
            
        if any(phrase in text for phrase in ['go offline', 'disconnect']):
            return SteeringCommand(mode=AgentMode.OFFLINE)
            
        if any(phrase in text for phrase in ['stop', 'pause', 'hold on']):
            return SteeringCommand(mode=AgentMode.PAUSED)
            
        if any(phrase in text for phrase in ['resume', 'continue', 'go ahead']):
            return SteeringCommand(mode=AgentMode.NORMAL)
            
        return None

    def apply(self, command: SteeringCommand) -> str:
        """Applies the mode and returns a spoken confirmation."""
        if command.mode == AgentMode.FAST:
            return "Switching to fast mode."
        elif command.mode == AgentMode.DEEP_REASONING:
            return "Engaging deep reasoning mode."
        elif command.mode == AgentMode.OFFLINE:
            return "Going offline."
        elif command.mode == AgentMode.PAUSED:
            return "Paused. Let me know when to resume."
        elif command.mode == AgentMode.NORMAL:
            return "Resuming normal operation."
        return "Mode updated."
