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
# Which data sets Apple has for a place. Alerts only exist in some countries
# (not Taiwan or Japan as of 2026-10), so ask before treating "no alerts" as "none".
WEATHERKIT_AVAILABILITY = "https://weatherkit.apple.com/api/v1/availability"


def fetch_open_meteo(place: Place, days: int, http) -> Report:
    q = urllib.parse.urlencode({
        "latitude": place.lat, "longitude": place.lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code,uv_index",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": place.timezone, "forecast_days": days,
    })
    try:
        return parse_open_meteo(http(f"{OPEN_METEO}?{q}"))
    except HttpError as e:
        raise WwError("service_error", f"open-meteo HTTP {e.status}") from None


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
    return Report("open-meteo", current, days, None, data)


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
    country = wk.get("country_code", "TW")
    available = http(
        f"{WEATHERKIT_AVAILABILITY}/{place.lat}/{place.lon}?{urllib.parse.urlencode({'country': country})}", headers
    )
    alerts_available = "weatherAlerts" in available
    data_sets = ["currentWeather", "forecastDaily"] + (["weatherAlerts"] if alerts_available else [])
    q = urllib.parse.urlencode({
        "dataSets": ",".join(data_sets), "timezone": place.timezone, "countryCode": country,
    })
    data = http(f"{WEATHERKIT}/{lang}/{place.lat}/{place.lon}?{q}", headers)
    return parse_weatherkit(data, place.timezone, days, alerts_available)


def parse_weatherkit(data: dict, tz: str, days: int, alerts_available: bool) -> Report:
    try:
        return _parse_weatherkit(data, tz, days, alerts_available)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise WwError("service_error", "unexpected weatherkit response") from None


def _parse_weatherkit(data: dict, tz: str, days: int, alerts_available: bool) -> Report:
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
    alerts = None
    if alerts_available:  # Apple omits weatherAlerts from the response when none are active
        alerts = [
            f"{a.get('description', '')} ({a.get('source', '')})"
            for a in (data.get("weatherAlerts") or {}).get("alerts", [])
        ]
    return Report("weatherkit", current, out, alerts, data)
