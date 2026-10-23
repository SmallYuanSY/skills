import json
import shutil
import urllib.parse

import pytest

import ww_alerts_tw
import ww_cyclones
from conftest import NOW, OPEN_METEO, TAIPEI_DEFAULT, WEATHERKIT, FakeHttp, fixture
from ww_config import save_config
from ww_http import HttpError
import weatherwise

OM = "https://api.open-meteo.com/"
WK = "https://weatherkit.apple.com/"
NOM = "https://nominatim.openstreetmap.org/search"
BANQIAO = [{"display_name": "板橋區, 新北市, 220, 臺灣", "lat": "25.011", "lon": "121.459",
            "address": {"suburb": "板橋區", "city": "新北市", "country_code": "tw"}}]
JIAOXI = [{"display_name": "礁溪鄉, 宜蘭縣, 262, 臺灣", "lat": "24.827", "lon": "121.775",
           "address": {"town": "礁溪鄉", "county": "宜蘭縣", "country_code": "tw"}}]
PLACES = {"板橋": BANQIAO, "礁溪": JIAOXI}


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)


def geocoder(url):
    for name, result in PLACES.items():
        if urllib.parse.quote(name) in url or f"q={name}" in url:
            return result
    return []


def forecast(url):
    """Open-Meteo answers the timezone probe with one object and the real request with one per place."""
    if "daily" not in url:
        return OPEN_METEO
    n = url.split("latitude=")[1].split("&")[0].count("%2C") + 1
    return OPEN_METEO if n == 1 else [OPEN_METEO] * n


def world(**extra):
    return FakeHttp({NOM: geocoder, OM: forecast, ww_alerts_tw.FEED: fixture("ncdr.xml"),
                     ww_cyclones.LIST_URL: {"features": []}, **extra})


def run(argv, http, capsys):
    code = weatherwise.main(argv, http=http, now=NOW)
    return code, capsys.readouterr().out.strip()


def use_weatherkit(config_dir, p8_key):
    config_dir.mkdir(parents=True, exist_ok=True)
    key = config_dir / p8_key.name
    shutil.copy(p8_key, key)
    save_config(config_dir, {"default": TAIPEI_DEFAULT, "weatherkit": {
        "team_id": "TEAM123456", "key_id": "ABC123DEF4", "service_id": "dev.example.weather",
        "key_path": str(key)}})


def test_free_mode_with_default_place(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    code, out = run([], FakeHttp({OM: OPEN_METEO}), capsys)
    assert code == 0
    assert out.splitlines()[:3] == [
        "local_time: 2026-10-07T20:41 Wed",
        "location: 台北市 (25.033, 121.565)",
        "now: Partly Cloudy 27°C",
    ]
    assert "source:" not in out and "humidity" not in out and "UV" not in out


def test_no_config_and_no_place_asks_where(config_dir, capsys):
    code, out = run([], FakeHttp({}), capsys)
    assert code == 1
    assert out.startswith("error: no_default_location\naction: ask the user where they are")


def test_weatherkit_mode(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run([], FakeHttp({WK: WEATHERKIT}), capsys)
    assert code == 0
    assert out.splitlines()[:3] == [
        "local_time: 2026-10-07T20:41 Wed", "location: 台北市 (25.033, 121.565)", "now: Partly Cloudy 27°C"]
    assert "next_hour: unavailable here" in out


def test_both_sources_give_the_same_weather_lines(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    _, free = run(["--days", "2"], FakeHttp({OM: OPEN_METEO}), capsys)
    use_weatherkit(config_dir, p8_key)
    _, paid = run(["--days", "2"], FakeHttp({WK: WEATHERKIT}), capsys)
    weather = lambda out: [ln for ln in out.splitlines() if not ln.startswith("next_hour")]  # noqa: E731
    assert weather(free) == weather(paid)
    assert "next_hour" not in free


def test_auth_failure_falls_back_with_a_notice(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run([], FakeHttp({WK: HttpError(401), OM: OPEN_METEO}), capsys)
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("notice: weatherkit_auth_failed (HTTP 401), fell back to open-meteo;")
    assert "membership may have expired" in lines[0]
    assert lines[1].startswith("local_time:") and "source:" not in out


def test_other_weatherkit_errors_do_not_fall_back(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run([], FakeHttp({WK: HttpError(500), OM: OPEN_METEO}), capsys)
    assert code == 1
    assert out.startswith("error: service_error")


def test_incomplete_weatherkit_config_is_an_error_not_a_fallback(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT, "weatherkit": {"team_id": "T"}})
    code, out = run([], FakeHttp({OM: OPEN_METEO}), capsys)
    assert code == 1
    assert out.startswith("error: weatherkit_config_incomplete")


def test_days_are_clamped(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    for given, sent in [("0", "forecast_days=1"), ("20", "forecast_days=10")]:
        http = FakeHttp({OM: OPEN_METEO})
        run(["--days", given], http, capsys)
        assert any(sent in u for u, _ in http.calls if u.startswith(OM))


def test_json_keeps_the_raw_data(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    _, out = run(["--json"], FakeHttp({OM: OPEN_METEO}), capsys)
    data = json.loads(out)
    assert data["places"][0]["source"] == "open-meteo"
    assert data["places"][0]["forecast"]["daily"] == OPEN_METEO["daily"]
    assert "notice" not in data


def test_version(capsys):
    _, out = run(["--version"], FakeHttp({}), capsys)
    assert out == "weatherwise 2.0.0 · by SmallYuan · https://github.com/SmallYuanSY/skills"


def test_bad_arguments_are_reported_for_the_model(config_dir, capsys):
    code, out = run(["--days", "many"], FakeHttp({}), capsys)
    assert code == 1
    assert out.startswith("error: bad_arguments")


def test_lang_flag_reaches_the_geocoder(config_dir, capsys):
    http = FakeHttp({"https://nominatim.openstreetmap.org/": [{"display_name": "Tokyo, Japan", "lat": "35.68", "lon": "139.69"}],
                     OM: OPEN_METEO})
    run(["Tokyo", "--global", "--lang", "en"], http, capsys)
    assert "accept-language=en" in http.calls[0][0]


def test_one_bad_place_does_not_fail_the_others(config_dir, capsys):
    code, out = run(["板橋", "zzzz"], world(), capsys)
    assert code == 0
    assert "[1] 板橋區, 新北市: Partly Cloudy 27°C" in out
    assert "[2] error: place_not_found (zzzz)\n    action: try another spelling" in out


def test_all_places_bad_uses_the_single_error_format(config_dir, capsys):
    code, out = run(["zzzz", "yyyy"], world(), capsys)
    assert code == 1
    assert out.startswith("error: place_not_found (zzzz)\naction: ")


def test_six_places_is_too_many(config_dir, capsys):
    http = world()
    code, out = run(list("abcdef"), http, capsys)
    assert code == 1
    assert out.startswith("error: too_many_places (6)\naction: ") and http.calls == []


def test_two_taiwan_places_fetch_ncdr_once(config_dir, capsys):
    http = world()
    code, out = run(["板橋", "礁溪"], http, capsys)
    assert code == 0
    assert [u for u, _ in http.calls].count(ww_alerts_tw.FEED) == 1
    assert sum(u.startswith(OM) and "daily" in u for u, _ in http.calls) == 1  # one forecast request
    assert out.splitlines()[1].startswith("[1] 板橋區") and out.splitlines()[2].startswith("[2] 礁溪鄉")
    assert "today 22–26°C, rain 0%" in out
    assert "[1][2]" in out  # NCDR rain/wind alerts that both places share are listed once


def test_second_run_within_ttl_makes_no_alert_requests(config_dir, capsys):
    run(["板橋", "礁溪"], world(), capsys)
    http = world()
    run(["板橋", "礁溪"], http, capsys)
    urls = [u for u, _ in http.calls]
    assert ww_alerts_tw.FEED not in urls
    assert not any(u.startswith(NOM) for u in urls)  # geocoding is cached for 30 days too


def test_cached_alerts_report_when_they_were_fetched(config_dir, capsys):
    weatherwise.main(["板橋"], http=world(), now=NOW.replace(minute=38))  # fetched 3 minutes before NOW
    capsys.readouterr()
    _, out = run(["板橋"], world(), capsys)
    assert "alerts (as of 20:38, current only" in out


def test_json_has_places_alerts_and_cyclones(config_dir, capsys):
    code, out = run(["板橋", "礁溪", "--json"], world(), capsys)
    data = json.loads(out)
    assert code == 0 and [p["location"] for p in data["places"]] == ["板橋區, 新北市, 臺灣", "礁溪鄉, 宜蘭縣, 臺灣"]
    first = data["places"][0]
    assert first["alerts"]["status"] == "ok" and first["alerts"]["items"]
    assert {"kind", "severity", "title", "summary", "detail", "expires", "key"} <= set(first["alerts"]["items"][0])
    assert first["forecast"]["daily"] == OPEN_METEO["daily"] and data["cyclones"] == []


def test_country_code_flag_is_gone(config_dir, capsys):
    code, out = run(["config", "weatherkit", "--country-code", "tw"], FakeHttp({}), capsys)
    assert code == 1 and out.startswith("error: bad_arguments")


def test_detail_flag_is_accepted_anywhere(config_dir, capsys):
    code, out = run(["板橋", "--detail", "礁溪"], world(), capsys)
    assert code == 0 and "[2] 礁溪鄉" in out


def test_weatherkit_auth_failure_falls_back_for_every_place(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run(["板橋", "礁溪"], world(**{WK: HttpError(403)}), capsys)
    assert code == 0 and out.startswith("notice: weatherkit_auth_failed (HTTP 403)")
    assert "[2] 礁溪鄉" in out


def test_revoked_weatherkit_key_is_tried_once(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    http = world(**{WK: HttpError(401)})
    code, out = run(["板橋", "礁溪"], http, capsys)
    assert code == 0 and sum(u.startswith(WK) for u, _ in http.calls) == 1
    assert "[1] 板橋區" in out and "[2] 礁溪鄉" in out


def test_no_nominatim_pause_before_a_cached_lookup(config_dir, capsys, monkeypatch):
    run(["礁溪"], world(), capsys)
    sleeps = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    run(["板橋", "礁溪"], world(), capsys)
    assert sleeps == []


def test_nominatim_pause_before_a_second_live_lookup(config_dir, capsys, monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    run(["板橋", "礁溪"], world(), capsys)
    assert len(sleeps) == 1


def test_gdacs_age_counts_toward_as_of(config_dir, capsys):
    gdacs = {"features": []}
    import ww_cyclones
    weatherwise.main(["板橋"], http=world(**{ww_cyclones.LIST_URL: gdacs}), now=NOW.replace(minute=30))
    capsys.readouterr()
    _, out = run(["板橋"], world(**{ww_cyclones.LIST_URL: gdacs}), capsys)  # NCDR expired, GDACS still cached
    assert "alerts (as of 20:30, current only" in out


def test_json_has_the_query_of_each_place(config_dir, capsys):
    _, out = run(["板橋", "zzzz", "--json"], world(), capsys)
    assert [p["query"] for p in json.loads(out)["places"]] == ["板橋", "zzzz"]


def test_gdacs_failure_says_cyclones_unavailable(config_dir, capsys):
    import ww_cyclones
    from ww_http import HttpError
    code, out = run(["板橋"], world(**{ww_cyclones.LIST_URL: HttpError(503)}), capsys)
    assert code == 0 and "cyclones: unavailable (gdacs HTTP 503; do not tell the user there is no tropical cyclone)" in out
    code, out = run(["板橋", "--json"], world(**{ww_cyclones.LIST_URL: HttpError(503)}), capsys)
    assert json.loads(out)["cyclones_unavailable"] == "gdacs HTTP 503"


def test_official_typhoon_alert_with_failed_geometry_has_no_gdacs_text(config_dir, capsys):
    """Scenario A: NCDR typhoon alert merged with a GDACS storm whose geometry could not be fetched."""
    gdacs = json.loads(fixture("gdacs_list.json"))
    geo = gdacs["features"][0]["properties"]["url"]["geometry"].split("?")[0]
    code, out = run(["板橋", "礁溪"], world(**{ww_cyclones.LIST_URL: gdacs, geo: HttpError(503)}), capsys)
    assert code == 0
    line = next(ln for ln in out.splitlines() if "颱風警報" in ln)
    assert "GDACS" not in line and "forecast" not in line and "CHAMPI" not in line
    assert "cyclones (" not in out and "forecast closest" not in out


def test_json_has_alerts_as_of_like_the_text_header(config_dir, capsys):
    _, out = run(["板橋", "--json"], world(), capsys)
    assert json.loads(out)["alerts_as_of"] == "2026-10-07T20:41:00+08:00"
    weatherwise.main(["板橋"], http=world(), now=NOW.replace(minute=30))  # seeds the alert cache
    capsys.readouterr()
    weatherwise.main(["板橋", "--json"], http=world(), now=NOW.replace(minute=40))
    assert json.loads(capsys.readouterr().out)["alerts_as_of"] == "2026-10-07T20:30:00+08:00"
