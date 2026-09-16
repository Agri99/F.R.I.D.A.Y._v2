"""
src/friday/tools/conversation.py

WHAT THIS IS FOR:
Live conversation skill set per runbook section 25.
Provides tools for the Live Conversation model to control its own pipeline.
"""

from typing import Any
from .registry import ToolRegistry, Tool
from .metadata import build_schema

# Global state to signal orchestrator/app
SWITCH_TO_VOICE = False
END_VOICE = False

def _live_conversation() -> dict[str, Any]:
    """Turn on live conversational mode."""
    global SWITCH_TO_VOICE
    SWITCH_TO_VOICE = True
    return {"status": "ok", "message": "Switching to live conversational mode."}

def _end_conversation() -> dict[str, Any]:
    """Gracefully exit voice mode."""
    global END_VOICE
    END_VOICE = True
    return {"status": "ok", "message": "Exiting voice mode."}

def _barge_in(reason: str = "") -> dict[str, Any]:
    """Handle interruptions gracefully by stopping current speech and listening."""
    # The actual audio interruption is handled in the pipeline, but this tool
    # allows the agent to acknowledge an interruption contextually.
    return {"status": "ok", "message": f"Acknowledged barge-in: {reason}"}

def register_all_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            name="conversation.live_conversation",
            description="Turn on live conversational mode (voice interaction).",
            tier="SAFE",
            capability_scope="interaction",
            input_schema=build_schema({}),
            handler=_live_conversation,
        )
    )
    registry.register(
        Tool(
            name="conversation.end",
            description="Gracefully exit voice mode.",
            tier="SAFE",
            capability_scope="interaction",
            input_schema=build_schema({}),
            handler=_end_conversation,
        )
    )
    registry.register(
        Tool(
            name="voice.barge_in",
            description="Handle user interruptions gracefully.",
            tier="SAFE",
            capability_scope="interaction",
            input_schema=build_schema(
                {"reason": {"type": "string", "description": "The reason or context for the interruption."}},
                ["reason"]
            ),
            handler=_barge_in,
        )
    )

