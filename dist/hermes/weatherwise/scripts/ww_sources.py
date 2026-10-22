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


def _local_time(iso: str, zone: ZoneInfo) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(zone).strftime("%H:%M")


def summarize_next_hour(data: dict, tz: str) -> str:
    """One line from forecastNextHour: segments say when rain starts or stops, intensity is mm/h."""
    nh = data["forecastNextHour"]
    zone = ZoneInfo(tz)
    segs = nh.get("summary") or []
    rainy = [s for s in segs if s["condition"] != "clear"]
    if not rainy:
        return "no rain expected in the next hour"
    peak = max([s.get("precipitationIntensity") or 0 for s in rainy]
               + [m.get("precipitationIntensity") or 0 for m in nh.get("minutes") or []])
    first = rainy[0]
    if segs[0] is not first:
        text = f"rain starting ~{_local_time(first['startTime'], zone)}"
    else:
        later = segs[1:2]
        stop = first.get("endTime") or (later[0]["startTime"] if later else None)
        if stop is None or (nh.get("forecastEnd") and stop >= nh["forecastEnd"]):
            text = "rain for the whole hour"
        else:
            text = f"rain now, stopping ~{_local_time(stop, zone)}"
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
    next_hour = summarize_next_hour(data, tz) if data.get("forecastNextHour") else "unavailable here"
    return Report("weatherkit", current, out, data, next_hour)
