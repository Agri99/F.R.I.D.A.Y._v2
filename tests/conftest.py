"""
Shared test fixtures.
"""
import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    """Isolate cwd so tests don't pollute real project files."""
    monkeypatch.chdir(tmp_path)

@pytest.fixture
def mock_settings():
    class Settings:
        def __init__(self):
            self.model = "test-model"
            self.temperature = 0.0
    return Settings()

@pytest.fixture
def mock_model_provider():
    class MockProvider:
        def generate(self, *args, **kwargs):
            return "mocked response"
    return MockProvider()

@pytest.fixture
def tool_registry():
    class MockRegistry:
        def get(self, name):
            return None
    return MockRegistry()
