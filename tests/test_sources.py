import jwt
import pytest

from conftest import OPEN_METEO, WEATHERKIT, WK_AVAILABLE_WITH_ALERTS, FakeHttp
from ww_errors import WwError
from ww_http import HttpError
from ww_model import Current, Day, Place
from ww_sources import WEATHERKIT as WEATHERKIT_URL
from ww_sources import WEATHERKIT_AVAILABILITY
from ww_sources import fetch_open_meteo, fetch_weatherkit, parse_open_meteo, parse_weatherkit

TAIPEI = Place("台北市", 25.033, 121.565, "Asia/Taipei")
EXPECTED_CURRENT = Current("Partly Cloudy", 27.0, 29.1, 70, 12.3, 6.0)
EXPECTED_DAYS = [Day("2026-10-07", "Cloudy", 21.9, 25.8, 0), Day("2026-10-08", "Rain", 23.2, 27.4, 80)]


def test_open_meteo_parses_current_and_daily():
    r = parse_open_meteo(OPEN_METEO)
    assert r.source == "open-meteo"
    assert r.current == EXPECTED_CURRENT
    assert r.days == EXPECTED_DAYS


def test_open_meteo_nulls_become_none():
    data = {**OPEN_METEO, "current": {**OPEN_METEO["current"], "uv_index": None},
            "daily": {**OPEN_METEO["daily"], "precipitation_probability_max": [None, 80]}}
    r = parse_open_meteo(data)
    assert r.current.uv is None
    assert r.days[0].precip_chance is None


def test_open_meteo_request_uses_the_place_timezone_and_days():
    http = FakeHttp({"https://api.open-meteo.com/": OPEN_METEO})
    fetch_open_meteo(TAIPEI, 2, http)
    url = http.calls[0][0]
    assert "timezone=Asia%2FTaipei" in url and "forecast_days=2" in url


def test_open_meteo_http_error_is_a_service_error():
    with pytest.raises(WwError) as e:
        fetch_open_meteo(TAIPEI, 2, FakeHttp({"https://api.open-meteo.com/": HttpError(500)}))
    assert e.value.code == "service_error"


def test_weatherkit_matches_open_meteo_and_uses_local_dates():
    r = parse_weatherkit(WEATHERKIT, "Asia/Taipei", 10, alerts_available=True)
    assert r.source == "weatherkit"
    assert r.current.condition == "Partly Cloudy"
    assert round(r.current.humidity) == 70
    # 2026-10-06T16:00Z is already 2026-10-07 in Taipei
    assert [(d.date, d.condition, round(d.precip_chance)) for d in r.days] == [
        ("2026-10-07", "Cloudy", 0), ("2026-10-08", "Rain", 80)]


def test_weatherkit_request_is_signed(p8_key):
    wk = {"team_id": "TEAM123456", "key_id": "ABC123DEF4", "service_id": "dev.example.weather",
          "key_path": str(p8_key), "country_code": "TW"}
    http = FakeHttp({WEATHERKIT_AVAILABILITY: WK_AVAILABLE_WITH_ALERTS, WEATHERKIT_URL: WEATHERKIT})
    fetch_weatherkit(TAIPEI, 3, "en", wk, http, 1_791_000_000)
    assert http.calls[0][0] == f"{WEATHERKIT_AVAILABILITY}/25.033/121.565?country=TW"
    url, headers = http.calls[1]
    assert "weatherAlerts" in url
    assert url.startswith(f"{WEATHERKIT_URL}/en/25.033/121.565?")
    token = headers["Authorization"].removeprefix("Bearer ")
    assert jwt.get_unverified_header(token)["kid"] == "ABC123DEF4"
    claims = jwt.decode(token, options={"verify_signature": False})
    assert (claims["iss"], claims["sub"]) == ("TEAM123456", "dev.example.weather")


def test_weatherkit_http_errors_are_left_to_the_caller(p8_key):
    wk = {"team_id": "T", "key_id": "K", "service_id": "S", "key_path": str(p8_key)}
    with pytest.raises(HttpError):
        fetch_weatherkit(TAIPEI, 3, "en", wk, FakeHttp({"https://weatherkit.apple.com/": HttpError(401)}), 0)


def test_unreadable_key_is_an_invalid_key_file(tmp_path):
    bad = tmp_path / "AuthKey_X.p8"
    bad.write_text("not a key")
    wk = {"team_id": "T", "key_id": "K", "service_id": "S", "key_path": str(bad)}
    with pytest.raises(WwError) as e:
        fetch_weatherkit(TAIPEI, 3, "en", wk, FakeHttp({}), 0)
    assert e.value.code == "invalid_key_file"
