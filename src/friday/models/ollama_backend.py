"""
src/friday/models/ollama_backend.py

WHAT THIS IS FOR:
One concrete ModelProvider that talks to a locally running Ollama
server. Implements all enhanced capabilities like vision, streaming,
and health monitoring.

WHY IT'S BUILT THIS WAY:
Isolation. If Ollama's API changes, this is the only file that needs to change.
"""

from __future__ import annotations

import time
import requests
import json
from typing import Iterator

from friday.models.base import (
    ModelDelta,
    ModelMessage,
    ModelProvider,
    ModelResponse,
    ProviderHealth,
)


class OllamaProvider(ModelProvider):
    def __init__(self, model: str, host: str = "http://localhost:11434", timeout: int = 120):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._supports_tools_cache: bool | None = None
        self._supports_vision_cache: bool | None = None

    def _fetch_model_info(self) -> dict | None:
        try:
            r = requests.get(f"{self.host}/api/show", json={"name": self.model}, timeout=3)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        return None

    def supports_tools(self) -> bool:
        if self._supports_tools_cache is not None:
            return self._supports_tools_cache
        
        info = self._fetch_model_info()
        if info:
            template = info.get("template", "")
            # Modern Ollama models (Qwen, Llama, Mistral) support tools natively
            self._supports_tools_cache = True
        else:
            self._supports_tools_cache = True
        return self._supports_tools_cache


    def supports_vision(self) -> bool:
        if self._supports_vision_cache is not None:
            return self._supports_vision_cache
        
        info = self._fetch_model_info()
        if info:
            details = info.get("details", {})
            families = details.get("families", []) or []
            self._supports_vision_cache = "clip" in families or "vision" in families
        else:
            self._supports_vision_cache = False
        return self._supports_vision_cache

    def health(self) -> ProviderHealth:
        start_time = time.time()
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=3)
            latency = (time.time() - start_time) * 1000
            if r.status_code == 200:
                data = r.json()
                models = [m.get("name") for m in data.get("models", [])]
                model_loaded = any(self.model == m or self.model in m for m in models)
                return ProviderHealth(available=True, model_loaded=model_loaded, latency_ms=latency)
            return ProviderHealth(available=False, model_loaded=False)
        except requests.RequestException:
            return ProviderHealth(available=False, model_loaded=False)

    def generate(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
        images: list[str] | None = None,
    ) -> ModelResponse:
        ollama_messages = []
        for i, m in enumerate(messages):
            msg = {"role": m.role, "content": m.content}
            # Append images to the last message if provided
            if images and i == len(messages) - 1 and self.supports_vision():
                msg["images"] = images
            ollama_messages.append(msg)

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
        }
        if tools and self.supports_tools():
            payload["tools"] = tools

        resp = requests.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        message = data.get("message", {})
        return ModelResponse(
            text=message.get("content", ""),
            tool_calls=message.get("tool_calls", []) or [],
            raw=data,
        )

    def stream(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
    ) -> Iterator[ModelDelta]:
        ollama_messages = [{"role": m.role, "content": m.content} for m in messages]
        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
        }
        if tools and self.supports_tools():
            payload["tools"] = tools

        resp = requests.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout, stream=True)
        resp.raise_for_status()

        for line in resp.iter_lines():
            if line:
                data = json.loads(line)
                message = data.get("message", {})
                yield ModelDelta(
                    text=message.get("content", ""),
                    tool_calls=message.get("tool_calls", []) or None
                )
