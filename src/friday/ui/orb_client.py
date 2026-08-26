"""Orb client interface."""
from __future__ import annotations

class OrbClient:
    """Client for controlling the Orb UI."""
    
    def update_state(self, state: str) -> None:
        """Send state to the orb server."""
        from friday.ui.orb_server import set_state
        set_state(state)
        
    def show(self) -> None:
        """Show the orb overlay."""
        from friday.ui.orb_server import set_orb_visibility
        set_orb_visibility(True)
        
    def hide(self) -> None:
        """Hide the orb overlay."""
        from friday.ui.orb_server import set_orb_visibility
        set_orb_visibility(False)
        
    def move(self, x: int, y: int) -> None:
        """Move the orb (placeholder)."""
        pass
