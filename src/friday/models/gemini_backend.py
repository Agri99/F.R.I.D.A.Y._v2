"""
src/friday/models/gemini_backend.py

WHAT THIS IS FOR:
Google Gemini API model provider for F.R.I.D.A.Y. using the official google-genai SDK.
Implements the ModelProvider contract with native tool calling, streaming, multimodal vision,
health checking, and automated fallback on temporary 503 spikes.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any, Iterator

from friday.models.base import (
    ModelDelta,
    ModelMessage,
    ModelProvider,
    ModelResponse,
    ProviderHealth,
)
from friday.security.secrets import SecretsManager

try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]


class GeminiProvider(ModelProvider):
    """Concrete ModelProvider that interfaces with Google's Gemini API."""

    def __init__(
        self,
        model: str = "gemini-3.5-flash-lite",
        api_key: str | None = None,
        timeout: int = 60,
    ):
        self.model = model
        self.timeout = timeout
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

        if not self.api_key:
            try:
                secrets = SecretsManager()
                self.api_key = secrets.get("gemini_api_key") or secrets.get("google/gemini_api_key")
            except Exception:
                pass

        self._client: Any = None
        if _GENAI_AVAILABLE and self.api_key:
            self._client = genai.Client(api_key=self.api_key)

    @property
    def client(self):
        if not _GENAI_AVAILABLE:
            raise RuntimeError("The google-genai package is not installed. Install with `pip install google-genai`.")
        if self._client is None:
            if not self.api_key:
                self.api_key = os.environ.get("GEMINI_API_KEY")
                if not self.api_key:
                    try:
                        self.api_key = SecretsManager().get("gemini_api_key")
                    except Exception:
                        pass
            if not self.api_key:
                raise RuntimeError("GEMINI_API_KEY is not configured.")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return True

    def health(self) -> ProviderHealth:
        if not _GENAI_AVAILABLE:
            return ProviderHealth(available=False, model_loaded=False, error="google-genai library not installed")
        if not self.api_key:
            return ProviderHealth(available=False, model_loaded=False, error="GEMINI_API_KEY is not configured")

        start_time = time.time()
        models_to_probe = [self.model]
        if self.model != "gemini-3.5-flash-lite":
            models_to_probe.append("gemini-3.5-flash-lite")

        for m in models_to_probe:
            try:
                self.client.models.get(model=m)
                latency = (time.time() - start_time) * 1000.0
                return ProviderHealth(available=True, model_loaded=True, latency_ms=latency)
            except Exception as exc:
                if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                    continue
                return ProviderHealth(available=False, model_loaded=False, error=str(exc))

        return ProviderHealth(available=False, model_loaded=False, error="All probed Gemini models unavailable")

    def _build_request_payload(
        self,
        messages: list[ModelMessage] | list[dict] | str,
        tools: list[dict] | None = None,
        images: list[str] | None = None,
    ) -> tuple[list[Any], str | None, list[Any] | None]:
        """Convert Friday messages, tools, and images to google-genai types."""
        if isinstance(messages, str):
            messages = [ModelMessage(role="user", content=messages)]

        system_parts: list[str] = []
        contents: list[Any] = []

        for m in messages:
            role_val = getattr(m, "role", None) if not isinstance(m, dict) else m.get("role")
            content_val = getattr(m, "content", "") if not isinstance(m, dict) else m.get("content", "")
            if role_val == "system":
                system_parts.append(content_val)
            else:
                role = "user" if role_val == "user" else "model"
                part = types.Part.from_text(text=content_val)
                contents.append(types.Content(role=role, parts=[part]))

        # Append images to the last content turn if provided
        if images and contents:
            last_content = contents[-1]
            for img in images:
                try:
                    raw_bytes = base64.b64decode(img)
                    last_content.parts.append(
                        types.Part.from_bytes(data=raw_bytes, mime_type="image/jpeg")
                    )
                except Exception:
                    pass

        # If no user messages were provided, supply a minimal prompt
        if not contents:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text="Hello")]))

        system_instruction = "\n\n".join(system_parts) if system_parts else None

        gemini_tools = None
        if tools and self.supports_tools():
            declarations = []
            for t in tools:
                func = t.get("function", t)
                name = func.get("name")
                desc = func.get("description", "")
                params = func.get("parameters") or {"type": "object", "properties": {}}
                declarations.append(
                    types.FunctionDeclaration(
                        name=name,
                        description=desc,
                        parameters_json_schema=params,
                    )
                )
            if declarations:
                gemini_tools = [types.Tool(function_declarations=declarations)]

        return contents, system_instruction, gemini_tools

    def generate(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
        images: list[str] | None = None,
    ) -> ModelResponse:
        contents, system_instruction, gemini_tools = self._build_request_payload(messages, tools, images)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.2,
        )

        models_to_try = [self.model]
        if self.model != "gemini-3.5-flash-lite":
            models_to_try.append("gemini-3.5-flash-lite")
        if "gemini-3.1-flash-lite" not in models_to_try:
            models_to_try.append("gemini-3.1-flash-lite")

        last_exc: Exception | None = None
        resp: Any = None
        for m in models_to_try:
            try:
                resp = self.client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=config,
                )
                break
            except Exception as exc:
                last_exc = exc
                if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                    continue
                raise exc

        if resp is None:
            if last_exc:
                raise last_exc
            raise RuntimeError("No model response received.")

        tool_calls: list[dict] = []
        if resp.function_calls:
            for fc in resp.function_calls:
                args = dict(fc.args) if fc.args else {}
                tool_calls.append({
                    "function": {
                        "name": fc.name,
                        "arguments": args,
                    }
                })

        return ModelResponse(
            text=resp.text or "",
            tool_calls=tool_calls,
            raw={"id": getattr(resp, "response_id", None)},
        )

    def stream(
        self,
        messages: list[ModelMessage],
        tools: list[dict] | None = None,
    ) -> Iterator[ModelDelta]:
        contents, system_instruction, gemini_tools = self._build_request_payload(messages, tools)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.2,
        )

        models_to_try = [self.model]
        if self.model != "gemini-3.5-flash-lite":
            models_to_try.append("gemini-3.5-flash-lite")
        if "gemini-3.1-flash-lite" not in models_to_try:
            models_to_try.append("gemini-3.1-flash-lite")

        response_stream: Any = None
        for m in models_to_try:
            try:
                response_stream = self.client.models.generate_content_stream(
                    model=m,
                    contents=contents,
                    config=config,
                )
                break
            except Exception as exc:
                if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                    continue
                raise exc

        if response_stream is None:
            return

        for chunk in response_stream:
            text = chunk.text or ""
            chunk_tool_calls = None
            if chunk.function_calls:
                chunk_tool_calls = []
                for fc in chunk.function_calls:
                    chunk_tool_calls.append({
                        "function": {
                            "name": fc.name,
                            "arguments": dict(fc.args) if fc.args else {},
                        }
                    })
            yield ModelDelta(text=text, tool_calls=chunk_tool_calls)
