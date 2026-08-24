from pathlib import Path
from tools.registry import register_tool
from security.policy import RiskClass


@register_tool(risk=RiskClass.YELLOW)
def create_text_file(filename: str, content: str) -> dict:
    """Create a text file with the given content in FRIDAY's workspace folder.

    Args:
        filename: Name of the file to create, e.g. 'notes.txt'
        content: Text content to write into the file

    Returns:
        dict: path of the created file and status
    """
    workspace = Path("workspace")
    workspace.mkdir(exist_ok=True)

    safe_name = Path(filename).name  # strips any ../ path traversal attempt
    file_path = workspace / safe_name

    file_path.write_text(content, encoding="utf-8")
    return {"status": "created", "path": str(file_path)}

def _preview_delete(filename: str) -> dict:
    safe_name = Path(filename).name
    file_path = Path("workspace") / safe_name
    if not file_path.exists():
        return {"found": False, "message": f"{safe_name} does not exist"}
    return {"found": True, "path": str(file_path), "size_bytes": file_path.stat().st_size}

@register_tool(risk=RiskClass.RED, preview=_preview_delete)
def delete_workspace_file(filename: str) -> dict:
    """Delete a file from FRIDAY's workspace folder.

    Args:
        filename: Name of the file to delete, e.g. 'notes.txt'

    Returns:
        dict: status of the deletion
    """
    from pathlib import Path
    safe_name = Path(filename).name
    file_path = Path("workspace") / safe_name

    if not file_path.exists():
        return {"status": "error", "message": f"{safe_name} does not exist"}

    file_path.unlink()
    return {"status": "deleted", "path": str(file_path)}