import pytest
from locations import WeatherLocation, WeatherLocationError, parse_weather_locations

DEFAULT = "Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864"

def test_parse_default_two_cities():
    locs = parse_weather_locations(DEFAULT)
    assert locs == [
        WeatherLocation(name="Barcelona", latitude=41.3874, longitude=2.1686),
        WeatherLocation(name="Sant Cugat del Vallès", latitude=41.4728, longitude=2.0864),
    ]

def test_parse_rejects_empty():
    with pytest.raises(WeatherLocationError):
        parse_weather_locations("")
    with pytest.raises(WeatherLocationError):
        parse_weather_locations("   ")

def test_parse_rejects_malformed():
    with pytest.raises(WeatherLocationError):
        parse_weather_locations("Barcelona")
    with pytest.raises(WeatherLocationError):
        parse_weather_locations("Barcelona:41.3874")


def test_parse_rejects_duplicate_names():
    with pytest.raises(WeatherLocationError, match="duplicate location name"):
        parse_weather_locations(
            "Barcelona:41.3874,2.1686;Barcelona:41.4728,2.0864"
        )
