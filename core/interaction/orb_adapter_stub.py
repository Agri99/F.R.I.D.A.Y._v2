"""
core/interaction/orb_adapter_stub.py

WHAT THIS IS FOR:
Where your EXISTING v1 PySide6 + Three.js orb plugs in as Process C.
Your orb rendering code (transparent window, sphere reacting to
state, drag-to-reposition) does not change. What changes is where it
gets its state from: instead of an in-process callback, it listens on
the /orb WebSocket channel for `{"type": "state", "state": "..."}`
messages, and it SENDS only whitelisted UI commands back (show, hide,
move, set_state, exit_ui) - never a tool call, because the server on
the Core side structurally cannot route orb messages to the
orchestrator (see server.py).

Replace `apply_state_to_sphere` and the tray/drag handlers below with
your real v1 PySide6/Three.js glue.
"""

from __future__ import annotations

import asyncio
import json

import websockets

CORE_ORB_URL = "ws://localhost:8765/orb"


# --- REPLACE WITH YOUR REAL v1 ORB RENDERING CALLS --------------------------

def apply_state_to_sphere(state: str) -> None:
    """Update the Three.js sphere's color/motion for the given OrbState value."""
    raise NotImplementedError("plug in your v1 orb state->visual mapping here")

# -----------------------------------------------------------------------------


async def orb_listener() -> None:
    async with websockets.connect(CORE_ORB_URL) as ws:
        # Example of sending a UI-only command - system tray "show" click,
        # drag-end "move", etc. would call ws.send with one of these shapes:
        #
        # await ws.send(json.dumps({"command": "show"}))
        # await ws.send(json.dumps({"command": "move", "payload": {"x": 120, "y": 340}}))
        #
        # Anything outside {show, hide, move, set_state, exit_ui} is
        # rejected by Core before it goes anywhere near tool dispatch.

        async for raw in ws:
            data = json.loads(raw)
            if data.get("type") == "state":
                apply_state_to_sphere(data["state"])
            elif data.get("type") == "error":
                # e.g. you sent a malformed/illegal command - log and ignore,
                # never silently retry with something more permissive
                print(f"[orb] rejected command: {data.get('reason')}")


if __name__ == "__main__":
    asyncio.run(orb_listener())
