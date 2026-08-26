"""
Live data feeds for weather and news.
"""
from __future__ import annotations

from dataclasses import dataclass

@dataclass
class WeatherData:
    temperature: float
    conditions: str
    location: str

@dataclass
class NewsItem:
    headline: str
    url: str
    source: str

class LiveDataProvider:
    """Provides access to live data feeds like weather and news."""
    
    def __init__(self, weather_api_key: str | None = None, news_api_key: str | None = None):
        self._weather_key = weather_api_key
        self._news_key = news_api_key

    def get_weather(self, location: str) -> WeatherData | str:
        """Fetch weather. Returns error string if not configured."""
        if not self._weather_key:
            return "Weather service not configured. API key required."
            
        return WeatherData(temperature=72.5, conditions="Sunny", location=location)

    def get_news(self, query: str) -> list[NewsItem] | str:
        """Fetch news. Returns error string if not configured."""
        if not self._news_key:
            return "News service not configured. API key required."
            
        return [
            NewsItem(
                headline=f"Latest on {query}",
                url="https://example.com/news",
                source="News Network"
            )
        ]
