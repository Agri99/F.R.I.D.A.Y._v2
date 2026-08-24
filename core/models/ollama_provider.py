"""
core/models/ollama_provider.py

WHAT THIS IS FOR:
One concrete ModelProvider that talks to a locally running Ollama
server (http://localhost:11434 by default). This is the ONLY file in
the whole project allowed to know Ollama's HTTP API shape.

WHY IT'S BUILT THIS WAY:
Isolation. If Ollama's API changes, or you switch to llama.cpp
directly, this file is the blast radius — not the orchestrator.
"""

from __future__ import annotations

import requests

from core.models.base import ModelMessage, ModelProvider, ModelResponse


class OllamaProvider(ModelProvider):
    def __init__(self, model: str, host: str = "http://localhost:11434", timeout: int = 120):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=3)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def generate(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
    ) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        if tools:
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
