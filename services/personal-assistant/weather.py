"""Open-Meteo weather tool — free, no API key."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
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


@dataclass(frozen=True)
class WeatherDaySummary:
    date: str
    high_c: float
    low_c: float
    precipitation_probability: int
    condition: str
    weather_code: int
    source: str = "open-meteo"

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "high_c": self.high_c,
            "low_c": self.low_c,
            "precipitation_probability": self.precipitation_probability,
            "condition": self.condition,
            "weather_code": self.weather_code,
            "source": self.source,
        }


@dataclass(frozen=True)
class WeatherBundle:
    now: WeatherSnapshot
    today: WeatherDaySummary
    tomorrow: WeatherDaySummary

    def as_dict(self) -> dict[str, Any]:
        return {
            "now": self.now.as_dict(),
            "today": self.today.as_dict(),
            "tomorrow": self.tomorrow.as_dict(),
        }


def _condition(code: int) -> str:
    return _WMO.get(code, f"code-{code}")


def _daily_summary(daily: dict[str, list[Any]], date: str) -> WeatherDaySummary:
    try:
        index = daily["time"].index(date)
    except ValueError as exc:
        raise ValueError(f"Open-Meteo response has no daily forecast for {date}") from exc

    code = int(daily["weather_code"][index])
    return WeatherDaySummary(
        date=date,
        high_c=float(daily["temperature_2m_max"][index]),
        low_c=float(daily["temperature_2m_min"][index]),
        precipitation_probability=int(
            daily["precipitation_probability_max"][index]
        ),
        condition=_condition(code),
        weather_code=code,
    )


def fetch_weather_bundle(
    latitude: float,
    longitude: float,
    *,
    base_url: str = "https://api.open-meteo.com",
    tz: str = "Europe/Madrid",
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> WeatherBundle:
    url = f"{base_url.rstrip('/')}/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,weather_code,precipitation_probability",
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max"
        ),
        "wind_speed_unit": "kmh",
        "timezone": tz,
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
    current_time = datetime.fromisoformat(current["time"])
    today_date = current_time.date().isoformat()
    tomorrow_date = (current_time.date() + timedelta(days=1)).isoformat()
    now_code = int(current["weather_code"])
    now = WeatherSnapshot(
        latitude=float(body.get("latitude", latitude)),
        longitude=float(body.get("longitude", longitude)),
        temperature_c=float(current["temperature_2m"]),
        wind_speed_kmh=float(current["wind_speed_10m"]),
        condition=_condition(now_code),
        weather_code=now_code,
    )

    hourly = body["hourly"]
    remaining_today = [
        (float(temperature), int(code), int(precipitation))
        for time, temperature, code, precipitation in zip(
            hourly["time"],
            hourly["temperature_2m"],
            hourly["weather_code"],
            hourly["precipitation_probability"],
        )
        if (hour_time := datetime.fromisoformat(time)).date() == current_time.date()
        and hour_time >= current_time
    ]
    if remaining_today:
        temperatures = [row[0] for row in remaining_today]
        codes = [row[1] for row in remaining_today]
        today_code = Counter(codes).most_common(1)[0][0]
        today = WeatherDaySummary(
            date=today_date,
            high_c=max(temperatures),
            low_c=min(temperatures),
            precipitation_probability=max(row[2] for row in remaining_today),
            condition=_condition(today_code),
            weather_code=today_code,
        )
    else:
        today = _daily_summary(body["daily"], today_date)

    return WeatherBundle(
        now=now,
        today=today,
        tomorrow=_daily_summary(body["daily"], tomorrow_date),
    )


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
        condition=_condition(code),
        weather_code=code,
    )
