from __future__ import annotations
import comtypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from .registry import Tool
from .metadata import build_schema

def _get_volume_interface():
    comtypes.CoInitialize()
    devices = AudioUtilities.GetSpeakers()
    if hasattr(devices, "EndpointVolume"):
        return devices.EndpointVolume
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(IAudioEndpointVolume)

def _set_volume(level: int) -> dict:
    try:
        level = max(0, min(100, level))
        volume = _get_volume_interface()
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return {"status": "ok", "volume": level}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

def _mute(mute: bool = True) -> dict:
    try:
        volume = _get_volume_interface()
        volume.SetMute(1 if mute else 0, None)
        return {"status": "ok", "muted": mute}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

def _get_volume() -> dict:
    try:
        volume = _get_volume_interface()
        current = volume.GetMasterVolumeLevelScalar()
        return {"volume": round(current * 100), "muted": bool(volume.GetMute())}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

def register_all_tools(registry) -> None:
    registry.register(Tool(
        name="audio.set_volume",
        description="Set volume level.",
        tier="GREEN",
        capability_scope="system.control",
        input_schema=build_schema({"level": {"type": "integer"}}, ["level"]),
        handler=_set_volume
    ))
    registry.register(Tool(
        name="audio.mute",
        description="Mute/unmute.",
        tier="GREEN",
        capability_scope="system.control",
        input_schema=build_schema({"mute": {"type": "boolean"}}),
        handler=_mute
    ))
    registry.register(Tool(
        name="audio.get_volume",
        description="Get current volume.",
        tier="GREEN",
        capability_scope="system.read",
        input_schema=build_schema({}),
        handler=_get_volume
    ))
