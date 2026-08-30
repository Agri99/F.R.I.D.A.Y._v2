from __future__ import annotations
import shutil
from datetime import datetime
from pathlib import Path
from .registry import Tool, VerificationResult
from .metadata import build_schema

def _resolve_path(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        # Handle special folders
        if path.lower().startswith("downloads") or path.lower().startswith("~downloads"):
            p = Path.home() / "Downloads" / path.replace("downloads/", "").replace("~downloads/", "").lstrip("/\\")
        else:
            p = Path("workspace").resolve() / p
    return p.resolve()

def _list_dir(path: str = "") -> dict:
    target = _resolve_path(path)
    if not target.exists() or not target.is_dir():
        return {"status": "error", "message": "Directory does not exist"}

    # Sort files by modified time (latest first)
    files = sorted(target.iterdir(), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)
    return {"files": [p.name for p in files][:50]}  # limit to 50 for context size

def _read_file(filename: str) -> dict:
    file_path = _resolve_path(filename)
    if not file_path.exists():
        return {"status": "error", "message": "File does not exist"}
    return {"content": file_path.read_text(encoding="utf-8")}

def _write_file(filename: str, content: str) -> dict:
    file_path = _resolve_path(filename)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return {"status": "created", "path": str(file_path)}

def _verify_write(args: dict, result: dict) -> VerificationResult:
    if _resolve_path(args["filename"]).exists():
        return VerificationResult(True, "File written successfully")
    return VerificationResult(False, "File missing after write")

def _move_file(source: str, dest: str) -> dict:
    src_path = _resolve_path(source)
    dst_path = _resolve_path(dest)
    if not src_path.exists():
        return {"status": "error", "message": f"Source {src_path} does not exist"}
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.rename(dst_path)
    return {"status": "moved"}


def _find_latest(directory: str, pattern: str = "*.txt") -> dict:
    """Find the latest file in a directory matching a pattern."""
    target = _resolve_path(directory)
    if not target.exists() or not target.is_dir():
        return {"status": "error", "message": "Directory does not exist"}

    files = list(target.glob(pattern))
    if not files:
        return {"status": "error", "message": f"No files matching '{pattern}' found in {directory}"}

    latest = max(files, key=lambda x: x.stat().st_mtime)
    return {
        "status": "ok",
        "file": latest.name,
        "path": str(latest),
        "modified": datetime.fromtimestamp(latest.stat().st_mtime).isoformat()
    }

def _delete_file(filename: str) -> dict:
    file_path = _resolve_path(filename)
    if not file_path.exists():
        return {"status": "error", "message": "File does not exist"}
    file_path.unlink()
    return {"status": "deleted"}

def _preview_delete(filename: str, **kwargs) -> dict:
    file_path = _resolve_path(filename)
    if not file_path.exists():
        return {"found": False, "message": f"{filename} does not exist"}
    return {"found": True, "path": str(file_path), "size_bytes": file_path.stat().st_size}

def _verify_delete(args: dict, result: dict) -> VerificationResult:
    if not _resolve_path(args["filename"]).exists():
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
    registry.register(Tool(
        name="filesystem.find_latest",
        description="Find the latest file in a directory matching a pattern (e.g., '*.txt' in Downloads).",
        tier="GREEN",
        capability_scope="filesystem.read",
        input_schema=build_schema({
            "directory": {"type": "string"},
            "pattern": {"type": "string", "default": "*.txt"}
        }, ["directory"]),
        handler=_find_latest
    ))
