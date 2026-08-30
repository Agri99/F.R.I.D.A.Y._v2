"""
src/friday/online/live_data.py

WHAT THIS IS FOR:
Fetches live data feeds like weather and news using public endpoints with offline fallbacks.
"""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class WeatherData:
    temperature: float
    conditions: str
    location: str
    humidity: int | None = None
    wind_speed: float | None = None


@dataclass
class NewsItem:
    headline: str
    url: str
    source: str


class LiveDataProvider:
    """Provides access to live weather, time, and news data."""

    def __init__(self, weather_api_key: str | None = None, news_api_key: str | None = None, timeout_seconds: int = 5):
        self._weather_key = weather_api_key
        self._news_key = news_api_key
        self.timeout_seconds = timeout_seconds

    def get_weather(self, location: str = "auto") -> WeatherData | str:
        """Fetch real-time weather from wttr.in JSON service without requiring API keys."""
        loc_encoded = urllib.parse.quote_plus(location.strip()) if location and location != "auto" else ""
        url = f"https://wttr.in/{loc_encoded}?format=j1"

        try:
            headers = {"User-Agent": "FRIDAY-Agent/3.0"}
            resp = requests.get(url, headers=headers, timeout=self.timeout_seconds)
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current_condition", [{}])[0]
                temp_c = float(current.get("temp_C", 20.0))
                desc = current.get("weatherDesc", [{}])[0].get("value", "Clear")
                humidity = int(current.get("humidity", 50))
                wind = float(current.get("windspeedKmph", 0.0))

                nearest_area = data.get("nearest_area", [{}])[0]
                area_name = nearest_area.get("areaName", [{}])[0].get("value", location)

                return WeatherData(
                    temperature=temp_c,
                    conditions=desc,
                    location=area_name,
                    humidity=humidity,
                    wind_speed=wind,
                )
        except Exception as exc:
            logger.warning(f"Live weather fetch failed: {exc}")

        return f"Unable to retrieve live weather for '{location}' (service offline or unreachable)."

    def get_news(self, query: str = "technology") -> list[NewsItem] | str:
        """Fetch latest news headlines from public RSS/news sources."""
        try:
            import xml.etree.ElementTree as ET
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(query.strip())}&hl=en-US&gl=US&ceid=US:en"
            resp = requests.get(url, headers={"User-Agent": "FRIDAY-Agent/3.0"}, timeout=self.timeout_seconds)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                items: list[NewsItem] = []
                for item in root.findall(".//item")[:5]:
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    source = item.findtext("source", "Google News")
                    if title:
                        items.append(NewsItem(headline=title, url=link, source=source))
                if items:
                    return items
        except Exception as exc:
            logger.warning(f"News fetch failed: {exc}")

        return f"Unable to fetch live news headlines for '{query}'."
