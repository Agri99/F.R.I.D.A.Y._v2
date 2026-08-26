"""
src/friday/models/cloud_backend.py

WHAT THIS IS FOR:
An optional OpenAI-compatible cloud provider fallback (§29).

WHY IT'S BUILT THIS WAY:
If local hardware is insufficient or fails, this can step in.
Secrets are passed explicitly and it provides a graceful fallback
while adhering to Principle B and E.
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


class CloudProvider(ModelProvider):
    def __init__(self, model: str, api_key: str, base_url: str = "https://api.openai.com/v1", timeout: int = 60):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def supports_tools(self) -> bool:
        return True  # Generally OpenAI-compatible models support tools

    def supports_vision(self) -> bool:
        return True  # Generally OpenAI-compatible models support vision

    def health(self) -> ProviderHealth:
        start_time = time.time()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            r = requests.get(f"{self.base_url}/models", headers=headers, timeout=5)
            latency = (time.time() - start_time) * 1000
            if r.status_code == 200:
                data = r.json()
                models = [m.get("id") for m in data.get("data", [])]
                model_loaded = self.model in models
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
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        api_messages = []
        for i, m in enumerate(messages):
            if images and i == len(messages) - 1:
                content = [{"type": "text", "text": m.content}]
                for img in images:
                    content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}})
                api_messages.append({"role": m.role, "content": content})
            else:
                api_messages.append({"role": m.role, "content": m.content})

        payload = {
            "model": self.model,
            "messages": api_messages,
            "stream": False
        }
        
        if tools:
            # Note: Expects tools in OpenAI schema format
            payload["tools"] = tools

        resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        
        # Parse tool calls to match our internal representation
        tool_calls = message.get("tool_calls", [])
        formatted_tools = []
        if tool_calls:
            for tc in tool_calls:
                formatted_tools.append({
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"]["arguments"])
                    }
                })

        return ModelResponse(
            text=message.get("content") or "",
            tool_calls=formatted_tools,
            raw=data
        )

    def stream(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
    ) -> Iterator[ModelDelta]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        payload = {
            "model": self.model,
            "messages": api_messages,
            "stream": True
        }
        
        if tools:
            payload["tools"] = tools

        resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=self.timeout, stream=True)
        resp.raise_for_status()

        for line in resp.iter_lines():
            if line:
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data_str = line_str[6:]
                    if data_str == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        choice = data.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        
                        text = delta.get("content") or ""
                        
                        tool_calls = delta.get("tool_calls", [])
                        formatted_tools = None
                        if tool_calls:
                            formatted_tools = []
                            for tc in tool_calls:
                                if "function" in tc:
                                    args = tc["function"].get("arguments", "")
                                    name = tc["function"].get("name")
                                    tool_chunk = {"function": {"arguments": args}}
                                    if name:
                                        tool_chunk["function"]["name"] = name
                                    formatted_tools.append(tool_chunk)

                        yield ModelDelta(text=text, tool_calls=formatted_tools)
                    except json.JSONDecodeError:
                        continue
