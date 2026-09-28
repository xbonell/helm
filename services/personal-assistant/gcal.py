"""Google Calendar agenda fetch — OAuth refresh + REST (httpx)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

BRIEF_TZ = ZoneInfo("Europe/Madrid")
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"

AgendaStatus = Literal["ok", "unconfigured", "error"]


@dataclass
class AgendaItem:
    date: str
    time: str
    end_time: str | None
    title: str
    all_day: bool
    calendar: str
    event_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "time": self.time,
            "end_time": self.end_time,
            "title": self.title,
            "all_day": self.all_day,
            "calendar": self.calendar,
        }


@dataclass
class AgendaResult:
    items: list[AgendaItem]
    status: AgendaStatus
    error: str | None = None


def madrid_window(now: datetime) -> tuple[datetime, datetime]:
    """[start of today, start of day-after-tomorrow) in Madrid."""
    local = now.astimezone(BRIEF_TZ)
    start = datetime.combine(local.date(), time.min, tzinfo=BRIEF_TZ)
    end = start + timedelta(days=2)
    return start, end


def _parse_rfc3339(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _event_in_window(
    *,
    all_day: bool,
    start: datetime | date,
    end: datetime | date,
    window: tuple[datetime, datetime],
) -> bool:
    win_start, win_end = window
    if all_day:
        assert isinstance(start, date) and isinstance(end, date)
        event_start = datetime.combine(start, time.min, tzinfo=BRIEF_TZ)
        event_end = datetime.combine(end, time.min, tzinfo=BRIEF_TZ)
    else:
        assert isinstance(start, datetime) and isinstance(end, datetime)
        event_start = start.astimezone(BRIEF_TZ)
        event_end = end.astimezone(BRIEF_TZ)
    return event_start < win_end and event_end > win_start


def normalize_events(
    raw_items: list[dict],
    *,
    calendar_id: str,
    window: tuple[datetime, datetime],
) -> list[AgendaItem]:
    window_start_date = window[0].date()
    items: list[AgendaItem] = []
    for raw in raw_items:
        try:
            event_id = str(raw.get("id", ""))
            title = str(raw.get("summary") or "(no title)")
            start_raw = raw.get("start") or {}
            end_raw = raw.get("end") or {}

            if "date" in start_raw:
                start_date = date.fromisoformat(start_raw["date"])
                end_date = date.fromisoformat(end_raw.get("date", start_raw["date"]))
                if not _event_in_window(
                    all_day=True,
                    start=start_date,
                    end=end_date,
                    window=window,
                ):
                    continue
                reported = max(start_date, window_start_date)
                items.append(
                    AgendaItem(
                        date=reported.isoformat(),
                        time="all-day",
                        end_time=None,
                        title=title,
                        all_day=True,
                        calendar=calendar_id,
                        event_id=event_id,
                    )
                )
                continue

            start_dt = _parse_rfc3339(start_raw["dateTime"])
            end_dt = _parse_rfc3339(end_raw["dateTime"])
            if not _event_in_window(
                all_day=False,
                start=start_dt,
                end=end_dt,
                window=window,
            ):
                continue
            start_local = start_dt.astimezone(BRIEF_TZ)
            end_local = end_dt.astimezone(BRIEF_TZ)
            reported = max(start_local.date(), window_start_date)
            items.append(
                AgendaItem(
                    date=reported.isoformat(),
                    time=start_local.strftime("%H:%M"),
                    end_time=end_local.strftime("%H:%M"),
                    title=title,
                    all_day=False,
                    calendar=calendar_id,
                    event_id=event_id,
                )
            )
        except (KeyError, ValueError):
            continue
    return items


def _sort_key(item: AgendaItem) -> tuple[str, int, str]:
    day_order = 0 if item.all_day else 1
    time_key = "" if item.all_day else item.time
    return (item.date, day_order, time_key)


def _merge_and_sort(items: list[AgendaItem]) -> list[AgendaItem]:
    seen: set[str] = set()
    deduped: list[AgendaItem] = []
    for item in items:
        if item.event_id and item.event_id in seen:
            continue
        if item.event_id:
            seen.add(item.event_id)
        deduped.append(item)
    return sorted(deduped, key=_sort_key)


def _calendar_ids() -> list[str]:
    raw = os.environ.get("GOOGLE_CALENDAR_IDS", "").strip()
    if raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return ["primary"]


def _oauth_configured() -> bool:
    return all(
        os.environ.get(key, "").strip()
        for key in (
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_REFRESH_TOKEN",
        )
    )


def _rfc3339_offset(dt: datetime) -> str:
    local = dt.astimezone(BRIEF_TZ)
    return local.isoformat(timespec="seconds")


def _fetch_access_token(client: httpx.Client) -> str:
    response = client.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
        },
    )
    response.raise_for_status()
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise ValueError("token response is not valid JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("token response is not a JSON object")
    token = body.get("access_token")
    if not token:
        raise httpx.HTTPStatusError(
            "token response missing access_token",
            request=response.request,
            response=response,
        )
    return str(token)


def _fetch_calendar_events(
    client: httpx.Client,
    *,
    calendar_id: str,
    access_token: str,
    window: tuple[datetime, datetime],
) -> list[dict]:
    encoded_id = quote(calendar_id, safe="@")
    url = EVENTS_URL.format(calendar_id=encoded_id)
    time_min, time_max = window
    response = client.get(
        url,
        params={
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": _rfc3339_offset(time_min),
            "timeMax": _rfc3339_offset(time_max),
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise ValueError("events response is not valid JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("events response is not a JSON object")
    items = body.get("items")
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("events response items is not a list")
    return list(items)


def fetch_agenda(
    *,
    now: datetime | None = None,
    client: httpx.Client | None = None,
) -> AgendaResult:
    if not _oauth_configured():
        return AgendaResult(items=[], status="unconfigured")

    moment = now or datetime.now(tz=BRIEF_TZ)
    window = madrid_window(moment)
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        access_token = _fetch_access_token(client)
        all_items: list[AgendaItem] = []
        for calendar_id in _calendar_ids():
            raw = _fetch_calendar_events(
                client,
                calendar_id=calendar_id,
                access_token=access_token,
                window=window,
            )
            all_items.extend(
                normalize_events(raw, calendar_id=calendar_id, window=window)
            )
        return AgendaResult(items=_merge_and_sort(all_items), status="ok")
    except httpx.HTTPError as exc:
        message = "calendar request failed"
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            message = f"calendar HTTP {exc.response.status_code}"
        return AgendaResult(items=[], status="error", error=message)
    except (ValueError, AttributeError, json.JSONDecodeError):
        return AgendaResult(
            items=[], status="error", error="calendar response parse failed"
        )
    finally:
        if owns:
            client.close()
