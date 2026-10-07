"""Turns what the user said ("台中", "Tokyo", "24.15,120.67", nothing) into a Place."""
import re
import urllib.parse
from dataclasses import replace

from ww_errors import WwError
from ww_model import Place

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
COORDS = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def resolve_place(query: str | None, cfg: dict, lang: str, global_search: bool, http) -> Place:
    if not query:
        d = cfg.get("default")
        if not d:
            raise WwError("no_default_location")
        return Place(d["name"], float(d["lat"]), float(d["lon"]), d.get("timezone"))
    m = COORDS.match(query)
    if m:
        lat, lon = float(m[1]), float(m[2])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise WwError("place_not_found", query.strip())
        return Place(f"{lat},{lon}", lat, lon)
    return geocode(query, lang, global_search, http)


def geocode(query: str, lang: str, global_search: bool, http) -> Place:
    base = {"q": query, "format": "json", "limit": 1, "accept-language": lang}
    # Taiwan first, then worldwide; --global goes straight to worldwide
    attempts = [base] if global_search else [{**base, "countrycodes": "tw"}, base]
    for params in attempts:
        res = http(f"{NOMINATIM}?{urllib.parse.urlencode(params)}")
        if res:
            r = res[0]
            parts = [p.strip() for p in r["display_name"].split(",")]
            name = ", ".join(p for p in parts if not p.isdigit())
            return Place(name, float(r["lat"]), float(r["lon"]))
    raise WwError("place_not_found", query)


def with_timezone(place: Place, http) -> Place:
    if place.timezone:
        return place
    q = urllib.parse.urlencode(
        {"latitude": place.lat, "longitude": place.lon, "timezone": "auto", "forecast_days": 1}
    )
    return replace(place, timezone=http(f"{OPEN_METEO}?{q}").get("timezone") or "UTC")
