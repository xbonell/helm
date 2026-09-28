from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import gcal as calendar_mod
import httpx
import pytest

AgendaItem = calendar_mod.AgendaItem
madrid_window = calendar_mod.madrid_window
normalize_events = calendar_mod.normalize_events
merge_and_sort = calendar_mod._merge_and_sort

BRIEF_TZ = ZoneInfo("Europe/Madrid")
FROZEN_NOW = datetime(2026, 9, 28, 10, 0, tzinfo=BRIEF_TZ)

CALENDAR_EVENTS_FIXTURE: list[dict] = [
    {
        "id": "timed-today",
        "summary": "Morning standup",
        "start": {"dateTime": "2026-09-28T09:30:00+02:00"},
        "end": {"dateTime": "2026-09-28T10:00:00+02:00"},
    },
    {
        "id": "all-day-tomorrow",
        "summary": "Public holiday",
        "start": {"date": "2026-09-29"},
        "end": {"date": "2026-09-30"},
    },
    {
        "id": "day-after",
        "summary": "Too far out",
        "start": {"dateTime": "2026-09-30T14:00:00+02:00"},
        "end": {"dateTime": "2026-09-30T15:00:00+02:00"},
    },
]


def _window() -> tuple[datetime, datetime]:
    return madrid_window(FROZEN_NOW)


def test_timed_event_normalized_to_madrid_hhmm() -> None:
    items = normalize_events(
        [CALENDAR_EVENTS_FIXTURE[0]],
        calendar_id="primary",
        window=_window(),
    )
    assert len(items) == 1
    item = items[0]
    assert item.date == "2026-09-28"
    assert item.time == "09:30"
    assert item.end_time == "10:00"
    assert item.all_day is False
    assert item.title == "Morning standup"
    assert item.calendar == "primary"


def test_all_day_event_uses_all_day_time() -> None:
    items = normalize_events(
        [CALENDAR_EVENTS_FIXTURE[1]],
        calendar_id="primary",
        window=_window(),
    )
    assert len(items) == 1
    item = items[0]
    assert item.date == "2026-09-29"
    assert item.time == "all-day"
    assert item.end_time is None
    assert item.all_day is True


def test_same_day_all_day_sorts_before_timed() -> None:
    timed = {
        "id": "timed-same-day",
        "summary": "Afternoon meeting",
        "start": {"dateTime": "2026-09-28T14:00:00+02:00"},
        "end": {"dateTime": "2026-09-28T15:00:00+02:00"},
    }
    all_day = {
        "id": "all-day-same-day",
        "summary": "Blocked day",
        "start": {"date": "2026-09-28"},
        "end": {"date": "2026-09-29"},
    }
    window = _window()
    items = merge_and_sort(
        normalize_events([timed, all_day], calendar_id="primary", window=window)
    )
    assert len(items) == 2
    assert items[0].all_day is True
    assert items[0].title == "Blocked day"
    assert items[1].all_day is False
    assert items[1].title == "Afternoon meeting"


def test_normalize_skips_malformed_events() -> None:
    bad = {"id": "bad", "summary": "Broken", "start": {"dateTime": "not-a-date"}}
    good = CALENDAR_EVENTS_FIXTURE[0]
    items = normalize_events(
        [bad, good],
        calendar_id="primary",
        window=_window(),
    )
    assert len(items) == 1
    assert items[0].title == "Morning standup"


def test_multi_day_all_day_clamps_date_to_window_start() -> None:
    """Event started before today but still overlaps today+tomorrow window."""
    long_all_day = {
        "id": "vacation-span",
        "summary": "Vacation",
        "start": {"date": "2026-09-25"},
        "end": {"date": "2026-10-02"},
    }
    items = normalize_events(
        [long_all_day],
        calendar_id="primary",
        window=_window(),
    )
    assert len(items) == 1
    assert items[0].date == "2026-09-28"
    assert items[0].time == "all-day"


def test_fetch_agenda_invalid_token_json_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "refresh-token")

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, content=b"not-json", request=request)
        raise AssertionError(f"unexpected request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = calendar_mod.fetch_agenda(now=FROZEN_NOW, client=client)

    assert result.status == "error"
    assert result.items == []
    assert result.error == "calendar response parse failed"


def test_window_drops_day_after_tomorrow() -> None:
    items = normalize_events(
        CALENDAR_EVENTS_FIXTURE,
        calendar_id="primary",
        window=_window(),
    )
    ids = {i.event_id for i in items}
    assert "day-after" not in ids
    assert len(items) == 2


def test_merge_calendars_dedupes_by_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared = {
        "id": "shared-id",
        "summary": "Duplicate",
        "start": {"dateTime": "2026-09-28T11:00:00+02:00"},
        "end": {"dateTime": "2026-09-28T12:00:00+02:00"},
    }
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv(
        "GOOGLE_CALENDAR_IDS", "primary,work@group.calendar.google.com"
    )

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                200,
                json={"access_token": "access-token", "expires_in": 3600},
                request=request,
            )
        if "calendars/primary" in str(request.url):
            return httpx.Response(200, json={"items": [shared]}, request=request)
        if "calendars/work" in str(request.url):
            return httpx.Response(200, json={"items": [shared]}, request=request)
        raise AssertionError(f"unexpected request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = calendar_mod.fetch_agenda(now=FROZEN_NOW, client=client)

    assert result.status == "ok"
    dupes = [i for i in result.items if i.event_id == "shared-id"]
    assert len(dupes) == 1
    assert dupes[0].calendar == "primary"


def test_agenda_item_as_dict_omits_event_id() -> None:
    item = AgendaItem(
        date="2026-09-28",
        time="09:30",
        end_time="10:00",
        title="Focus",
        all_day=False,
        calendar="primary",
        event_id="secret-internal-id",
    )
    d = item.as_dict()
    assert set(d.keys()) == {
        "date",
        "time",
        "end_time",
        "title",
        "all_day",
        "calendar",
    }
    assert "event_id" not in d


def test_fetch_agenda_missing_env_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)
    result = calendar_mod.fetch_agenda(now=FROZEN_NOW)
    assert result.status == "unconfigured"
    assert result.items == []
    assert result.error is None


def test_fetch_agenda_token_401_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "refresh-token")

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(401, json={"error": "invalid_grant"}, request=request)
        raise AssertionError(f"unexpected request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = calendar_mod.fetch_agenda(now=FROZEN_NOW, client=client)

    assert result.status == "error"
    assert result.items == []
    assert result.error


def test_fetch_agenda_success_merges_calendars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("GOOGLE_CALENDAR_IDS", "primary,extra@group.calendar.google.com")

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                200,
                json={"access_token": "access-token", "expires_in": 3600},
                request=request,
            )
        if "calendars/primary" in str(request.url):
            return httpx.Response(
                200,
                json={"items": [CALENDAR_EVENTS_FIXTURE[0]]},
                request=request,
            )
        if "calendars/extra" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "extra-event",
                            "summary": "Extra cal",
                            "start": {"dateTime": "2026-09-29T15:00:00+02:00"},
                            "end": {"dateTime": "2026-09-29T16:00:00+02:00"},
                        }
                    ]
                },
                request=request,
            )
        raise AssertionError(f"unexpected request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = calendar_mod.fetch_agenda(now=FROZEN_NOW, client=client)

    assert result.status == "ok"
    assert result.error is None
    assert len(result.items) == 2
    titles = [i.title for i in result.items]
    assert "Morning standup" in titles
    assert "Extra cal" in titles
