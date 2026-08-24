import comtypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from tools.registry import register_tool
from security.policy import RiskClass


def _get_volume_interface():
    comtypes.CoInitialize()
    devices = AudioUtilities.GetSpeakers()

    if hasattr(devices, "EndpointVolume"):
        return devices.EndpointVolume  # newer pycaw wrapper

    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(IAudioEndpointVolume)


@register_tool(risk=RiskClass.YELLOW)
def set_volume(level: int) -> dict:
    """Set the system master volume to a specific percentage.

    Args:
        level: Volume level from 0 to 100.

    Returns:
        dict: the volume level that was actually set
    """
    level = max(0, min(100, level))
    volume = _get_volume_interface()
    volume.SetMasterVolumeLevelScalar(level / 100.0, None)
    return {"status": "ok", "volume": level}


@register_tool(risk=RiskClass.YELLOW)
def mute_volume(mute: bool = True) -> dict:
    """Mute or unmute the system volume.

    Args:
        mute: True to mute, False to unmute.

    Returns:
        dict: the resulting mute state
    """
    volume = _get_volume_interface()
    volume.SetMute(1 if mute else 0, None)
    return {"status": "ok", "muted": mute}


@register_tool(risk=RiskClass.GREEN)
def get_volume() -> dict:
    """Get the current system volume level and mute state.

    Returns:
        dict: current volume percentage and whether it's muted
    """
    volume = _get_volume_interface()
    current = volume.GetMasterVolumeLevelScalar()
    return {"volume": round(current * 100), "muted": bool(volume.GetMute())}