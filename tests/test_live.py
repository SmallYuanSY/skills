"""Real requests: they catch what fixtures can't, such as the APIs' actual field names."""
import json
import re
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


def test_geocode_german_district(polite):
    p = geocode("Bad Oldesloe", "en", True, get)
    assert p.country_code == "de" and "Stormarn" in (p.district or "")
    time.sleep(1.1)
    hamburg = geocode("Hamburg", "en", True, get)
    assert hamburg.country_code == "de" and hamburg.district  # kreisfreie Stadt: county missing, city used


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
    assert lines[0].startswith(f"local_time: {taipei_today()}T")
    assert not any(line.startswith("source:") for line in lines)


@needs_weatherkit
def test_weatherkit_returns_every_field_the_fixture_uses():
    r = fetch_weatherkit(TAIPEI, 3, "zh-TW", local_weatherkit(), get, int(time.time()))
    assert set(WEATHERKIT["currentWeather"]) <= set(r.raw["currentWeather"])
    assert set(WEATHERKIT["forecastDaily"]["days"][0]) <= set(r.raw["forecastDaily"]["days"][0])
    assert r.days[0].date == taipei_today()


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
    assert capsys.readouterr().out.startswith("local_time: ")
    assert weatherwise.main(["config", "weatherkit", "--remove"]) == 0


@needs_weatherkit
def test_weatherkit_next_hour_in_tokyo():
    tokyo = Place("東京", 35.681, 139.767, "Asia/Tokyo", "jp")
    r = fetch_weatherkit(tokyo, 1, "en", local_weatherkit(), get, int(time.time()))
    assert "forecastNextHour" in r.raw
    assert re.fullmatch(
        r"no rain expected in the next hour|rain for the whole hour|rain starting ~\d\d:\d\d(, heavy)?"
        r"|rain now, stopping ~\d\d:\d\d(, heavy)?|rain for the whole hour, heavy",
        r.next_hour)


def test_ncdr_feed_still_has_the_fields_we_parse():
    import xml.etree.ElementTree as ET

    import ww_alerts_tw

    root = ET.fromstring(get(ww_alerts_tw.FEED, text=True))
    assert root.find(".//WarningMessage") is None, "rate limited"
    entries = root.findall(f"{ww_alerts_tw.ATOM}entry")
    assert entries
    for e in entries:
        assert e.findtext(f"{ww_alerts_tw.ATOM}author/{ww_alerts_tw.ATOM}name")
        assert e.findtext(f"{ww_alerts_tw.ATOM}title")
        expires = e.findtext(f"{ww_alerts_tw.CAP}expires")
        if expires:
            assert ww_alerts_tw.parse_ncdr_time(expires).tzinfo is not None
    assert any(e.findtext(f"{ww_alerts_tw.CAP}status") for e in entries)


def test_gdacs_list_and_geometry_shape():
    import ww_cyclones

    features = get(ww_cyclones.LIST_URL)["features"]
    assert features
    for f in features:
        p = f["properties"]
        assert p["eventname"] and p["alertlevel"] in ("Green", "Orange", "Red")
        assert p["iscurrent"] in ("true", "false") and datetime.fromisoformat(p["todate"])
        lon, lat = f["geometry"]["coordinates"]
        assert -90 <= lat <= 90 and -180 <= lon <= 180
        assert p["url"]["geometry"].startswith("https://www.gdacs.org/")
    current = next((f for f in features if f["properties"]["iscurrent"] == "true"), features[0])
    geo = get(current["properties"]["url"]["geometry"])
    classes = {g["properties"].get("Class") for g in geo["features"]}
    assert "Point_Centroid" in classes and "Poly_Green" in classes
    assert any(g["geometry"]["type"] == "LineString" and "forecast" in g["properties"] for g in geo["features"])


def test_jma_area_and_tokyo_warning_shape(polite):
    import ww_alerts_jp

    area = get(ww_alerts_jp.AREA_URL)
    assert area["class20s"]["1310100"]["name"] == "千代田区"
    assert ww_alerts_jp._office_of(area, "1310100") == "130000"
    time.sleep(1)
    report = get(ww_alerts_jp.WARNING_URL.format("130000"))
    assert datetime.fromisoformat(report["reportDatetime"]).tzinfo and "headlineText" in report
    areas = [a for t in report["areaTypes"] for a in t["areas"]]
    assert any(a["code"] == "1310100" for a in areas)
    for a in areas:
        for w in a["warnings"]:
            assert w["status"]
            if w["status"] not in ww_alerts_jp.INACTIVE:
                assert w["code"]
    p = Place("千代田区", 35.694, 139.754, "Asia/Tokyo", "jp", "東京", "千代田区")
    assert ww_alerts_jp.alerts_for([p], get, datetime.now().astimezone())[0] is not None


def test_nws_point_shape(polite):
    import ww_alerts_us

    data = get(ww_alerts_us.URL.format(36.0633, -111.4152), {"Accept": "application/geo+json"})
    assert isinstance(data["features"], list)
    for f in data["features"]:
        p = f["properties"]
        assert p["id"] and p["event"] and "severity" in p and "description" in p
    time.sleep(1)
    p = Place("Flagstaff", 36.0633, -111.4152, "America/Phoenix", "us", "Arizona")
    assert isinstance(ww_alerts_us.alerts_for([p], get, datetime.now().astimezone())[0], list)


def test_hko_warnsum_is_a_dict(polite):
    import ww_alerts_hk

    data = get(ww_alerts_hk.URL)
    assert isinstance(data, dict)
    for w in data.values():
        assert w["name"] and w["updateTime"]
    hk = Place("香港", 22.32, 114.17, "Asia/Hong_Kong", "hk")
    assert ww_alerts_hk.alerts_for([hk], get, datetime.now().astimezone())[0] is not None


def test_eccc_shape(polite):
    import ww_alerts_ca

    toronto = Place("多倫多", 43.65, -79.38, "America/Toronto", "ca", "Ontario")
    data = get(ww_alerts_ca.URL.format(-79.88, 43.15, -78.88, 44.15))
    assert isinstance(data["features"], list)
    for f in data["features"]:
        p = f["properties"]
        assert f["id"] and f["geometry"]["type"] in ("Polygon", "MultiPolygon")
        assert p["alert_name_en"] and p["risk_colour_en"] and "expiration_datetime" in p
    time.sleep(1)
    now = datetime.now().astimezone()
    for f in data["features"]:
        a = ww_alerts_ca._alert(f) if f["properties"].get("alert_type") != "ended" else None
        assert a is None or (a.title and a.expires.tzinfo is not None)
    out = ww_alerts_ca.alerts_for([toronto], get, now)
    assert len(out) == 1 and isinstance(out[0], list)


def test_meteoalarm_germany_shape(polite):
    import ww_alerts_eu

    data = get(ww_alerts_eu.URL.format("germany"))
    assert isinstance(data["warnings"], list)
    for w in data["warnings"]:
        a = w["alert"]
        assert a["identifier"] and a["info"]
        info = ww_alerts_eu._info(a)
        assert info["event"] and info["severity"] and info["category"] and info["area"]
        assert all("areaDesc" in x for x in info["area"])
    berlin = Place("柏林", 52.52, 13.405, "Europe/Berlin", "de", "Berlin", "Mitte")
    now = datetime.now().astimezone()
    parsed = [ww_alerts_eu._alert(w)[0] for w in data["warnings"] if ww_alerts_eu._is_weather(ww_alerts_eu._info(w["alert"]))]
    assert all(a.title and a.key.startswith("meteoalarm:") and (a.expires is None or a.expires.tzinfo) for a in parsed)
    out = ww_alerts_eu.alerts_for([berlin], get, now)
    assert len(out) == 1 and (out[0] is None or isinstance(out[0], list))


def test_zh_tw_user_gets_local_language_names_abroad(polite):
    berlin = geocode("Berlin", "zh-TW", True, get)
    assert berlin.country_code == "de" and berlin.region == "Berlin"  # what MeteoAlarm's areaDesc says
    time.sleep(1.1)
    chiyoda = geocode("千代田区", "zh-TW", True, get)
    assert chiyoda.country_code == "jp" and chiyoda.locality == "千代田区"


def test_geocode_hong_kong_is_hk(polite):
    assert geocode("香港", "zh-TW", True, get).country_code == "hk"


def test_osaka_ward_matches_osaka_city_in_jma(polite):
    import ww_alerts_jp

    p = geocode("大阪市北区", "ja", True, get)
    assert (p.region, p.locality, p.district) == ("大阪府", "北区", "大阪市")
    codes, office = ww_alerts_jp._match(get(ww_alerts_jp.AREA_URL), p)
    assert (codes, office) == (["2710000"], "270000")
