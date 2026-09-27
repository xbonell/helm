from weather import WeatherSnapshot


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
