from __future__ import annotations

from unittest.mock import Mock

import brief
from brief import split_location_narratives
from weather import WeatherSnapshot


def _snapshot(latitude: float, longitude: float, condition: str) -> WeatherSnapshot:
    return WeatherSnapshot(
        latitude=latitude,
        longitude=longitude,
        temperature_c=22.0,
        wind_speed_kmh=10.0,
        condition=condition,
        weather_code=0,
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


def test_render_multi_weather_narratives_makes_one_generate_call(
    monkeypatch,
) -> None:
    response = Mock()
    response.json.return_value = {
        "text": "Barcelona: Clear.\nSant Cugat del Vallès: Overcast.",
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
    named = [
        ("Barcelona", _snapshot(41.3874, 2.1686, "clear")),
        ("Sant Cugat del Vallès", _snapshot(41.4728, 2.0864, "overcast")),
    ]

    got = brief.render_multi_weather_narratives(
        named, "http://model-router:8082/"
    )

    assert got == response.json.return_value
    client.post.assert_called_once()
    url, = client.post.call_args.args
    payload = client.post.call_args.kwargs["json"]
    assert url == "http://model-router:8082/v1/generate"
    assert (
        "Location names in order: Barcelona, Sant Cugat del Vallès."
        in payload["prompt"]
    )
    assert payload["max_tokens"] == 200
    response.raise_for_status.assert_called_once_with()


def test_generate_daily_brief_builds_multi_location_weather_with_fallback(
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
    snapshots = [
        _snapshot(41.3874, 2.1686, "clear"),
        _snapshot(41.4728, 2.0864, "overcast"),
    ]
    fetch = Mock(side_effect=snapshots)
    monkeypatch.setattr(brief, "fetch_weather", fetch)
    render = Mock(
        return_value={
            "text": "Barcelona: Sunny and mild.",
            "provider": "test-provider",
            "model": "test-model",
            "usage": {"total_tokens": 42},
        }
    )
    monkeypatch.setattr(brief, "render_multi_weather_narratives", render)

    got = brief.generate_daily_brief(
        decision_url="http://decision",
        model_url="http://model",
        weather_base_url="http://weather",
    )

    weather = got["sections"]["weather"]
    assert weather["locations"] == [
        {
            "name": "Barcelona",
            "data": snapshots[0].as_dict(),
            "narrative": "Sunny and mild.",
        },
        {
            "name": "Sant Cugat del Vallès",
            "data": snapshots[1].as_dict(),
            "narrative": "overcast, 22.0°C, wind 10.0 km/h.",
        },
    ]
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
    render.assert_called_once_with(
        [
            ("Barcelona", snapshots[0]),
            ("Sant Cugat del Vallès", snapshots[1]),
        ],
        "http://model",
    )
