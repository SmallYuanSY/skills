import sys

sys.dont_write_bytecode = True  # keep __pycache__ out of src/, which the translator copies

from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# 2026-10-07 12:41 UTC = 2026-10-07 20:41 Wed in Taipei
NOW = datetime(2026, 10, 7, 12, 41, tzinfo=timezone.utc)

TAIPEI_DEFAULT = {"name": "台北市", "lat": 25.033, "lon": 121.565, "timezone": "Asia/Taipei"}

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


class FakeHttp:
    """Routes a URL to the first response whose prefix matches. A response may be data,
    an exception to raise, or a callable taking the URL."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, url: str, headers: dict | None = None):
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
