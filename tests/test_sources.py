import jwt
import pytest

from conftest import (
    NEXT_HOUR_CLEAR, _next_hour, NEXT_HOUR_HEAVY_NOW_STOPPING_2140, NEXT_HOUR_RAIN_AT_2105, NEXT_HOUR_RAIN_WHOLE_HOUR,
    OPEN_METEO, WEATHERKIT, FakeHttp,
)
from ww_errors import WwError
from ww_http import HttpError
from ww_model import Current, Day, Place
from ww_sources import WEATHERKIT as WEATHERKIT_URL
from ww_sources import (
    fetch_open_meteo, fetch_open_meteo_many, fetch_weatherkit, parse_open_meteo, parse_weatherkit,
    summarize_next_hour,
)

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
    r = parse_weatherkit(WEATHERKIT, "Asia/Taipei", 10)
    assert r.source == "weatherkit"
    assert r.current.condition == "Partly Cloudy"
    assert round(r.current.humidity) == 70
    # 2026-10-06T16:00Z is already 2026-10-07 in Taipei
    assert [(d.date, d.condition, round(d.precip_chance)) for d in r.days] == [
        ("2026-10-07", "Cloudy", 0), ("2026-10-08", "Rain", 80)]


def test_weatherkit_request_is_signed(p8_key):
    wk = {"team_id": "TEAM123456", "key_id": "ABC123DEF4", "service_id": "dev.example.weather",
          "key_path": str(p8_key)}
    http = FakeHttp({WEATHERKIT_URL: WEATHERKIT})
    fetch_weatherkit(TAIPEI, 3, "en", wk, http, 1_791_000_000)
    assert len(http.calls) == 1
    url, headers = http.calls[0]
    assert "weatherAlerts" not in url
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


def wk(p8_key):
    return {"team_id": "T", "key_id": "K", "service_id": "S", "key_path": str(p8_key)}


def test_weatherkit_uses_the_place_country_not_a_setting(p8_key):
    http = FakeHttp({WEATHERKIT_URL: WEATHERKIT})
    fetch_weatherkit(Place("New York", 40.71, -74.0, "America/New_York", "us"), 1, "en", wk(p8_key), http, 0)
    assert "countryCode=US" in http.calls[0][0] and "availability" not in http.calls[0][0]


def test_weatherkit_omits_country_when_unknown(p8_key):
    http = FakeHttp({WEATHERKIT_URL: WEATHERKIT})
    fetch_weatherkit(TAIPEI, 1, "en", wk(p8_key), http, 0)
    assert "countryCode" not in http.calls[0][0]


def test_weatherkit_asks_for_next_hour_and_reports_unavailable_when_missing(p8_key):
    http = FakeHttp({WEATHERKIT_URL: WEATHERKIT})
    r = fetch_weatherkit(TAIPEI, 1, "en", wk(p8_key), http, 0)
    assert "dataSets=currentWeather%2CforecastDaily%2CforecastNextHour" in http.calls[0][0]
    assert r.next_hour == "unavailable here"


def test_weatherkit_reports_the_next_hour_when_present(p8_key):
    http = FakeHttp({WEATHERKIT_URL: {**WEATHERKIT, **NEXT_HOUR_RAIN_AT_2105}})
    r = fetch_weatherkit(Place("東京", 35.68, 139.76, "Asia/Tokyo", "jp"), 1, "en", wk(p8_key), http, 0)
    assert r.next_hour == "rain starting ~21:05"


def test_next_hour_rain_starting():
    assert summarize_next_hour(NEXT_HOUR_RAIN_AT_2105, "Asia/Tokyo") == "rain starting ~21:05"


def test_next_hour_all_clear():
    assert summarize_next_hour(NEXT_HOUR_CLEAR, "Asia/Tokyo") == "no rain expected in the next hour"


def test_next_hour_heavy_rain_now_stopping():
    assert summarize_next_hour(NEXT_HOUR_HEAVY_NOW_STOPPING_2140, "Asia/Tokyo") == "rain now, stopping ~21:40, heavy"


def test_next_hour_rain_all_hour():
    assert summarize_next_hour(NEXT_HOUR_RAIN_WHOLE_HOUR, "Asia/Tokyo") == "rain for the whole hour"


def test_next_hour_uses_the_place_timezone():
    assert summarize_next_hour(NEXT_HOUR_RAIN_AT_2105, "Europe/Berlin") == "rain starting ~14:05"


def test_open_meteo_many_places_is_one_request():
    banqiao = Place("板橋", 24.827, 121.45, "Asia/Taipei")
    http = FakeHttp({"https://api.open-meteo.com/": [OPEN_METEO, OPEN_METEO]})
    reports = fetch_open_meteo_many([TAIPEI, banqiao], 2, http)
    assert len(http.calls) == 1 and len(reports) == 2
    url = http.calls[0][0]
    assert "latitude=25.033%2C24.827" in url and "longitude=121.565%2C121.45" in url
    assert "timezone=Asia%2FTaipei%2CAsia%2FTaipei" in url
    assert reports[1].current == EXPECTED_CURRENT


def test_open_meteo_many_with_wrong_count_is_a_service_error():
    http = FakeHttp({"https://api.open-meteo.com/": [OPEN_METEO]})
    with pytest.raises(WwError) as e:
        fetch_open_meteo_many([TAIPEI, TAIPEI], 2, http)
    assert e.value.code == "service_error"


def test_open_meteo_has_no_next_hour():
    r = fetch_open_meteo(TAIPEI, 2, FakeHttp({"https://api.open-meteo.com/": OPEN_METEO}))
    assert r.next_hour is None


def test_next_hour_rain_turning_to_snow_is_not_stopping():
    data = _next_hour([
        {"startTime": "2026-10-07T11:41:00Z", "condition": "rain", "precipitationIntensity": 1.0},
        {"startTime": "2026-10-07T12:10:00Z", "condition": "snow", "precipitationIntensity": 1.0},
    ])
    assert summarize_next_hour(data, "Asia/Tokyo") == "rain for the whole hour"
    data["forecastNextHour"]["summary"].append(
        {"startTime": "2026-10-07T12:30:00Z", "condition": "clear", "precipitationIntensity": 0.0})
    assert summarize_next_hour(data, "Asia/Tokyo") == "rain now, stopping ~21:30"


def test_malformed_next_hour_keeps_current_and_daily():
    bad = {"forecastNextHour": {"summary": [{"startTime": "soon"}]}}
    r = parse_weatherkit({**WEATHERKIT, **bad}, "Asia/Taipei", 3)
    assert r.next_hour == "unavailable here"
    assert r.current.condition == "Partly Cloudy" and len(r.days) == 2


def test_next_hour_without_summary_but_rain_in_minutes_is_not_called_dry():
    data = _next_hour([], peak=2.0)
    assert parse_weatherkit({**WEATHERKIT, **data}, "Asia/Tokyo", 1).next_hour == "unavailable here"
    assert summarize_next_hour(_next_hour([]), "Asia/Tokyo") == "no rain expected in the next hour"
