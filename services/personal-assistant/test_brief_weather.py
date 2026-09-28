from __future__ import annotations

from unittest.mock import Mock

import httpx
import brief
from brief import split_location_narratives
from weather import WeatherBundle, WeatherDaySummary, WeatherSnapshot


def _snapshot(latitude: float, longitude: float, condition: str) -> WeatherSnapshot:
    return WeatherSnapshot(
        latitude=latitude,
        longitude=longitude,
        temperature_c=22.0,
        wind_speed_kmh=10.0,
        condition=condition,
        weather_code=0,
    )


def _day(date: str, condition: str, *, high: float = 26.0, low: float = 18.0) -> WeatherDaySummary:
    return WeatherDaySummary(
        date=date,
        high_c=high,
        low_c=low,
        precipitation_probability=10,
        condition=condition,
        weather_code=0,
    )


def _bundle(
    latitude: float,
    longitude: float,
    now_condition: str,
    today_condition: str,
    tomorrow_condition: str,
) -> WeatherBundle:
    return WeatherBundle(
        now=_snapshot(latitude, longitude, now_condition),
        today=_day("2026-09-27", today_condition),
        tomorrow=_day("2026-09-28", tomorrow_condition, high=24.0, low=16.0),
    )


def test_split_labeled_lines() -> None:
    text = (
        "Barcelona: Overcast, 24C with light wind.\n"
        "Sant Cugat del Vallès: Clear, 22C."
    )

    got = split_location_narratives(
        text, ["Barcelona", "Sant Cugat del Vallès"]
    )

    assert "Overcast" in got["Barcelona"]
    assert "Clear" in got["Sant Cugat del Vallès"]


def test_split_missing_label_returns_empty() -> None:
    got = split_location_narratives(
        "unrelated prose", ["Barcelona", "Sant Cugat del Vallès"]
    )

    assert got["Barcelona"] == ""
    assert got["Sant Cugat del Vallès"] == ""


def test_render_shared_weather_narrative_makes_one_generate_call(
    monkeypatch,
) -> None:
    response = Mock()
    response.json.return_value = {
        "text": "Mild and dry through tomorrow in both areas.",
        "provider": "test-provider",
        "model": "test-model",
        "usage": {"total_tokens": 42},
    }
    client = Mock()
    client.post.return_value = response
    context_manager = Mock()
    context_manager.__enter__ = Mock(return_value=client)
    context_manager.__exit__ = Mock(return_value=False)
    client_factory = Mock(return_value=context_manager)
    monkeypatch.setattr(brief.httpx, "Client", client_factory)
    locations_payload = [
        {
            "name": "Barcelona",
            "emoji": "☀️",
            "now": {"condition": "clear", "temperature_c": 22.0},
            "today": {"condition": "partly cloudy", "high_c": 26.0, "low_c": 18.0},
            "tomorrow": {"condition": "overcast", "high_c": 24.0, "low_c": 16.0},
        },
    ]

    got = brief.render_shared_weather_narrative(
        locations_payload, "http://model-router:8082/"
    )

    assert got == response.json.return_value
    client.post.assert_called_once()
    url, = client.post.call_args.args
    payload = client.post.call_args.kwargs["json"]
    assert url == "http://model-router:8082/v1/generate"
    assert "one short paragraph" in payload["prompt"]
    assert "the location's" in payload["prompt"]
    assert "both locations" not in payload["prompt"]
    assert "No bullet list" in payload["prompt"]
    assert "location-labeled lines" in payload["prompt"]
    assert str(locations_payload) in payload["prompt"]
    assert payload["max_tokens"] == 200
    response.raise_for_status.assert_called_once_with()


def test_generate_daily_brief_builds_shared_weather_narrative_with_fallback(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "WEATHER_LOCATIONS",
        "Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864",
    )
    monkeypatch.setattr(
        brief,
        "route_handler",
        Mock(return_value={"choice": "personal", "confidence": 1.0, "engine": "test"}),
    )
    bundles = [
        _bundle(41.3874, 2.1686, "clear", "partly cloudy", "overcast"),
        _bundle(41.4728, 2.0864, "overcast", "overcast", "rain"),
    ]
    fetch = Mock(side_effect=bundles)
    monkeypatch.setattr(brief, "fetch_weather_bundle", fetch)
    render = Mock(
        return_value={
            "text": "Mild and dry through tomorrow in both areas.",
            "provider": "test-provider",
            "model": "test-model",
            "usage": {"total_tokens": 42},
        }
    )
    monkeypatch.setattr(brief, "render_shared_weather_narrative", render)

    got = brief.generate_daily_brief(
        decision_url="http://decision",
        model_url="http://model",
        weather_base_url="http://weather",
    )

    weather = got["sections"]["weather"]
    assert weather["narrative"] == "Mild and dry through tomorrow in both areas."
    assert len(weather["locations"]) == 2
    barcelona = weather["locations"][0]
    sant_cugat = weather["locations"][1]
    assert barcelona["name"] == "Barcelona"
    assert barcelona["emoji"] == "☀️"
    assert barcelona["today"]["emoji"] == "⛅"
    assert barcelona["tomorrow"]["emoji"] == "☁️"
    assert "data" not in barcelona
    assert "narrative" not in barcelona
    assert barcelona["now"] == bundles[0].now.as_dict()
    assert barcelona["tomorrow"]["high_c"] == 24.0
    assert sant_cugat["name"] == "Sant Cugat del Vallès"
    assert sant_cugat["emoji"] == "☁️"
    assert sant_cugat["today"]["emoji"] == "☁️"
    assert sant_cugat["tomorrow"]["emoji"] == "🌧️"
    assert weather["model"] == {
        "provider": "test-provider",
        "model": "test-model",
        "usage": {"total_tokens": 42},
    }
    assert fetch.call_args_list[0].args == (41.3874, 2.1686)
    assert fetch.call_args_list[1].args == (41.4728, 2.0864)
    assert all(
        call.kwargs == {"base_url": "http://weather"}
        for call in fetch.call_args_list
    )
    render.assert_called_once()
    payload_arg = render.call_args.args[0]
    assert payload_arg[0]["name"] == "Barcelona"
    assert payload_arg[1]["name"] == "Sant Cugat del Vallès"
    assert render.call_args.args[1] == "http://model"


def _brief_weather_mocks(monkeypatch) -> tuple[Mock, list[WeatherBundle]]:
    monkeypatch.setenv(
        "WEATHER_LOCATIONS",
        "Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864",
    )
    monkeypatch.setattr(
        brief,
        "route_handler",
        Mock(return_value={"choice": "personal", "confidence": 1.0, "engine": "test"}),
    )
    bundles = [
        _bundle(41.3874, 2.1686, "clear", "partly cloudy", "overcast"),
        _bundle(41.4728, 2.0864, "overcast", "overcast", "rain"),
    ]
    fetch = Mock(side_effect=bundles)
    monkeypatch.setattr(brief, "fetch_weather_bundle", fetch)
    return fetch, bundles


def test_generate_daily_brief_uses_fallback_when_model_text_empty(
    monkeypatch,
) -> None:
    _brief_weather_mocks(monkeypatch)
    monkeypatch.setattr(
        brief,
        "render_shared_weather_narrative",
        Mock(
            return_value={
                "text": "   ",
                "provider": "test-provider",
                "model": "test-model",
                "usage": {"total_tokens": 1},
            }
        ),
    )

    got = brief.generate_daily_brief(
        decision_url="http://decision",
        model_url="http://model",
        weather_base_url="http://weather",
    )

    narrative = got["sections"]["weather"]["narrative"]
    assert "Barcelona:" in narrative
    assert "Sant Cugat del Vallès:" in narrative
    assert "partly cloudy" in narrative
    assert "Mild and dry" not in narrative


def test_generate_daily_brief_uses_fallback_when_generate_raises(
    monkeypatch,
) -> None:
    _brief_weather_mocks(monkeypatch)
    monkeypatch.setattr(
        brief,
        "render_shared_weather_narrative",
        Mock(side_effect=httpx.HTTPStatusError("error", request=Mock(), response=Mock())),
    )

    got = brief.generate_daily_brief(
        decision_url="http://decision",
        model_url="http://model",
        weather_base_url="http://weather",
    )

    narrative = got["sections"]["weather"]["narrative"]
    assert "Barcelona:" in narrative
    assert "rain" in narrative.lower()
    assert got["sections"]["weather"]["model"]["provider"] is None


def test_render_shared_weather_narrative_prompt_all_locations_for_two_cities(
    monkeypatch,
) -> None:
    response = Mock()
    response.json.return_value = {"text": "ok"}
    client = Mock()
    client.post.return_value = response
    context_manager = Mock()
    context_manager.__enter__ = Mock(return_value=client)
    context_manager.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(brief.httpx, "Client", Mock(return_value=context_manager))
    locations_payload = [
        {"name": "Barcelona", "emoji": "☀️", "now": {}, "today": {}, "tomorrow": {}},
        {"name": "Sant Cugat del Vallès", "emoji": "☁️", "now": {}, "today": {}, "tomorrow": {}},
    ]

    brief.render_shared_weather_narrative(locations_payload, "http://model")

    prompt = client.post.call_args.kwargs["json"]["prompt"]
    assert "all 2 locations'" in prompt
    assert "both locations" not in prompt
