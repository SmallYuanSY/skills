"""The model must always get `error:` + `action:`, never a Python traceback."""
import io

import pytest

import weatherwise
import ww_http
from conftest import NOW, OPEN_METEO, TAIPEI_DEFAULT, WEATHERKIT, FakeHttp
from ww_config import load_config, save_config
from ww_errors import WwError
from ww_http import HttpError
from ww_model import Place
from ww_places import NOMINATIM, OPEN_METEO as OM_URL, geocode, with_timezone
from ww_render import render_report
from ww_sources import parse_open_meteo, parse_weatherkit

OM = "https://api.open-meteo.com/"


def run(argv, http, capsys):
    code = weatherwise.main(argv, http=http, now=NOW)
    return code, capsys.readouterr().out.strip()


# Review finding 1: HTTP errors outside the weather sources
def test_geocoding_rate_limit_is_a_service_error():
    with pytest.raises(WwError) as e:
        geocode("Tokyo", "en", True, FakeHttp({NOMINATIM: HttpError(429)}))
    assert e.value.code == "service_error"


def test_timezone_lookup_failure_is_a_service_error():
    with pytest.raises(WwError) as e:
        with_timezone(Place("x", 1, 2), FakeHttp({OM_URL: HttpError(502)}))
    assert e.value.code == "service_error"


# Review finding 2: a 200 response that isn't JSON (captive portal, proxy page)
def test_non_json_response_is_a_service_error(monkeypatch):
    monkeypatch.setattr(ww_http.urllib.request, "urlopen", lambda req, timeout: io.BytesIO(b"<html>login</html>"))
    with pytest.raises(WwError) as e:
        ww_http.get("https://example.com/")
    assert e.value.code == "service_error"


# Review finding 3: hand-edited config with the wrong shapes or values
@pytest.mark.parametrize("cfg", [
    [],
    "x",
    {"default": "Taipei"},
    {"default": {"lat": 25.0, "lon": 121.5}},
    {"default": {"name": "x", "lat": "abc", "lon": 121.5}},
    {"default": {"name": "x", "lat": 95, "lon": 121.5}},
    {"default": {"name": "x", "lat": 25.0, "lon": 121.5, "timezone": "Mars/Base"}},
    {"weatherkit": "yes"},
    {"lang": 5},
])
def test_malformed_config_is_config_invalid(config_dir, cfg):
    config_dir.mkdir()
    (config_dir / "config.json").write_text(__import__("json").dumps(cfg))
    with pytest.raises(WwError) as e:
        load_config(config_dir)
    assert e.value.code == "config_invalid"


def test_config_show_on_a_bad_config_is_an_error_not_a_crash(config_dir, capsys):
    config_dir.mkdir()
    (config_dir / "config.json").write_text('{"default": {"name": "x", "lat": "abc", "lon": 1}}')
    code, out = run(["config", "show"], FakeHttp({}), capsys)
    assert code == 1 and out.startswith("error: config_invalid")


# Review finding 4: unexpected API values and shapes
def test_null_temperatures_render_as_unknown():
    data = {**OPEN_METEO,
            "current": {**OPEN_METEO["current"], "temperature_2m": None, "apparent_temperature": None},
            "daily": {**OPEN_METEO["daily"], "temperature_2m_max": [None, 27.4]}}
    report = parse_open_meteo(data)
    out = render_report(report, Place("台北市", 25.033, 121.565, "Asia/Taipei"), NOW)
    assert "current: Partly Cloudy, unknown, feels unknown" in out
    assert "2026-10-07 Wed: Cloudy, 22–unknown" in out


def test_weatherkit_schema_change_is_a_service_error():
    data = {**WEATHERKIT, "currentWeather": {"temperature": 20}}  # conditionCode missing
    with pytest.raises(WwError) as e:
        parse_weatherkit(data, "Asia/Taipei", 3, alerts_available=False)
    assert e.value.code == "service_error"


def test_open_meteo_schema_change_is_a_service_error():
    with pytest.raises(WwError) as e:
        parse_open_meteo({**OPEN_METEO, "current": {"time": "x"}})
    assert e.value.code == "service_error"


# Backstop: anything unforeseen still reaches the model as error/action, without its message
def test_unexpected_exception_never_shows_a_traceback(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})

    def explode(url, headers=None):
        raise RuntimeError("secret detail that must not be printed")

    code, out = run([], explode, capsys)
    assert code == 1
    assert out.startswith("error: internal_error (RuntimeError)\naction: ")
    assert "secret detail" not in out
    assert "Traceback" not in out


def test_text_mode_returns_the_decoded_body(monkeypatch):
    body = "<feed>颱風</feed>".encode()
    monkeypatch.setattr(ww_http.urllib.request, "urlopen", lambda req, timeout: io.BytesIO(body))
    assert ww_http.get("https://example.com/", text=True) == "<feed>颱風</feed>"
