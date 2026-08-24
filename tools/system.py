import psutil
from tools.registry import register_tool
from security.policy import RiskClass


@register_tool(risk=RiskClass.GREEN)
def get_system_info() -> dict:
    """Get current CPU usage, RAM usage, and free disk space.

    Returns:
        dict: cpu_percent, ram_percent, disk_free_gb
    """
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_free_gb": round(psutil.disk_usage("C:\\").free / (1024 ** 3), 1),
    }