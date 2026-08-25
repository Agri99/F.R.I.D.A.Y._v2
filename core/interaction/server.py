"""
core/interaction/server.py

WHAT THIS IS FOR:
The localhost boundary Section 23/24 asks for. One asyncio WebSocket
server, run inside FRIDAY Core (Process A), with two logical channels:

  /voice  - Process B connects here, sends VoiceInput (text only,
            never raw audio), Core runs it through the orchestrator
            and sends back the final task result.
  /orb    - Process C connects here. Core PUSHES OrbState broadcasts
            to it on every task state change. The orb may only send
            back OrbCommand messages from the closed whitelist -
            anything else is rejected before it gets anywhere near
            tool dispatch, because this server never routes orb
            messages into the orchestrator at all.

WHY IT'S BUILT THIS WAY:
This file is the enforcement point for "the orb has no authority to
execute tools" (Section 24). It's not a policy choice made deep in the
orchestrator - the orb's messages structurally cannot reach the
orchestrator. That's a stronger guarantee than a runtime check.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol

from core.interaction.contracts import (
    OrbCommand,
    OrbCommandMessage,
    OrbState,
    TASK_STATE_TO_ORB_STATE,
    VoiceInput,
)
from core.orchestrator import AgentOrchestrator

logger = logging.getLogger("friday.interaction_server")


class InteractionServer:
    def __init__(self, orchestrator: AgentOrchestrator, host: str = "localhost", port: int = 8765):
        self.orchestrator = orchestrator
        self.host = host
        self.port = port
        self._orb_clients: set[WebSocketServerProtocol] = set()

    # ---- public: called by orchestrator/task machinery on every transition ----
    async def broadcast_orb_state(self, orb_state: OrbState) -> None:
        if not self._orb_clients:
            return
        message = json.dumps({"type": "state", "state": orb_state.value})
        # gather so one dead client doesn't block the rest
        await asyncio.gather(
            *(client.send(message) for client in list(self._orb_clients)),
            return_exceptions=True,
        )

    # ---- connection routing ----
    async def _handler(self, websocket: WebSocketServerProtocol, path: str) -> None:
        if path == "/voice":
            await self._handle_voice(websocket)
        elif path == "/orb":
            await self._handle_orb(websocket)
        else:
            await websocket.close(code=4404, reason="unknown channel")

    async def _handle_voice(self, websocket: WebSocketServerProtocol) -> None:
        async for raw in websocket:
            try:
                data = json.loads(raw)
                voice_input = VoiceInput(
                    recognized_text=data["recognized_text"],
                    session_id=data["session_id"],
                    audio_path_for_authorization=data.get("audio_path_for_authorization"),
                    wake_word_meta=data.get("wake_word_meta", {}),
                )
            except (KeyError, json.JSONDecodeError) as exc:
                await websocket.send(json.dumps({"type": "error", "reason": f"malformed voice input: {exc}"}))
                continue

            task = self.orchestrator.run(
                voice_input.recognized_text,
                on_transition=self._make_state_broadcaster(),
            )
            await websocket.send(json.dumps({
                "type": "task_result",
                "task_id": task.id,
                "state": task.state.value,
                "history": [(s.value, r) for s, r in task.history],
            }))

    async def _handle_orb(self, websocket: WebSocketServerProtocol) -> None:
        self._orb_clients.add(websocket)
        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                    command = OrbCommand(data["command"])  # ValueError if not in whitelist
                    msg = OrbCommandMessage(command=command, payload=data.get("payload", {}))
                except (KeyError, ValueError, json.JSONDecodeError) as exc:
                    # Rejected here. This message never reaches the orchestrator -
                    # there is no code path from this branch to tool dispatch.
                    await websocket.send(json.dumps({"type": "error", "reason": f"rejected orb command: {exc}"}))
                    continue

                logger.info("orb command accepted (UI-only, no tool authority): %s", msg.command.value)
                # UI-only commands are acked, not executed as agent actions.
                await websocket.send(json.dumps({"type": "ack", "command": msg.command.value}))
        finally:
            self._orb_clients.discard(websocket)

    def _make_state_broadcaster(self):
        """Returns a sync callback the state machine can call; schedules the async broadcast."""
        loop = asyncio.get_event_loop()

        def _on_transition(task_state) -> None:
            orb_state = TASK_STATE_TO_ORB_STATE.get(task_state, OrbState.ERROR)
            asyncio.run_coroutine_threadsafe(self.broadcast_orb_state(orb_state), loop)

        return _on_transition

    async def serve_forever(self) -> None:
        async with websockets.serve(self._handler, self.host, self.port):
            logger.info("InteractionServer listening on ws://%s:%s (/voice, /orb)", self.host, self.port)
            await asyncio.Future()  # run until cancelled
