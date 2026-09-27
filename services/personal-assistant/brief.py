"""Personal assistant — generate-daily-brief orchestration."""

from __future__ import annotations

from datetime import date
from typing import Any
import os

import httpx

from weather import WeatherSnapshot, fetch_weather


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


def render_weather_section(weather: WeatherSnapshot, model_url: str, timeout: float = 120.0) -> dict[str, Any]:
    prompt = (
        "Write one short briefing sentence from this structured weather data. "
        "No preamble.\n"
        f"{weather.as_dict()}"
    )
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{model_url.rstrip('/')}/v1/generate",
            json={
                "system": "You write concise personal daily brief weather lines.",
                "prompt": prompt,
                "max_tokens": 120,
                "temperature": 0.2,
            },
        )
        response.raise_for_status()
        return response.json()


def generate_daily_brief(
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    decision_url: str | None = None,
    model_url: str | None = None,
    weather_base_url: str | None = None,
) -> dict[str, Any]:
    latitude = latitude if latitude is not None else float(os.environ.get("WEATHER_LATITUDE", "41.3874"))
    longitude = longitude if longitude is not None else float(os.environ.get("WEATHER_LONGITUDE", "2.1686"))
    decision_url = decision_url or os.environ.get("DECISION_GATEWAY_URL", "http://decision-gateway:8081")
    model_url = model_url or os.environ.get("MODEL_ROUTER_URL", "http://model-router:8082")
    weather_base_url = weather_base_url or os.environ.get(
        "WEATHER_BASE_URL", "https://api.open-meteo.com"
    )

    today = date.today().isoformat()
    decision = route_handler(f"generate-daily-brief for {today}", decision_url)
    weather = fetch_weather(latitude, longitude, base_url=weather_base_url)
    weather_gen = render_weather_section(weather, model_url)
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
                "data": weather.as_dict(),
                "narrative": weather_gen.get("text"),
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
