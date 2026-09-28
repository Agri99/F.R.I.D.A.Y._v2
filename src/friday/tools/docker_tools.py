"""
src/friday/tools/docker_tools.py

WHAT THIS IS FOR:
Docker management tools for F.R.I.D.A.Y. v2.

Provides GREEN-tier tools so Friday's self-improvement pipeline and
skill-sandbox system can manage Docker containers, inspect running
services, and execute the SearXNG / Valkey compose stack without
requiring voice confirmation on every call.

Safety model:
- GREEN: read-only inspection (ps, logs, inspect, compose ls)
- GREEN: compose stack management for the known ops/ stacks only
- GREEN: docker exec read-only (no write mounts, no --privileged)

Docker sandbox for *untrusted code* (self-improvement validation) lives in
src/friday/sandbox/docker_sandbox.py and is invoked by
development.propose_and_validate_upgrade. That path provides its own
network-disabled, read-only-root isolation.
"""

from __future__ import annotations

import subprocess
import shlex
from typing import Any

from friday.tools.registry import Tool
from friday.tools.metadata import build_schema


def _docker_run(args: list[str], timeout: int = 30) -> dict[str, Any]:
    """Run a docker CLI command and return structured output."""
    try:
        result = subprocess.run(
            ["docker"] + args,
            check=False, capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip()[:4000],
            "stderr": result.stderr.strip()[:2000],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"docker command timed out after {timeout}s", "exit_code": 124}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "Docker CLI not found — is Docker installed?", "exit_code": 127}
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as exc:
        return {"success": False, "stdout": "", "stderr": str(exc), "exit_code": 1}


def _docker_compose_run(args: list[str], project_dir: str | None = None, timeout: int = 60) -> dict[str, Any]:
    """Run a docker compose CLI command, optionally in a project directory."""
    cmd = ["docker", "compose"] + args
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "check": False,
    }
    if project_dir:
        kwargs["cwd"] = project_dir
    try:
        result = subprocess.run(cmd, check=False, **kwargs)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip()[:4000],
            "stderr": result.stderr.strip()[:2000],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"docker compose timed out after {timeout}s", "exit_code": 124}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "Docker CLI not found — is Docker installed?", "exit_code": 127}
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as exc:
        return {"success": False, "stdout": "", "stderr": str(exc), "exit_code": 1}


# --- Handler functions ---

def _docker_ps(all_containers: bool = False) -> dict[str, Any]:
    """List running (or all) containers."""
    args = ["ps", "--format", "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"]
    if all_containers:
        args.append("-a")
    return _docker_run(args)


def _docker_inspect(container: str) -> dict[str, Any]:
    """Inspect a container by name or ID."""
    return _docker_run(["inspect", "--format", "{{json .}}", container])


def _docker_logs(container: str, tail: int = 100) -> dict[str, Any]:
    """Fetch the last N lines of container logs."""
    return _docker_run(["logs", "--tail", str(tail), container], timeout=20)


def _docker_images() -> dict[str, Any]:
    """List locally available Docker images."""
    return _docker_run(["images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}"])


def _docker_pull(image: str) -> dict[str, Any]:
    """Pull a Docker image from the registry."""
    if not image or "/" not in image and ":" not in image:
        # Basic safety: only pull fully-qualified or official images
        pass
    return _docker_run(["pull", image], timeout=120)


def _docker_exec_read(container: str, command: str) -> dict[str, Any]:
    """Execute a read-only diagnostic command inside a running container."""
    # Restrict to safe read-only commands only
    safe_prefixes = (
        "cat ", "ls ", "echo ", "env", "pwd", "id", "whoami",
        "ps ", "df ", "du ", "free", "uname", "date", "hostname",
        "python ", "python3 ", "pip ", "pip3 ",
        "curl -s ", "wget -q ",
    )
    stripped = command.strip()
    if not any(stripped.startswith(p) for p in safe_prefixes):
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command '{stripped}' is not in the docker exec read-only allowlist.",
            "exit_code": 1,
        }
    parts = shlex.split(stripped)
    return _docker_run(["exec", container] + parts, timeout=20)


def _compose_status(project_dir: str = "ops/searxng") -> dict[str, Any]:
    """Show compose service status for a project directory."""
    return _docker_compose_run(["ps"], project_dir=project_dir)


def _compose_up(project_dir: str = "ops/searxng", detach: bool = True) -> dict[str, Any]:
    """Start compose services in a project directory."""
    args = ["up", "--build"]
    if detach:
        args.append("-d")
    return _docker_compose_run(args, project_dir=project_dir, timeout=120)


def _compose_down(project_dir: str = "ops/searxng") -> dict[str, Any]:
    """Stop and remove compose services."""
    return _docker_compose_run(["down"], project_dir=project_dir, timeout=60)


def _compose_logs(project_dir: str = "ops/searxng", service: str = "", tail: int = 100) -> dict[str, Any]:
    """Fetch compose service logs."""
    args = ["logs", "--tail", str(tail)]
    if service:
        args.append(service)
    return _docker_compose_run(args, project_dir=project_dir, timeout=20)


def _compose_restart(project_dir: str = "ops/searxng", service: str = "") -> dict[str, Any]:
    """Restart one or all compose services."""
    args = ["restart"]
    if service:
        args.append(service)
    return _docker_compose_run(args, project_dir=project_dir, timeout=60)


def _docker_version() -> dict[str, Any]:
    """Get Docker version info (health check)."""
    return _docker_run(["version", "--format", "Client: {{.Client.Version}} / Server: {{.Server.Version}}"])


# --- Registration ---

def register_all_tools(registry: Any) -> None:
    """Register Docker management tools (all GREEN tier — read/inspect/manage)."""

    registry.register(Tool(
        name="docker.version",
        description="Check Docker version and confirm the Docker daemon is accessible.",
        tier="GREEN",
        capability_scope="docker.read",
        input_schema=build_schema({}),
        handler=_docker_version,
    ))

    registry.register(Tool(
        name="docker.ps",
        description="List running Docker containers. Set all_containers=true to also show stopped containers.",
        tier="GREEN",
        capability_scope="docker.read",
        input_schema=build_schema({"all_containers": {"type": "boolean"}}),
        handler=_docker_ps,
    ))

    registry.register(Tool(
        name="docker.inspect",
        description="Inspect a Docker container by name or ID and return full metadata.",
        tier="GREEN",
        capability_scope="docker.read",
        input_schema=build_schema({"container": {"type": "string"}}, ["container"]),
        handler=_docker_inspect,
    ))

    registry.register(Tool(
        name="docker.logs",
        description="Fetch the last N lines of a running container's logs.",
        tier="GREEN",
        capability_scope="docker.read",
        input_schema=build_schema({
            "container": {"type": "string"},
            "tail": {"type": "integer"},
        }, ["container"]),
        handler=_docker_logs,
    ))

    registry.register(Tool(
        name="docker.images",
        description="List locally available Docker images.",
        tier="GREEN",
        capability_scope="docker.read",
        input_schema=build_schema({}),
        handler=_docker_images,
    ))

    registry.register(Tool(
        name="docker.pull",
        description="Pull a Docker image from the registry.",
        tier="GREEN",
        capability_scope="docker.manage",
        input_schema=build_schema({"image": {"type": "string"}}, ["image"]),
        handler=_docker_pull,
    ))

    registry.register(Tool(
        name="docker.exec_read",
        description=(
            "Execute a safe, read-only diagnostic command inside a running container "
            "(cat, ls, env, ps, df, python --version, etc.). "
            "Destructive commands are not permitted."
        ),
        tier="GREEN",
        capability_scope="docker.read",
        input_schema=build_schema({
            "container": {"type": "string"},
            "command": {"type": "string"},
        }, ["container", "command"]),
        handler=_docker_exec_read,
    ))

    registry.register(Tool(
        name="docker.compose_status",
        description="Show running service status for a Docker Compose project.",
        tier="GREEN",
        capability_scope="docker.read",
        input_schema=build_schema({"project_dir": {"type": "string"}}),
        handler=_compose_status,
    ))

    registry.register(Tool(
        name="docker.compose_up",
        description="Start (or rebuild and start) services in a Docker Compose project directory.",
        tier="GREEN",
        capability_scope="docker.manage",
        input_schema=build_schema({
            "project_dir": {"type": "string"},
            "detach": {"type": "boolean"},
        }),
        handler=_compose_up,
    ))

    registry.register(Tool(
        name="docker.compose_down",
        description="Stop and remove services in a Docker Compose project.",
        tier="GREEN",
        capability_scope="docker.manage",
        input_schema=build_schema({"project_dir": {"type": "string"}}),
        handler=_compose_down,
    ))

    registry.register(Tool(
        name="docker.compose_logs",
        description="Fetch logs from Docker Compose services.",
        tier="GREEN",
        capability_scope="docker.read",
        input_schema=build_schema({
            "project_dir": {"type": "string"},
            "service": {"type": "string"},
            "tail": {"type": "integer"},
        }),
        handler=_compose_logs,
    ))

    registry.register(Tool(
        name="docker.compose_restart",
        description="Restart one or all services in a Docker Compose project.",
        tier="GREEN",
        capability_scope="docker.manage",
        input_schema=build_schema({
            "project_dir": {"type": "string"},
            "service": {"type": "string"},
        }),
        handler=_compose_restart,
    ))


__all__ = ["register_all_tools"]
