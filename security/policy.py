from enum import Enum


class RiskClass(Enum):
    GREEN = "green"    # read-only, no confirmation needed
    YELLOW = "yellow"  # reversible local changes
    ORANGE = "orange"  # external effects (email, calendar writes, etc.)
    RED = "red"        # destructive or system-wide


def requires_confirmation(risk: RiskClass) -> bool:
    return risk in (RiskClass.ORANGE, RiskClass.RED)