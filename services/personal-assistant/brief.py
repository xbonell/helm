"""Personal assistant — generate-daily-brief orchestration."""

from __future__ import annotations

from datetime import date
from typing import Any
import os

import httpx

from locations import parse_weather_locations
from weather import WeatherSnapshot, fetch_weather
from weather_emoji import emoji_for_condition


def mock_context() -> dict[str, Any]:
    """Mocked agenda / fitness / priorities / news for MVP orchestration."""
    return {
        "agenda": [
            {"time": "09:30", "title": "Focus block — platform work"},
            {"time": "14:00", "title": "Review open PRs"},
            {"time": "17:30", "title": "Walk / reset"},
        ],
        "priorities": [
            "Ship Helm MVP daily-brief command",
            "Keep AI cost near zero during development",
            "Document persistence and restore",
        ],
        "fitness": {
            "plan": "Zone-2 walk 30–40 min",
            "sleep_hours": 7.2,
            "readiness": "good",
        },
        "news": [
            {"title": "(mock) Local tech meetup this week", "source": "mock"},
            {"title": "(mock) Weather outlook: mild and dry", "source": "mock"},
        ],
    }


def route_handler(context: str, decision_url: str, timeout: float = 120.0) -> dict[str, Any]:
    payload = {
        "context": context,
        "candidates": ["personal", "finance", "development", "legal"],
        "criteria": {
            "personal": "Personal assistant, daily brief, weather, calendar, lifestyle",
            "finance": "Money, budgets, invoices, investments",
            "development": "Software, code, repositories, engineering",
            "legal": "Contracts, compliance, legal advice",
        },
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{decision_url.rstrip('/')}/v1/decide", json=payload)
        response.raise_for_status()
        return response.json()


def split_location_narratives(text: str, names: list[str]) -> dict[str, str]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    narratives = {name: "" for name in names}
    for name in names:
        for line in lines:
            for prefix in (f"{name}:", f"{name} -", f"{name} –"):
                if line.startswith(prefix):
                    narratives[name] = line[len(prefix):].strip()
                    break
            if narratives[name]:
                break
    return narratives


def _template_narrative(weather: WeatherSnapshot) -> str:
    return (
        f"{weather.condition}, {weather.temperature_c}°C, "
        f"wind {weather.wind_speed_kmh} km/h."
    )


def render_multi_weather_narratives(
    named: list[tuple[str, WeatherSnapshot]],
    model_url: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    payload_lines = []
    for name, snapshot in named:
        payload_lines.append(f"{name}: {snapshot.as_dict()}")
    names = [name for name, _ in named]
    name_list = ", ".join(names)
    prompt = (
        "Write exactly one short briefing sentence per location from this weather data. "
        f"Output exactly {len(names)} lines, each starting with the location name "
        f"followed by a colon. Location names in order: {name_list}. No preamble.\n"
        + "\n".join(payload_lines)
    )
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{model_url.rstrip('/')}/v1/generate",
            json={
                "system": "You write concise personal daily brief weather lines.",
                "prompt": prompt,
                "max_tokens": 200,
                "temperature": 0.2,
            },
        )
        response.raise_for_status()
        return response.json()


def generate_daily_brief(
    *,
    decision_url: str | None = None,
    model_url: str | None = None,
    weather_base_url: str | None = None,
) -> dict[str, Any]:
    decision_url = decision_url or os.environ.get("DECISION_GATEWAY_URL", "http://decision-gateway:8081")
    model_url = model_url or os.environ.get("MODEL_ROUTER_URL", "http://model-router:8082")
    weather_base_url = weather_base_url or os.environ.get(
        "WEATHER_BASE_URL", "https://api.open-meteo.com"
    )

    today = date.today().isoformat()
    decision = route_handler(f"generate-daily-brief for {today}", decision_url)
    raw_locations = os.environ.get(
        "WEATHER_LOCATIONS",
        "Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864",
    )
    locations = parse_weather_locations(raw_locations)
    snapshots = [
        fetch_weather(
            location.latitude,
            location.longitude,
            base_url=weather_base_url,
        )
        for location in locations
    ]
    named_snapshots = [
        (location.name, snapshot)
        for location, snapshot in zip(locations, snapshots)
    ]
    weather_gen = render_multi_weather_narratives(named_snapshots, model_url)
    narratives = split_location_narratives(
        weather_gen.get("text") or "",
        [location.name for location in locations],
    )
    mocked = mock_context()

    brief = {
        "command": "generate-daily-brief",
        "date": today,
        "routing": {
            "choice": decision.get("choice"),
            "confidence": decision.get("confidence"),
            "engine": decision.get("engine"),
        },
        "sections": {
            "weather": {
                "locations": [
                    {
                        "name": location.name,
                        "data": snapshot.as_dict(),
                        "emoji": emoji_for_condition(snapshot.condition),
                        "narrative": narratives[location.name]
                        or _template_narrative(snapshot),
                    }
                    for location, snapshot in zip(locations, snapshots)
                ],
                "model": {
                    "provider": weather_gen.get("provider"),
                    "model": weather_gen.get("model"),
                    "usage": weather_gen.get("usage"),
                },
            },
            "agenda": mocked["agenda"],
            "priorities": mocked["priorities"],
            "fitness": mocked["fitness"],
            "news": mocked["news"],
        },
    }
    return brief
