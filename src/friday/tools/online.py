from __future__ import annotations

from typing import Any

from .registry import Tool
from .metadata import build_schema
from friday.online.live_data import LiveDataProvider
from friday.online.search import WebSearchProvider


provider = LiveDataProvider()


def _get_weather(location: str = "auto") -> dict[str, Any]:
    res = provider.get_weather(location)
    if isinstance(res, str):
        return {"status": "error", "message": res}
    return {
        "status": "ok",
        "location": res.location,
        "temperature_c": res.temperature,
        "conditions": res.conditions,
        "humidity": res.humidity,
        "wind_speed_kmh": res.wind_speed,
    }


def _search(query: str, max_results: int = 3) -> dict[str, Any]:
    res = scraper.search(query, max_results)
    if isinstance(res, str):
        return {"status": "error", "message": res}
    return {"status": "ok", "results": [r.__dict__ for r in res]}


# Global fallback for tests/external callers without settings
scraper = WebSearchProvider()


def register_all_tools(registry, settings=None) -> None:
    search_cfg = getattr(settings, "search", None) if settings is not None else None
    global scraper
    scraper = WebSearchProvider(
        base_url=getattr(search_cfg, "base_url", "http://127.0.0.1:8088"),
        timeout_seconds=getattr(search_cfg, "timeout_seconds", 6.0),
        language=getattr(search_cfg, "language", "en"),
        safe_search=getattr(search_cfg, "safe_search", 1),
        specialized_fallbacks=getattr(search_cfg, "specialized_fallbacks", True),
    )

    registry.register(Tool(
        name="online.weather",
        description="Get live weather conditions for a location.",
        tier="GREEN",
        capability_scope="online.read",
        input_schema=build_schema({"location": {"type": "string"}}, ["location"]),
        handler=_get_weather,
    ))
    registry.register(Tool(
        name="online.search",
        description="Search the web through FRIDAY's local SearXNG service, with Wikipedia and Google News as specialized fallbacks.",
        tier="GREEN",
        capability_scope="online.read",
        input_schema=build_schema({"query": {"type": "string"}, "max_results": {"type": "integer"}}, ["query"]),
        handler=_search,
    ))