from orb.state_server import set_orb_visibility
from tools.registry import register_tool
from security.policy import RiskClass


@register_tool(risk=RiskClass.GREEN)
def toggle_orb(visible: bool) -> dict:
    """Show or hide FRIDAY's floating 3D orb window. This does not shut down the assistant.
    Use this for phrases like 'hide yourself', 'hide the orb', 'disappear', 'go away',
    'come back', 'show yourself', or 'appear'. Do not use window control for this.

    Args:
        visible: True to show the orb, False to hide it.

    Returns:
        dict: status and whether the orb should be visible
    """
    return set_orb_visibility(visible)