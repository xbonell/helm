import httpx

import weather
from weather import WeatherSnapshot


FORECAST = {
    "latitude": 41.4,
    "longitude": 2.17,
    "current": {
        "time": "2026-09-27T15:30",
        "temperature_2m": 21.5,
        "weather_code": 2,
        "wind_speed_10m": 12.0,
    },
    "hourly": {
        "time": [
            "2026-09-27T14:00",
            "2026-09-27T16:00",
            "2026-09-27T18:00",
            "2026-09-28T00:00",
        ],
        "temperature_2m": [30.0, 22.0, 18.0, 16.0],
        "weather_code": [0, 61, 61, 3],
        "precipitation_probability": [5, 40, 70, 20],
    },
    "daily": {
        "time": ["2026-09-27", "2026-09-28"],
        "weather_code": [2, 3],
        "temperature_2m_max": [30.0, 19.0],
        "temperature_2m_min": [17.0, 13.0],
        "precipitation_probability_max": [70, 25],
    },
}


def _client(body: dict = FORECAST) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=body, request=request)
        )
    )


def test_weather_snapshot_dict() -> None:
    snap = WeatherSnapshot(
        latitude=41.4,
        longitude=2.17,
        temperature_c=22.0,
        wind_speed_kmh=10.0,
        condition="clear",
        weather_code=0,
    )
    d = snap.as_dict()
    assert d["condition"] == "clear"
    assert d["source"] == "open-meteo"


def test_fetch_weather_bundle_summarizes_remaining_today_and_tomorrow() -> None:
    with _client() as client:
        bundle = weather.fetch_weather_bundle(
            41.4, 2.17, base_url="https://weather.test", client=client
        )

    assert bundle.now.as_dict() == {
        "latitude": 41.4,
        "longitude": 2.17,
        "temperature_c": 21.5,
        "wind_speed_kmh": 12.0,
        "condition": "partly cloudy",
        "weather_code": 2,
        "source": "open-meteo",
    }
    assert bundle.today.date == "2026-09-27"
    assert bundle.today.high_c == 22.0
    assert bundle.today.low_c == 18.0
    assert bundle.today.precipitation_probability == 70
    assert bundle.today.condition == "light rain"
    assert bundle.tomorrow.as_dict() == {
        "date": "2026-09-28",
        "high_c": 19.0,
        "low_c": 13.0,
        "precipitation_probability": 25,
        "condition": "overcast",
        "weather_code": 3,
        "source": "open-meteo",
    }


def test_fetch_weather_bundle_requests_madrid_forecast_fields() -> None:
    seen_request: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen_request.append(request)
        return httpx.Response(200, json=FORECAST, request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        weather.fetch_weather_bundle(
            41.4, 2.17, base_url="https://weather.test/", client=client
        )

    params = seen_request[0].url.params
    assert params["timezone"] == "Europe/Madrid"
    assert params["hourly"] == (
        "temperature_2m,weather_code,precipitation_probability"
    )
    assert params["daily"] == (
        "weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max"
    )


def test_today_falls_back_to_daily_when_no_hours_remain() -> None:
    forecast = {
        **FORECAST,
        "current": {**FORECAST["current"], "time": "2026-09-27T23:30"},
    }

    with _client(forecast) as client:
        bundle = weather.fetch_weather_bundle(
            41.4, 2.17, base_url="https://weather.test", client=client
        )

    assert bundle.today.as_dict() == {
        "date": "2026-09-27",
        "high_c": 30.0,
        "low_c": 17.0,
        "precipitation_probability": 70,
        "condition": "partly cloudy",
        "weather_code": 2,
        "source": "open-meteo",
    }
