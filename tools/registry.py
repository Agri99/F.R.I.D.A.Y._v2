from security.policy import RiskClass


class ToolDefinition:
    def __init__(self, func, risk, preview=None, pre_notice=None, critical=False):
        self.func = func
        self.risk = risk
        self.name = func.__name__
        self.preview = preview
        self.pre_notice = pre_notice  # optional string spoken before this tool runs
        self.critical = critical


TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(risk: RiskClass, preview=None, pre_notice=None, critical=False):
    def decorator(func):
        TOOL_REGISTRY[func.__name__] = ToolDefinition(func, risk, preview=preview, pre_notice=pre_notice, critical=critical)
        return func
    return decorator