"""Open-Meteo (free, default) and WeatherKit (optional) both become the same Report."""
import urllib.parse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ww_errors import WwError
from ww_http import HttpError
from ww_model import Current, Day, Place, Report, weatherkit_condition, wmo_condition

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
WEATHERKIT = "https://weatherkit.apple.com/api/v1/weather"
HEAVY_RAIN_MM_H = 4.0


def fetch_open_meteo(place: Place, days: int, http) -> Report:
    return fetch_open_meteo_many([place], days, http)[0]


def fetch_open_meteo_many(places: list[Place], days: int, http) -> list[Report]:
    """One request for all places: Open-Meteo takes comma-joined coordinates."""
    q = urllib.parse.urlencode({
        "latitude": ",".join(str(p.lat) for p in places), "longitude": ",".join(str(p.lon) for p in places),
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code,uv_index",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": ",".join(p.timezone for p in places), "forecast_days": days,
    })
    try:
        data = http(f"{OPEN_METEO}?{q}")
    except HttpError as e:
        raise WwError("service_error", f"open-meteo HTTP {e.status}") from None
    items = data if isinstance(data, list) else [data]  # one place gets a dict, several get a list
    if len(items) != len(places):
        raise WwError("service_error", "unexpected open-meteo response")
    return [parse_open_meteo(item) for item in items]


def parse_open_meteo(data: dict) -> Report:
    try:
        return _parse_open_meteo(data)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise WwError("service_error", "unexpected open-meteo response") from None


def _parse_open_meteo(data: dict) -> Report:
    c = data.get("current")
    current = Current(
        wmo_condition(c["weather_code"]), c["temperature_2m"], c["apparent_temperature"],
        c["relative_humidity_2m"], c["wind_speed_10m"], c.get("uv_index"),
    ) if c else None
    d = data.get("daily") or {}
    days = [
        Day(t, wmo_condition(code), lo, hi, chance)
        for t, code, hi, lo, chance in zip(
            d.get("time", []), d.get("weather_code", []), d.get("temperature_2m_max", []),
            d.get("temperature_2m_min", []), d.get("precipitation_probability_max", []),
        )
    ]
    return Report("open-meteo", current, days, data)


def make_token(wk: dict, now_ts: int) -> str:
    import jwt

    try:
        key = Path(wk["key_path"]).expanduser().read_text()
        return jwt.encode(
            {"iss": wk["team_id"], "iat": now_ts, "exp": now_ts + 3600, "sub": wk["service_id"]},
            key, algorithm="ES256",
            headers={"kid": wk["key_id"], "id": f"{wk['team_id']}.{wk['service_id']}"},
        )
    except (OSError, ValueError, jwt.PyJWTError) as e:
        # Name the problem without echoing anything read from the key file
        raise WwError("invalid_key_file", type(e).__name__) from None


def fetch_weatherkit(place: Place, days: int, lang: str, wk: dict, http, now_ts: int) -> Report:
    headers = {"Authorization": f"Bearer {make_token(wk, now_ts)}"}
    params = {"dataSets": "currentWeather,forecastDaily,forecastNextHour", "timezone": place.timezone}
    if place.country_code:
        params["countryCode"] = place.country_code.upper()
    data = http(f"{WEATHERKIT}/{lang}/{place.lat}/{place.lon}?{urllib.parse.urlencode(params)}", headers)
    return parse_weatherkit(data, place.timezone, days)


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def summarize_next_hour(data: dict, tz: str) -> str:
    """One line from forecastNextHour. Segments split on any condition change, so only
    `clear` ends rain; rain turning to snow is still precipitation."""
    nh = data["forecastNextHour"]
    zone = ZoneInfo(tz)
    segs = nh.get("summary") or []
    minutes = nh.get("minutes") or []
    peak = max([s.get("precipitationIntensity") or 0 for s in segs if s["condition"] != "clear"]
               + [m.get("precipitationIntensity") or 0 for m in minutes], default=0)
    if not segs:
        if peak > 0:  # minutes show rain but nothing says when it starts or stops
            raise ValueError("no summary segments")
        return "no rain expected in the next hour"
    if all(s["condition"] == "clear" for s in segs):
        return "no rain expected in the next hour"
    fmt = lambda dt: dt.astimezone(zone).strftime("%H:%M")  # noqa: E731
    first = next(i for i, s in enumerate(segs) if s["condition"] != "clear")
    if first > 0:
        text = f"rain starting ~{fmt(_utc(segs[first]['startTime']))}"
    else:
        stop = next((_utc(s["startTime"]) for s in segs[first:] if s["condition"] == "clear"), None)
        end = segs[-1].get("endTime")
        if stop is None and end and nh.get("forecastEnd") and _utc(end) < _utc(nh["forecastEnd"]):
            stop = _utc(end)
        text = "rain for the whole hour" if stop is None else f"rain now, stopping ~{fmt(stop)}"
    return text + (", heavy" if peak >= HEAVY_RAIN_MM_H else "")


def parse_weatherkit(data: dict, tz: str, days: int) -> Report:
    try:
        return _parse_weatherkit(data, tz, days)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise WwError("service_error", "unexpected weatherkit response") from None


def _parse_weatherkit(data: dict, tz: str, days: int) -> Report:
    c = data.get("currentWeather")
    current = Current(
        weatherkit_condition(c["conditionCode"]), c["temperature"], c["temperatureApparent"],
        c["humidity"] * 100, c["windSpeed"], c.get("uvIndex"),
    ) if c else None
    zone = ZoneInfo(tz)
    out = []
    for d in (data.get("forecastDaily") or {}).get("days", [])[:days]:
        start = datetime.fromisoformat(d["forecastStart"].replace("Z", "+00:00")).astimezone(zone)
        chance = d.get("precipitationChance")
        out.append(Day(
            start.date().isoformat(), weatherkit_condition(d["conditionCode"]),
            d["temperatureMin"], d["temperatureMax"], None if chance is None else chance * 100,
        ))
    next_hour = "unavailable here"
    if data.get("forecastNextHour"):
        try:  # a malformed next-hour block must not cost the whole report
            next_hour = summarize_next_hour(data, tz)
        except (KeyError, TypeError, ValueError, AttributeError):
            pass
    return Report("weatherkit", current, out, data, next_hour)
