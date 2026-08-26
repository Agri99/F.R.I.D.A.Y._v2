"""Orb WebSocket server."""
from __future__ import annotations
import asyncio
import json
import threading
import websockets

_clients = set()
_loop: asyncio.AbstractEventLoop | None = None
_ready = threading.Event()

# Enhanced states: IDLE, LISTENING, THINKING, PLANNING, EXECUTING, WAITING_CONFIRMATION, VERIFYING, LEARNING, OFFLINE, ERROR

async def _handler(websocket):
    _clients.add(websocket)
    try:
        async for _ in websocket:
            pass
    finally:
        _clients.discard(websocket)

async def _broadcast(message: str) -> None:
    if _clients:
        await asyncio.gather(*(ws.send(message) for ws in list(_clients)), return_exceptions=True)

async def _main():
    async with websockets.serve(_handler, "127.0.0.1", 8765):
        _ready.set()
        await asyncio.Future()

def start_server_in_background() -> None:
    global _loop

    def _run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(_main())

    threading.Thread(target=_run, daemon=True).start()
    _ready.wait(timeout=5)

def set_state(state: str) -> None:
    """Thread-safe state update broadcast."""
    if _loop is None:
        return
    message = json.dumps({"state": state})
    asyncio.run_coroutine_threadsafe(_broadcast(message), _loop)

def set_orb_visibility(visible: bool) -> dict:
    """Toggle visibility of the orb."""
    if _loop is None:
        return {"status": "error", "message": "Orb is not running yet."}
    message = json.dumps({"visibility": "show" if visible else "hide"})
    future = asyncio.run_coroutine_threadsafe(_broadcast(message), _loop)
    try:
        future.result(timeout=2)
    except Exception as exc:
        return {"status": "error", "message": f"Could not reach the orb: {exc}"}
    if not _clients:
        return {"status": "error", "message": "Orb window is not connected."}
    return {"status": "ok", "visible": visible}
