"""Unit tests for GeminiProvider and Gemini backend routing."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from friday.models.base import ModelMessage, ModelResponse
from friday.models.gemini_backend import GeminiProvider
from friday.models.router import ModelRouter
from friday.config import Settings, ModelDef


class MockFunctionCall:
    def __init__(self, name: str, args: dict):
        self.name = name
        self.args = args


class MockGenerateResponse:
    def __init__(self, text: str = "", function_calls: list | None = None, response_id: str = "mock-123"):
        self.text = text
        self.function_calls = function_calls or []
        self.response_id = response_id


def test_gemini_provider_init():
    provider = GeminiProvider(model="gemini-3.8-flash", api_key="dummy-key")
    assert provider.model == "gemini-3.8-flash"
    assert provider.api_key == "dummy-key"
    assert provider.supports_tools() is True
    assert provider.supports_vision() is True


def test_gemini_provider_health_no_key():
    with patch.dict(os.environ, {}, clear=True):
        provider = GeminiProvider(model="gemini-3.8-flash", api_key="")
        provider.api_key = None
        health = provider.health()
        assert health.available is False
        assert health.model_loaded is False


def test_gemini_provider_health_success():
    provider = GeminiProvider(model="gemini-3.8-flash", api_key="dummy-key")
    mock_client = MagicMock()
    mock_client.models.get.return_value = MagicMock()
    provider._client = mock_client

    health = provider.health()
    assert health.available is True
    assert health.model_loaded is True
    assert health.latency_ms is not None


def test_gemini_provider_generate_text():
    provider = GeminiProvider(model="gemini-3.8-flash", api_key="dummy-key")
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MockGenerateResponse(text="Hello Boss!")
    provider._client = mock_client

    messages = [
        ModelMessage(role="system", content="You are FRIDAY."),
        ModelMessage(role="user", content="Hi Friday"),
    ]

    resp = provider.generate(messages=messages)
    assert isinstance(resp, ModelResponse)
    assert resp.text == "Hello Boss!"
    assert resp.tool_calls == []
    assert mock_client.models.generate_content.called


def test_gemini_provider_generate_tool_call():
    provider = GeminiProvider(model="gemini-3.8-flash", api_key="dummy-key")
    mock_client = MagicMock()
    mock_fc = MockFunctionCall(name="system.get_time", args={})
    mock_client.models.generate_content.return_value = MockGenerateResponse(
        text="",
        function_calls=[mock_fc]
    )
    provider._client = mock_client

    messages = [ModelMessage(role="user", content="What time is it?")]
    tools = [{
        "type": "function",
        "function": {
            "name": "system.get_time",
            "description": "Get current time",
            "parameters": {"type": "object", "properties": {}}
        }
    }]

    resp = provider.generate(messages=messages, tools=tools)
    assert isinstance(resp, ModelResponse)
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0]["function"]["name"] == "system.get_time"
    assert resp.tool_calls[0]["function"]["arguments"] == {}


def test_gemini_provider_stream():
    provider = GeminiProvider(model="gemini-3.8-flash", api_key="dummy-key")
    mock_client = MagicMock()
    chunk1 = MockGenerateResponse(text="Good ")
    chunk2 = MockGenerateResponse(text="morning!")
    mock_client.models.generate_content_stream.return_value = [chunk1, chunk2]
    provider._client = mock_client

    deltas = list(provider.stream(messages=[ModelMessage(role="user", content="Hello")]))
    assert len(deltas) == 2
    assert deltas[0].text == "Good "
    assert deltas[1].text == "morning!"


def test_router_instantiates_gemini():
    settings = Settings()
    settings.models.reasoning = ModelDef(provider="gemini", model="gemini-3.8-flash")
    settings.gemini_api_key = "test-key"

    router = ModelRouter(settings)
    provider = router.get("reasoning")
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "gemini-3.8-flash"
    assert provider.api_key == "test-key"

