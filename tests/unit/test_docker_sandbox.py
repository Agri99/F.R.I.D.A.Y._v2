"""
tests/unit/test_docker_sandbox.py

WHAT THIS IS FOR:
Proves the actual bug is fixed: IsolatedTester.use_docker was a dead flag
- set in the constructor, never read anywhere, so every execution path
ran on the host via subprocess.run() regardless of its value. These tests
mock the `docker` SDK (no live daemon needed) to prove use_docker=True
genuinely routes through container execution now, and that use_docker=
False is completely unchanged from before (regression guard).
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from friday.development.tester import IsolatedTester


def test_host_mode_unchanged_when_use_docker_false(tmp_path):
    """Regression guard: default behavior (use_docker=False) must be
    byte-for-byte the same subprocess path as before this fix."""
    tester = IsolatedTester(use_docker=False)
    result = tester._run_cmd([sys.executable, "-c", "print('hello')"], tmp_path)
    assert result.passed is True
    assert "hello" in result.stdout


def test_docker_mode_actually_calls_docker_sdk_not_subprocess(tmp_path, monkeypatch):
    """The core bug, proven: with use_docker=True, _run_cmd must reach
    docker.from_env() and containers.run() - not silently fall through to
    subprocess.run() like it used to."""
    import friday.development.tester as tester_mod  # noqa: F401

    fake_client = MagicMock()
    fake_client.ping.return_value = True
    fake_client.images.get.return_value = MagicMock()  # image "already exists"

    fake_container = MagicMock()
    fake_container.wait.return_value = {"StatusCode": 0}
    fake_container.logs.return_value = b"all good\n"
    fake_client.containers.run.return_value = fake_container

    fake_docker_module = SimpleNamespace(from_env=lambda: fake_client)
    monkeypatch.setitem(sys.modules, "docker", fake_docker_module)

    tester = IsolatedTester(use_docker=True)
    result = tester._run_cmd(["python", "-m", "pytest"], tmp_path)

    fake_client.containers.run.assert_called_once()
    call_kwargs = fake_client.containers.run.call_args.kwargs
    assert call_kwargs["network_disabled"] is True
    assert call_kwargs["user"] == "sandbox"
    assert call_kwargs["volumes"][str(tmp_path.resolve())]["mode"] == "ro"
    assert result.passed is True
    assert result.stdout == "all good\n"


def test_docker_daemon_unreachable_fails_cleanly_not_crash(tmp_path, monkeypatch):
    """If Docker Desktop isn't running, this must return a clear failure -
    not raise an unhandled exception that would crash the calling tool."""
    fake_client = MagicMock()
    fake_client.ping.side_effect = ConnectionError("daemon not running")
    fake_docker_module = SimpleNamespace(from_env=lambda: fake_client)
    monkeypatch.setitem(sys.modules, "docker", fake_docker_module)

    tester = IsolatedTester(use_docker=True)
    result = tester._run_cmd(["python", "-m", "pytest"], tmp_path)

    assert result.passed is False
    assert "not reachable" in result.stderr.lower()


def test_docker_sdk_not_installed_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", None)  # simulates ImportError on `import docker`

    tester = IsolatedTester(use_docker=True)
    result = tester._run_cmd(["python", "-m", "pytest"], tmp_path)

    assert result.passed is False
    assert "not installed" in result.stderr.lower()


def test_container_command_swaps_host_python_for_sandbox_python(tmp_path, monkeypatch):
    """The host's absolute python.exe path doesn't exist inside the
    container - it must be swapped for the sandbox image's own 'python'."""
    fake_client = MagicMock()
    fake_client.ping.return_value = True
    fake_client.images.get.return_value = MagicMock()
    fake_container = MagicMock()
    fake_container.wait.return_value = {"StatusCode": 0}
    fake_container.logs.return_value = b""
    fake_client.containers.run.return_value = fake_container
    monkeypatch.setitem(sys.modules, "docker", SimpleNamespace(from_env=lambda: fake_client))

    tester = IsolatedTester(use_docker=True, python_executable="C:\\weird\\host\\python.exe")
    tester._run_cmd(["C:\\weird\\host\\python.exe", "-m", "pytest"], tmp_path)

    called_command = fake_client.containers.run.call_args.kwargs["command"]
    assert called_command == ["python", "-m", "pytest"]


def test_resource_limits_are_applied(tmp_path, monkeypatch):
    fake_client = MagicMock()
    fake_client.ping.return_value = True
    fake_client.images.get.return_value = MagicMock()
    fake_container = MagicMock()
    fake_container.wait.return_value = {"StatusCode": 0}
    fake_container.logs.return_value = b""
    fake_client.containers.run.return_value = fake_container
    monkeypatch.setitem(sys.modules, "docker", SimpleNamespace(from_env=lambda: fake_client))

    tester = IsolatedTester(use_docker=True, cpu_limit=1.5, memory_limit_mb=1024)
    tester._run_cmd(["python", "-c", "pass"], tmp_path)

    call_kwargs = fake_client.containers.run.call_args.kwargs
    assert call_kwargs["mem_limit"] == "1024m"
    assert call_kwargs["nano_cpus"] == int(1.5 * 1_000_000_000)


def test_container_always_removed_even_on_failure(tmp_path, monkeypatch):
    fake_client = MagicMock()
    fake_client.ping.return_value = True
    fake_client.images.get.return_value = MagicMock()
    fake_container = MagicMock()
    fake_container.wait.side_effect = Exception("timeout")
    fake_client.containers.run.return_value = fake_container
    monkeypatch.setitem(sys.modules, "docker", SimpleNamespace(from_env=lambda: fake_client))

    tester = IsolatedTester(use_docker=True, docker_timeout_seconds=1)
    result = tester._run_cmd(["python", "-m", "pytest"], tmp_path)

    fake_container.remove.assert_called_once_with(force=True)
    assert result.passed is False
