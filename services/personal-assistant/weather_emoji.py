from __future__ import annotations

_EMOJI = {
    "clear": "☀️",
    "mainly clear": "🌤️",
    "partly cloudy": "⛅",
    "overcast": "☁️",
    "fog": "🌫️",
    "depositing rime fog": "🌫️",
    "light drizzle": "🌦️",
    "light rain": "🌧️",
    "rain": "🌧️",
    "heavy rain": "🌧️",
    "light snow": "🌨️",
    "rain showers": "🌧️",
    "thunderstorm": "⛈️",
}


def emoji_for_condition(condition: str) -> str:
    key = (condition or "").strip().lower()
    return _EMOJI.get(key, "🌤️")
