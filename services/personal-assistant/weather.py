"""Open-Meteo weather tool — free, no API key."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

# WMO weather interpretation codes (subset).
_WMO = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    80: "rain showers",
    95: "thunderstorm",
}


@dataclass(frozen=True)
class WeatherSnapshot:
    latitude: float
    longitude: float
    temperature_c: float
    wind_speed_kmh: float
    condition: str
    weather_code: int
    source: str = "open-meteo"

    def as_dict(self) -> dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "temperature_c": self.temperature_c,
            "wind_speed_kmh": self.wind_speed_kmh,
            "condition": self.condition,
            "weather_code": self.weather_code,
            "source": self.source,
        }


def fetch_weather(
    latitude: float,
    longitude: float,
    *,
    base_url: str = "https://api.open-meteo.com",
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> WeatherSnapshot:
    url = f"{base_url.rstrip('/')}/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "wind_speed_unit": "kmh",
        "timezone": "auto",
    }
    owns = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        body = response.json()
    finally:
        if owns:
            client.close()

    current = body["current"]
    code = int(current["weather_code"])
    return WeatherSnapshot(
        latitude=float(body.get("latitude", latitude)),
        longitude=float(body.get("longitude", longitude)),
        temperature_c=float(current["temperature_2m"]),
        wind_speed_kmh=float(current["wind_speed_10m"]),
        condition=_WMO.get(code, f"code-{code}"),
        weather_code=code,
    )
