from __future__ import annotations
from dataclasses import dataclass

class WeatherLocationError(ValueError):
    pass

@dataclass(frozen=True)
class WeatherLocation:
    name: str
    latitude: float
    longitude: float

def parse_weather_locations(raw: str) -> list[WeatherLocation]:
    text = (raw or "").strip()
    if not text:
        raise WeatherLocationError("WEATHER_LOCATIONS is empty")
    out: list[WeatherLocation] = []
    seen_names: set[str] = set()
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise WeatherLocationError(f"missing ':' in location entry: {part!r}")
        name, coords = part.rsplit(":", 1)
        name = name.strip()
        coords = coords.strip()
        if not name or "," not in coords:
            raise WeatherLocationError(f"invalid location entry: {part!r}")
        lat_s, lon_s = coords.split(",", 1)
        try:
            lat = float(lat_s.strip())
            lon = float(lon_s.strip())
        except ValueError as exc:
            raise WeatherLocationError(f"invalid coordinates in {part!r}") from exc
        if name in seen_names:
            raise WeatherLocationError(f"duplicate location name: {name!r}")
        seen_names.add(name)
        out.append(WeatherLocation(name=name, latitude=lat, longitude=lon))
    if not out:
        raise WeatherLocationError("WEATHER_LOCATIONS produced no locations")
    return out
