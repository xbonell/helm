from __future__ import annotations

from unittest.mock import Mock

import brief
from gcal import AgendaItem, AgendaResult


def _brief_weather_mocks(monkeypatch) -> None:
    monkeypatch.setenv(
        "WEATHER_LOCATIONS",
        "Barcelona:41.3874,2.1686",
    )
    monkeypatch.setattr(
        brief,
        "route_handler",
        Mock(return_value={"choice": "personal", "confidence": 1.0, "engine": "test"}),
    )
    monkeypatch.setattr(
        brief,
        "fetch_weather_bundle",
        Mock(
            return_value=Mock(
                now=Mock(as_dict=Mock(return_value={"condition": "clear"})),
                today=Mock(as_dict=Mock(return_value={"condition": "sunny"})),
                tomorrow=Mock(as_dict=Mock(return_value={"condition": "cloudy"})),
            )
        ),
    )
    monkeypatch.setattr(
        brief,
        "render_shared_weather_narrative",
        Mock(return_value={"text": "Fine weather.", "provider": "p", "model": "m", "usage": {}}),
    )


def test_generate_daily_brief_uses_calendar_agenda(monkeypatch) -> None:
    _brief_weather_mocks(monkeypatch)
    items = [
        AgendaItem(
            date="2026-09-28",
            time="10:00",
            end_time="11:00",
            title="Standup",
            all_day=False,
            calendar="primary",
            event_id="evt-1",
        ),
        AgendaItem(
            date="2026-09-29",
            time="all-day",
            end_time=None,
            title="Holiday",
            all_day=True,
            calendar="primary",
            event_id="evt-2",
        ),
    ]
    monkeypatch.setattr(
        brief,
        "fetch_agenda",
        Mock(return_value=AgendaResult(items=items, status="ok")),
    )

    got = brief.generate_daily_brief(
        decision_url="http://decision",
        model_url="http://model",
        weather_base_url="http://weather",
    )

    sections = got["sections"]
    assert sections["agenda"] == [item.as_dict() for item in items]
    assert sections["agenda_status"] == "ok"
    assert "agenda_error" not in sections
    assert sections["priorities"] == brief.mock_context()["priorities"]
    assert sections["fitness"] == brief.mock_context()["fitness"]
    assert sections["news"] == brief.mock_context()["news"]
    mock_titles = {e["title"] for e in brief.mock_context()["agenda"]}
    assert not any(e.get("title") in mock_titles for e in sections["agenda"])
    for entry in sections["agenda"]:
        assert "event_id" not in entry


def test_generate_daily_brief_calendar_unconfigured(monkeypatch) -> None:
    _brief_weather_mocks(monkeypatch)
    monkeypatch.setattr(
        brief,
        "fetch_agenda",
        Mock(return_value=AgendaResult(items=[], status="unconfigured")),
    )

    got = brief.generate_daily_brief(
        decision_url="http://decision",
        model_url="http://model",
        weather_base_url="http://weather",
    )

    sections = got["sections"]
    assert sections["agenda"] == []
    assert sections["agenda_status"] == "unconfigured"
    assert "agenda_error" not in sections


def test_generate_daily_brief_calendar_error(monkeypatch) -> None:
    _brief_weather_mocks(monkeypatch)
    monkeypatch.setattr(
        brief,
        "fetch_agenda",
        Mock(
            return_value=AgendaResult(
                items=[],
                status="error",
                error="token failed",
            )
        ),
    )

    got = brief.generate_daily_brief(
        decision_url="http://decision",
        model_url="http://model",
        weather_base_url="http://weather",
    )

    sections = got["sections"]
    assert sections["agenda"] == []
    assert sections["agenda_status"] == "error"
    assert sections["agenda_error"] == "token failed"
