from __future__ import annotations
import shutil
from pathlib import Path
from .registry import Tool, VerificationResult
from .metadata import build_schema

def _get_workspace() -> Path:
    workspace = Path("workspace")
    workspace.mkdir(exist_ok=True)
    return workspace

def _list_dir(path: str = "") -> dict:
    wp = _get_workspace()
    target = (wp / path).resolve()
    if not str(target).startswith(str(wp.resolve())):
        return {"status": "error", "message": "Path out of bounds"}
    if not target.exists() or not target.is_dir():
        return {"status": "error", "message": "Directory does not exist"}
    return {"files": [p.name for p in target.iterdir()]}

def _read_file(filename: str) -> dict:
    wp = _get_workspace()
    safe_name = Path(filename).name
    file_path = wp / safe_name
    if not file_path.exists():
        return {"status": "error", "message": "File does not exist"}
    return {"content": file_path.read_text(encoding="utf-8")}

def _write_file(filename: str, content: str) -> dict:
    wp = _get_workspace()
    safe_name = Path(filename).name
    file_path = wp / safe_name
    file_path.write_text(content, encoding="utf-8")
    return {"status": "created", "path": str(file_path)}

def _verify_write(args: dict, result: dict) -> VerificationResult:
    wp = _get_workspace()
    safe_name = Path(args["filename"]).name
    if (wp / safe_name).exists():
        return VerificationResult(True, "File written successfully")
    return VerificationResult(False, "File missing after write")

def _move_file(source: str, dest: str) -> dict:
    wp = _get_workspace()
    src_path = wp / Path(source).name
    dst_path = wp / Path(dest).name
    if not src_path.exists():
        return {"status": "error", "message": "Source does not exist"}
    src_path.rename(dst_path)
    return {"status": "moved"}

def _delete_file(filename: str) -> dict:
    wp = _get_workspace()
    safe_name = Path(filename).name
    file_path = wp / safe_name
    if not file_path.exists():
        return {"status": "error", "message": "File does not exist"}
    file_path.unlink()
    return {"status": "deleted"}

def _preview_delete(filename: str, **kwargs) -> dict:
    safe_name = Path(filename).name
    file_path = _get_workspace() / safe_name
    if not file_path.exists():
        return {"found": False, "message": f"{safe_name} does not exist"}
    return {"found": True, "path": str(file_path), "size_bytes": file_path.stat().st_size}

def _verify_delete(args: dict, result: dict) -> VerificationResult:
    wp = _get_workspace()
    safe_name = Path(args["filename"]).name
    if not (wp / safe_name).exists():
        return VerificationResult(True, "File deleted successfully")
    return VerificationResult(False, "File still exists")

def register_all_tools(registry) -> None:
    registry.register(Tool(
        name="filesystem.list",
        description="List directory contents within workspace.",
        tier="GREEN",
        capability_scope="filesystem.read",
        input_schema=build_schema({"path": {"type": "string"}}),
        handler=_list_dir
    ))
    registry.register(Tool(
        name="filesystem.read",
        description="Read file content.",
        tier="GREEN",
        capability_scope="filesystem.read",
        input_schema=build_schema({"filename": {"type": "string"}}, ["filename"]),
        handler=_read_file
    ))
    registry.register(Tool(
        name="filesystem.write",
        description="Write content to a file.",
        tier="ORANGE",
        capability_scope="filesystem.write",
        input_schema=build_schema({
            "filename": {"type": "string"},
            "content": {"type": "string"}
        }, ["filename", "content"]),
        handler=_write_file,
        verify=_verify_write
    ))
    registry.register(Tool(
        name="filesystem.move",
        description="Move or rename a file.",
        tier="ORANGE",
        capability_scope="filesystem.write",
        input_schema=build_schema({
            "source": {"type": "string"},
            "dest": {"type": "string"}
        }, ["source", "dest"]),
        handler=_move_file
    ))
    registry.register(Tool(
        name="filesystem.delete",
        description="Delete a file.",
        tier="RED",
        capability_scope="filesystem.delete",
        input_schema=build_schema({"filename": {"type": "string"}}, ["filename"]),
        handler=_delete_file,
        preview=_preview_delete,
        verify=_verify_delete,
        critical=True
    ))
