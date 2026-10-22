import sys

sys.dont_write_bytecode = True  # keep __pycache__ out of src/, which the translator copies

from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# 2026-10-07 12:41 UTC = 2026-10-07 20:41 Wed in Taipei
NOW = datetime(2026, 10, 7, 12, 41, tzinfo=timezone.utc)

TAIPEI_DEFAULT = {"name": "台北市", "lat": 25.033, "lon": 121.565, "timezone": "Asia/Taipei",
                  "country_code": "tw"}

OPEN_METEO = {
    "timezone": "Asia/Taipei",
    "current": {
        "time": "2026-10-07T20:30", "temperature_2m": 27.0, "apparent_temperature": 29.1,
        "relative_humidity_2m": 70, "wind_speed_10m": 12.3, "weather_code": 2, "uv_index": 6.0,
    },
    "daily": {
        "time": ["2026-10-07", "2026-10-08"],
        "weather_code": [3, 61],
        "temperature_2m_max": [25.8, 27.4],
        "temperature_2m_min": [21.9, 23.2],
        "precipitation_probability_max": [0, 80],
    },
}

WEATHERKIT = {
    "currentWeather": {
        "conditionCode": "PartlyCloudy", "temperature": 27.04, "temperatureApparent": 29.1,
        "humidity": 0.7, "windSpeed": 12.3, "uvIndex": 6,
    },
    "forecastDaily": {"days": [
        {"forecastStart": "2026-10-06T16:00:00Z", "conditionCode": "Cloudy",
         "temperatureMin": 21.9, "temperatureMax": 25.8, "precipitationChance": 0.0},
        {"forecastStart": "2026-10-07T16:00:00Z", "conditionCode": "Rain",
         "temperatureMin": 23.2, "temperatureMax": 27.4, "precipitationChance": 0.8},
    ]},
    "weatherAlerts": {"alerts": []},
}

# forecastNextHour as WeatherKit returns it: summary segments (startTime/endTime, condition,
# precipitationIntensity in mm/h) plus per-minute data. Query time is 20:41 in Tokyo (11:41Z).
def _next_hour(summary, peak=None):
    return {"forecastNextHour": {
        "forecastStart": "2026-10-07T11:41:00Z", "forecastEnd": "2026-10-07T12:41:00Z",
        "summary": summary,
        "minutes": [{"startTime": "2026-10-07T11:41:00Z", "precipitationIntensity": peak or 0.0}],
    }}


NEXT_HOUR_RAIN_AT_2105 = _next_hour([  # 2026-10-07T12:05Z = 21:05 Tokyo
    {"startTime": "2026-10-07T11:41:00Z", "endTime": "2026-10-07T12:05:00Z", "condition": "clear",
     "precipitationChance": 0.0, "precipitationIntensity": 0.0},
    {"startTime": "2026-10-07T12:05:00Z", "condition": "rain",
     "precipitationChance": 0.8, "precipitationIntensity": 1.2},
])
NEXT_HOUR_CLEAR = _next_hour([
    {"startTime": "2026-10-07T11:41:00Z", "condition": "clear", "precipitationChance": 0.0,
     "precipitationIntensity": 0.0},
])
NEXT_HOUR_HEAVY_NOW_STOPPING_2140 = _next_hour([  # 12:40Z = 21:40 Tokyo
    {"startTime": "2026-10-07T11:41:00Z", "endTime": "2026-10-07T12:40:00Z", "condition": "rain",
     "precipitationChance": 1.0, "precipitationIntensity": 6.5},
    {"startTime": "2026-10-07T12:40:00Z", "condition": "clear", "precipitationChance": 0.0,
     "precipitationIntensity": 0.0},
], peak=6.5)
NEXT_HOUR_RAIN_WHOLE_HOUR = _next_hour([
    {"startTime": "2026-10-07T11:41:00Z", "condition": "rain", "precipitationChance": 0.9,
     "precipitationIntensity": 1.0},
])


class FakeHttp:
    """Routes a URL to the first response whose prefix matches. A response may be data,
    an exception to raise, or a callable taking the URL."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, url: str, headers: dict | None = None, *, text: bool = False):
        self.calls.append((url, headers))
        for prefix, resp in self.routes.items():
            if url.startswith(prefix):
                if isinstance(resp, Exception):
                    raise resp
                return resp(url) if callable(resp) else resp
        raise AssertionError(f"unexpected request: {url}")


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    d = tmp_path / "config"
    monkeypatch.setenv("WEATHERWISE_CONFIG_DIR", str(d))
    return d


@pytest.fixture
def p8_key(tmp_path):
    """A real P-256 key in Apple's file naming, so JWT signing works offline."""
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    path = tmp_path / "downloads" / "AuthKey_ABC123DEF4.p8"
    path.parent.mkdir()
    path.write_bytes(pem)
    return path


FIXTURES = Path(__file__).parent / "fixtures" / "alerts"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    """Keep tests away from the real cache."""
    d = tmp_path / "cache"
    monkeypatch.setenv("WEATHERWISE_CACHE_DIR", str(d))
    return d
