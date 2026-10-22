"""Real requests: they catch what fixtures can't, such as the APIs' actual field names."""
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import weatherwise
from conftest import OPEN_METEO, WEATHERKIT
from ww_http import get
from ww_model import Place
from ww_places import geocode, reverse, with_timezone
from ww_sources import fetch_open_meteo, fetch_weatherkit

pytestmark = pytest.mark.live

TAIPEI = Place("台北市", 25.033, 121.565, "Asia/Taipei")
LOCAL_WEATHERKIT = Path("~/.config/weatherkit/config.json").expanduser()
WK_FIELDS = ("team_id", "key_id", "service_id", "key_path")


def local_weatherkit() -> dict | None:
    """The WeatherKit IDs already on this machine. Never reads the key itself."""
    if not LOCAL_WEATHERKIT.exists():
        return None
    cfg = json.loads(LOCAL_WEATHERKIT.read_text())
    if not all(cfg.get(k) for k in WK_FIELDS):
        return None
    return {k: cfg[k] for k in WK_FIELDS}


needs_weatherkit = pytest.mark.skipif(local_weatherkit() is None, reason="no WeatherKit key on this machine")


def taipei_today() -> str:
    return datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()


@pytest.fixture
def polite():
    """Nominatim allows one request per second."""
    yield get
    time.sleep(1.1)


def test_open_meteo_returns_every_field_the_fixture_uses():
    r = fetch_open_meteo(TAIPEI, 3, get)
    assert set(OPEN_METEO["current"]) <= set(r.raw["current"])
    assert set(OPEN_METEO["daily"]) <= set(r.raw["daily"])
    assert r.raw["timezone"] == "Asia/Taipei"
    assert len(r.days) == 3
    assert r.days[0].date == taipei_today()
    assert not r.current.condition.startswith("Unknown")


def test_geocode_in_taiwan(polite):
    place = geocode("板橋", "zh-TW", False, polite)
    assert 24.9 < place.lat < 25.1 and 121.4 < place.lon < 121.55


@pytest.mark.parametrize("q,region,locality", [
    ("坪林", "新北市", "坪林區"), ("礁溪", "宜蘭縣", "礁溪鄉"), ("板橋", "新北市", "板橋區"),
    ("宜蘭市", "宜蘭縣", "宜蘭市")])
def test_geocode_prefers_the_district_over_a_same_named_village(q, region, locality, polite):
    p = geocode(q, "zh-TW", False, get)
    assert (p.country_code, p.region, p.locality) == ("tw", region, locality)


def test_geocode_tokyo_has_japanese_municipality(polite):
    p = geocode("東京都千代田区", "ja", True, get)
    assert p.country_code == "jp"
    assert "東京" in p.region


def test_reverse_fills_country_for_coordinates(polite):
    p = reverse(40.71, -74.0, "en", get)
    assert p.country_code == "us"


def test_geocode_abroad_with_timezone(polite):
    place = with_timezone(geocode("Tokyo", "en", True, polite), get)
    assert "Tokyo" in place.name
    assert place.timezone == "Asia/Tokyo"


def test_free_mode_end_to_end(config_dir, capsys, polite):
    assert weatherwise.main(["config", "set-default", "台北"]) == 0
    assert "timezone=Asia/Taipei" in capsys.readouterr().out
    assert weatherwise.main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "source: open-meteo"
    assert lines[2].startswith(f"local_time: {taipei_today()}T")


@needs_weatherkit
def test_weatherkit_returns_every_field_the_fixture_uses():
    r = fetch_weatherkit(TAIPEI, 3, "zh-TW", local_weatherkit(), get, int(time.time()))
    assert set(WEATHERKIT["currentWeather"]) <= set(r.raw["currentWeather"])
    assert set(WEATHERKIT["forecastDaily"]["days"][0]) <= set(r.raw["forecastDaily"]["days"][0])
    assert r.days[0].date == taipei_today()


@needs_weatherkit


@needs_weatherkit
def test_weatherkit_setup_end_to_end(config_dir, capsys):
    wk = local_weatherkit()
    assert weatherwise.main(["config", "set-default", "25.033,121.565"]) == 0
    code = weatherwise.main(["config", "weatherkit", "--team-id", wk["team_id"], "--service-id", wk["service_id"],
                             "--key-file", wk["key_path"], "--key-id", wk["key_id"]])
    out = capsys.readouterr().out
    assert code == 0, out
    assert weatherwise.main(["config", "show"]) == 0
    out = capsys.readouterr().out
    assert "source: weatherkit" in out
    assert wk["team_id"] not in out
    assert weatherwise.main([]) == 0
    assert capsys.readouterr().out.startswith("source: weatherkit")
    assert weatherwise.main(["config", "weatherkit", "--remove"]) == 0
