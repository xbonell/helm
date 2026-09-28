"""Personal assistant — generate-daily-brief orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
import os

import httpx

from locations import parse_weather_locations
from weather import WeatherBundle, fetch_weather_bundle
from weather_emoji import emoji_for_condition

BRIEF_TZ = ZoneInfo("Europe/Madrid")


def brief_local_date(*, now: datetime | None = None) -> str:
    """Calendar date for the brief in Europe/Madrid (matches weather day boundaries)."""
    current = now if now is not None else datetime.now(BRIEF_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BRIEF_TZ)
    else:
        current = current.astimezone(BRIEF_TZ)
    return current.date().isoformat()


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


def _location_payload(name: str, bundle: WeatherBundle) -> dict[str, Any]:
    return {
        "name": name,
        "emoji": emoji_for_condition(bundle.now.condition),
        "now": {**bundle.now.as_dict()},
        "today": {
            **bundle.today.as_dict(),
            "emoji": emoji_for_condition(bundle.today.condition),
        },
        "tomorrow": {
            **bundle.tomorrow.as_dict(),
            "emoji": emoji_for_condition(bundle.tomorrow.condition),
        },
    }


def _fallback_shared_narrative(locations_payload: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for loc in locations_payload:
        now = loc["now"]
        today = loc["today"]
        tomorrow = loc["tomorrow"]
        parts.append(
            f"{loc['name']}: {now['condition']}, {now['temperature_c']}°C now; "
            f"today {today['condition']} {today['low_c']}–{today['high_c']}°C; "
            f"tomorrow {tomorrow['condition']} {tomorrow['low_c']}–{tomorrow['high_c']}°C."
        )
    return " ".join(parts)


def render_shared_weather_narrative(
    locations_payload: list[dict[str, Any]],
    model_url: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    count = len(locations_payload)
    if count == 1:
        locations_phrase = "the location's"
    else:
        locations_phrase = f"all {count} locations'"
    prompt = (
        "Write one short paragraph (2–4 sentences) for a morning personal brief. "
        f"Cover {locations_phrase} current conditions, the rest of today, and tomorrow. "
        "No bullet list, no preamble, no location-labeled lines.\n"
        f"{locations_payload}"
    )
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{model_url.rstrip('/')}/v1/generate",
            json={
                "system": "You write concise personal daily brief weather summaries.",
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

    today = brief_local_date()
    decision = route_handler(f"generate-daily-brief for {today}", decision_url)
    raw_locations = os.environ.get(
        "WEATHER_LOCATIONS",
        "Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864",
    )
    locations = parse_weather_locations(raw_locations)
    bundles = [
        fetch_weather_bundle(
            location.latitude,
            location.longitude,
            base_url=weather_base_url,
        )
        for location in locations
    ]
    locations_payload = [
        _location_payload(location.name, bundle)
        for location, bundle in zip(locations, bundles)
    ]
    try:
        weather_gen = render_shared_weather_narrative(locations_payload, model_url)
    except httpx.HTTPError:
        weather_gen = {}
    except ValueError:
        weather_gen = {}
    narrative = (weather_gen.get("text") or "").strip()
    if not narrative:
        narrative = _fallback_shared_narrative(locations_payload)
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
                "locations": locations_payload,
                "narrative": narrative,
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
