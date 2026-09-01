"""llama.cpp-compatible GGUF model backend."""
from __future__ import annotations

import json
import time
from collections.abc import Iterator

import requests

from friday.models.base import ModelDelta, ModelMessage, ModelProvider, ModelResponse, ProviderHealth


class LlamaCppProvider(ModelProvider):
    """Talk to llama.cpp's OpenAI-compatible HTTP server without owning its process."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:8080",
        timeout: int = 120,
        supports_tools: bool = True,
        supports_vision: bool = False,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._supports_tools = supports_tools
        self._supports_vision = supports_vision

    def supports_tools(self) -> bool:
        return self._supports_tools

    def supports_vision(self) -> bool:
        return self._supports_vision

    def health(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            response = requests.get(f"{self.base_url}/health", timeout=3)
            latency = (time.perf_counter() - started) * 1000
            if response.status_code != 200:
                return ProviderHealth(False, False, latency)
            payload = response.json() if response.content else {}
            status = str(payload.get("status", "ok")).lower()
            loaded = status in {"ok", "ready", "loaded"}
            return ProviderHealth(True, loaded, latency)
        except (requests.RequestException, ValueError):
            return ProviderHealth(False, False)

    def generate(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
        images: list[str] | None = None,
    ) -> ModelResponse:
        if images and not self.supports_vision():
            raise ValueError("Configured llama.cpp provider does not support vision")
        payload = self._payload(messages, tools, stream=False)
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {})
        return ModelResponse(
            text=message.get("content") or "",
            tool_calls=self._tool_calls(message.get("tool_calls", [])),
            raw=data,
        )

    def stream(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
    ) -> Iterator[ModelDelta]:
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=self._payload(messages, tools, stream=True),
            timeout=self.timeout,
            stream=True,
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8")
            if not text.startswith("data: "):
                continue
            encoded = text[6:]
            if encoded == "[DONE]":
                break
            try:
                delta = json.loads(encoded).get("choices", [{}])[0].get("delta", {})
            except json.JSONDecodeError:
                continue
            yield ModelDelta(
                text=delta.get("content") or "",
                tool_calls=self._tool_calls(delta.get("tool_calls", [])) or None,
            )

    def _payload(self, messages: list[ModelMessage], tools: list[dict] | None, stream: bool) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "stream": stream,
        }
        if tools:
            if not self.supports_tools():
                raise ValueError("Configured llama.cpp provider does not support tools")
            payload["tools"] = tools
        return payload

    @staticmethod
    def _tool_calls(calls: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for call in calls or []:
            function = dict(call.get("function", {}))
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    function["arguments"] = json.loads(arguments)
                except json.JSONDecodeError:
                    function["arguments"] = arguments
            normalized.append({"function": function})
        return normalized


__all__ = ["LlamaCppProvider"]
