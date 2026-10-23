import pytest

import ww_places

from conftest import TAIPEI_DEFAULT, FakeHttp
from ww_errors import WwError
from ww_http import HttpError
from ww_model import Place
from ww_config import load_config
from ww_places import NOMINATIM, NOMINATIM_REVERSE, OPEN_METEO, geocode, resolve_place, with_timezone
from ww_setup import ensure_default_complete

TAICHUNG = [{"display_name": "臺中市, 40001, 臺灣", "lat": "24.1477", "lon": "120.6736",
             "address": {"city": "臺中市", "country": "臺灣", "country_code": "tw"}}]


def test_no_query_uses_the_default():
    place = resolve_place(None, {"default": TAIPEI_DEFAULT}, "zh-TW", False, FakeHttp({}))
    assert place == Place("台北市", 25.033, 121.565, "Asia/Taipei", "tw")


def test_no_query_and_no_default_asks_for_a_place():
    with pytest.raises(WwError) as e:
        resolve_place(None, {}, "zh-TW", False, FakeHttp({}))
    assert e.value.code == "no_default_location"


@pytest.mark.parametrize("query", ["24.15,120.67", " 24.15 , 120.67 "])
def test_coordinates_skip_geocoding(query):
    place = resolve_place(query, {}, "zh-TW", False, FakeHttp({NOMINATIM_REVERSE: {}}))
    assert (place.lat, place.lon, place.timezone) == (24.15, 120.67, None)


@pytest.mark.parametrize("query", ["200,10", "10,-181"])
def test_out_of_range_coordinates_are_rejected(query):
    with pytest.raises(WwError) as e:
        resolve_place(query, {}, "zh-TW", False, FakeHttp({}))
    assert e.value.code == "place_not_found"


def test_place_name_searches_taiwan_first_and_drops_postcodes():
    http = FakeHttp({NOMINATIM: TAICHUNG})
    place = resolve_place("台中", {}, "zh-TW", False, http)
    assert place == Place("臺中市, 臺灣", 24.1477, 120.6736, None, "tw", "臺中市", None)
    assert "countrycodes=tw" in http.calls[0][0]
    assert "accept-language=zh-TW" in http.calls[0][0]


def test_falls_back_to_a_global_search():
    http = FakeHttp({NOMINATIM: lambda url: [] if "countrycodes=tw" in url else TAICHUNG})
    resolve_place("台中", {}, "en", False, http)
    assert len(http.calls) == 2
    assert "countrycodes" not in http.calls[1][0]


def test_global_flag_skips_the_taiwan_search():
    http = FakeHttp({NOMINATIM: TAICHUNG})
    resolve_place("Tokyo", {}, "en", True, http)
    assert len(http.calls) == 1
    assert "countrycodes" not in http.calls[0][0]


def test_unknown_place():
    with pytest.raises(WwError) as e:
        resolve_place("Atlantis", {}, "en", False, FakeHttp({NOMINATIM: []}))
    assert (e.value.code, e.value.detail) == ("place_not_found", "Atlantis")


def test_timezone_is_looked_up_only_when_missing():
    http = FakeHttp({OPEN_METEO: {"timezone": "Asia/Tokyo"}})
    assert with_timezone(Place("x", 35.68, 139.69), http).timezone == "Asia/Tokyo"
    assert with_timezone(Place("y", 1, 2, "Asia/Taipei"), http).timezone == "Asia/Taipei"
    assert len(http.calls) == 1


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(ww_places, "PAUSE", 0)


# Trimmed from real Nominatim answers (2026-10-22). A bare "坪林" lists only villages and hamlets;
# the district shows up when asking for "坪林區".
PINGLIN_RESULTS = [
    {"class": "place", "type": "village", "name": "坪林", "display_name": "坪林, 卓蘭鎮, 苗栗縣, 369, 臺灣",
     "lat": "24.3346950", "lon": "120.8750260",
     "address": {"village": "坪林", "town": "卓蘭鎮", "county": "苗栗縣", "country": "臺灣", "country_code": "tw"}},
    {"class": "place", "type": "hamlet", "name": "坪林", "display_name": "坪林, 三峽區, 紫微, 新北市, 237008, 臺灣",
     "lat": "24.9311717", "lon": "121.4112211",
     "address": {"hamlet": "坪林", "suburb": "三峽區", "village": "紫微", "city": "新北市",
                 "country": "臺灣", "country_code": "tw"}},
]
PINGLIN_DISTRICT = [
    {"class": "boundary", "type": "administrative", "name": "坪林區", "display_name": "坪林區, 新北市, 臺灣",
     "lat": "24.9344", "lon": "121.7114",
     "address": {"suburb": "坪林區", "city": "新北市", "country": "臺灣", "country_code": "tw"}},
]
# With the district among the five results, as the brief assumed: it must beat the first village.
PINGLIN_MIXED = [PINGLIN_RESULTS[0], PINGLIN_RESULTS[1], PINGLIN_DISTRICT[0]]
JIAOXI = [
    {"class": "railway", "type": "station", "name": "礁溪", "display_name": "礁溪, 溫泉路3巷, 德陽村, 礁溪鄉, 宜蘭縣, 26248, 臺灣",
     "lat": "24.8268030", "lon": "121.7754851",
     "address": {"railway": "礁溪", "hamlet": "德陽村", "city_district": "德陽村", "town": "礁溪鄉",
                 "county": "宜蘭縣", "country": "臺灣", "country_code": "tw"}},
]
CHIYODA = [
    {"class": "boundary", "type": "administrative", "name": "千代田区", "display_name": "千代田区, 東京, 102-0000, 日本",
     "lat": "35.6940537", "lon": "139.7535006",
     "address": {"city": "千代田区", "postcode": "102-0000", "country": "日本", "country_code": "jp"}},
]
NEW_YORK = {
    "lat": "40.7189702", "lon": "-73.9807827", "display_name": "Manhattan, New York County, New York, United States",
    "address": {"suburb": "Manhattan", "city_district": "New York County", "city": "New York",
                "state": "New York", "country": "United States", "country_code": "us"},
}


def test_administrative_match_beats_the_first_result():
    p = geocode("坪林", "zh-TW", False, FakeHttp({NOMINATIM: PINGLIN_MIXED}))
    assert (p.region, p.locality, p.country_code) == ("新北市", "坪林區", "tw")


def test_bare_district_name_is_retried_with_a_district_suffix():
    http = FakeHttp({NOMINATIM: lambda url: PINGLIN_DISTRICT if "q=%E5%9D%AA%E6%9E%97%E5%8D%80" in url else PINGLIN_RESULTS})
    p = geocode("坪林", "zh-TW", False, http)
    assert (p.name, p.region, p.locality) == ("坪林區, 新北市, 臺灣", "新北市", "坪林區")
    assert len(http.calls) == 2


def test_no_district_anywhere_falls_back_to_the_first_result():
    p = geocode("坪林", "zh-TW", False, FakeHttp({NOMINATIM: PINGLIN_RESULTS}))
    assert (p.region, p.locality) == ("苗栗縣", "卓蘭鎮")


def test_township_comes_from_town_in_the_county_case():
    p = geocode("礁溪", "zh-TW", False, FakeHttp({NOMINATIM: JIAOXI}))
    assert (p.region, p.locality) == ("宜蘭縣", "礁溪鄉")


def test_japan_takes_the_prefecture_from_display_name_when_the_address_has_none():
    p = geocode("東京都千代田区", "ja", True, FakeHttp({NOMINATIM: CHIYODA, NOMINATIM_REVERSE: HttpError(429)}))
    assert (p.country_code, p.region, p.locality) == ("jp", "東京", "千代田区")


def test_search_asks_for_address_details_and_five_results():
    http = FakeHttp({NOMINATIM: JIAOXI})
    geocode("礁溪", "zh-TW", False, http)
    assert "addressdetails=1" in http.calls[0][0]
    assert "limit=5" in http.calls[0][0]


def test_coordinates_get_country_from_reverse_geocoding():
    http = FakeHttp({NOMINATIM_REVERSE: NEW_YORK})
    place = resolve_place("40.71,-74.0", {}, "en", False, http)
    assert (place.name, place.country_code, place.region, place.locality) == ("40.71,-74.0", "us", "New York", "Manhattan")
    url = http.calls[0][0]
    for part in ("addressdetails=1", "zoom=14", "lat=40.71", "lon=-74.0", "accept-language=en"):
        assert part in url


def test_coordinates_still_work_when_reverse_geocoding_fails():
    from ww_http import HttpError
    place = resolve_place("40.71,-74.0", {}, "en", False, FakeHttp({NOMINATIM_REVERSE: HttpError(429)}))
    assert (place.lat, place.country_code) == (40.71, None)


def test_default_without_country_is_filled_once_and_saved(config_dir):
    from conftest import TAIPEI_DEFAULT
    from ww_config import save_config
    taipei = {"address": {"suburb": "信義區", "city": "臺北市", "country": "臺灣", "country_code": "tw"}}
    cfg = {"default": {k: v for k, v in TAIPEI_DEFAULT.items() if k != "country_code"}}
    save_config(config_dir, cfg)
    http = FakeHttp({NOMINATIM_REVERSE: taipei})
    ensure_default_complete(cfg, config_dir, "zh-TW", http)
    saved = load_config(config_dir)["default"]
    assert (saved["country_code"], saved["region"], saved["locality"]) == ("tw", "臺北市", "信義區")
    ensure_default_complete(load_config(config_dir), config_dir, "zh-TW", http)
    assert len(http.calls) == 1


def test_failed_ensure_means_exactly_one_reverse_request_per_run(config_dir, monkeypatch, capsys):
    import weatherwise
    from conftest import NOW, OPEN_METEO as OM
    from ww_config import save_config
    from ww_http import HttpError
    save_config(config_dir, {"default": {k: v for k, v in TAIPEI_DEFAULT.items() if k != "country_code"}})
    http = FakeHttp({NOMINATIM_REVERSE: HttpError(429), "https://api.open-meteo.com": OM})
    weatherwise.run_weather([], http, NOW)
    assert sum(u.startswith(NOMINATIM_REVERSE) for u, _ in http.calls) == 1


def test_default_with_country_makes_no_request():
    d = {**TAIPEI_DEFAULT, "country_code": "tw", "region": "臺北市", "locality": "信義區"}
    place = resolve_place(None, {"default": d}, "zh-TW", False, FakeHttp({}))
    assert (place.country_code, place.region, place.locality) == ("tw", "臺北市", "信義區")


def test_old_weatherkit_country_code_in_config_is_accepted(config_dir):
    from ww_config import save_config
    save_config(config_dir, {"weatherkit": {"team_id": "T", "key_id": "K", "service_id": "S",
                                            "key_path": "/x.p8", "country_code": "TW"},
                             "default": {**TAIPEI_DEFAULT, "country_code": "tw"}})
    assert load_config(config_dir)["weatherkit"]["country_code"] == "TW"


def test_non_string_country_code_in_default_is_rejected(config_dir):
    from ww_config import save_config
    save_config(config_dir, {"default": {**TAIPEI_DEFAULT, "country_code": 886}})
    with pytest.raises(WwError) as e:
        load_config(config_dir)
    assert e.value.code == "config_invalid"


def test_failed_suffix_retry_keeps_the_first_result():
    from ww_http import HttpError
    def route(url):
        if "%E5%8D%80" in url:
            raise HttpError(429)
        return PINGLIN_RESULTS
    p = geocode("坪林", "zh-TW", False, FakeHttp({NOMINATIM: route, NOMINATIM_REVERSE: HttpError(429)}))
    assert (p.region, p.locality) == ("苗栗縣", "卓蘭鎮")


@pytest.mark.parametrize("query,global_search", [("Springfield", False), ("坪林", True)])
def test_suffix_retry_only_for_cjk_taiwan_searches(query, global_search):
    http = FakeHttp({NOMINATIM: PINGLIN_RESULTS})
    geocode(query, "en", global_search, http)
    assert len(http.calls) == 1


def test_county_administered_city_has_the_county_as_region():
    # Real answer for 宜蘭市: town + county, no city
    yilan = [{"class": "boundary", "type": "administrative", "name": "宜蘭市", "display_name": "宜蘭市, 宜蘭縣, 臺灣",
              "lat": "24.7570", "lon": "121.7530",
              "address": {"town": "宜蘭市", "county": "宜蘭縣", "country": "臺灣", "country_code": "tw"}}]
    p = geocode("宜蘭市", "zh-TW", False, FakeHttp({NOMINATIM: yilan}))
    assert (p.region, p.locality) == ("宜蘭縣", "宜蘭市")


def test_district_is_the_county_outside_taiwan_and_none_in_taiwan():
    kreis = {"lat": "53.8", "lon": "10.37", "display_name": "Bad Oldesloe, Kreis Stormarn, Schleswig-Holstein, Deutschland",
             "address": {"town": "Bad Oldesloe", "county": "Kreis Stormarn", "state": "Schleswig-Holstein", "country_code": "de"}}
    p = geocode("Bad Oldesloe", "en", True, FakeHttp({NOMINATIM: [kreis], NOMINATIM_REVERSE: HttpError(429)}))
    assert (p.region, p.locality, p.district) == ("Schleswig-Holstein", "Bad Oldesloe", "Kreis Stormarn")
    berlin = {"lat": "52.5", "lon": "13.4", "display_name": "Berlin, Deutschland",
              "address": {"city": "Berlin", "state": "Berlin", "country_code": "de"}}
    assert geocode("Berlin", "en", True, FakeHttp({NOMINATIM: [berlin], NOMINATIM_REVERSE: HttpError(429)})).district == "Berlin"
    assert geocode("坪林", "zh-TW", False, FakeHttp({NOMINATIM: PINGLIN_MIXED})).district is None


BERLIN_DE = {"class": "place", "type": "city", "name": "Berlin", "display_name": "Berlin, Deutschland",
             "lat": "52.5170365", "lon": "13.3888599",
             "address": {"city": "Berlin", "state": "Berlin", "country": "Deutschland", "country_code": "de"}}
BERLIN_NH = {"class": "boundary", "type": "administrative", "name": "Berlin",
             "display_name": "Berlin, Coös County, New Hampshire, United States",
             "lat": "44.47", "lon": "-71.18",
             "address": {"city": "Berlin", "county": "Coös County", "state": "New Hampshire", "country_code": "us"}}


@pytest.mark.parametrize("global_search", [True, False])
def test_worldwide_search_keeps_the_importance_order(global_search):
    def route(url):
        return [] if "countrycodes=tw" in url else [BERLIN_DE, BERLIN_NH]
    p = geocode("Berlin", "en", global_search, FakeHttp({NOMINATIM: route, NOMINATIM_REVERSE: HttpError(429)}))
    assert p.country_code == "de"


BERLIN_ZH = {"lat": "52.5", "lon": "13.37", "display_name": "Tiergarten, 柏林, 德國",
             "address": {"suburb": "Tiergarten", "state": "柏林", "country": "德國", "country_code": "de"}}
BERLIN_LOCAL = {"lat": "52.5", "lon": "13.37", "display_name": "Tiergarten, Berlin, Deutschland",
                "address": {"suburb": "Tiergarten", "city": "Berlin", "state": "Berlin", "country_code": "de"}}


def test_abroad_fields_come_from_one_reverse_without_accept_language():
    http = FakeHttp({NOMINATIM: [BERLIN_ZH], NOMINATIM_REVERSE: BERLIN_LOCAL})
    p = geocode("Berlin", "zh-TW", True, http)
    reverse_calls = [u for u, _ in http.calls if u.startswith(NOMINATIM_REVERSE)]
    assert len(reverse_calls) == 1 and "accept-language" not in reverse_calls[0]
    assert (p.region, p.locality, p.country_code) == ("Berlin", "Tiergarten", "de")
    assert "柏林" in p.name  # the name stays in the user's language


def test_taiwan_search_makes_no_extra_request():
    http = FakeHttp({NOMINATIM: TAICHUNG})
    geocode("台中", "zh-TW", False, http)
    assert len(http.calls) == 1


def test_failed_local_lookup_keeps_the_user_language_fields():
    http = FakeHttp({NOMINATIM: [BERLIN_ZH], NOMINATIM_REVERSE: HttpError(429)})
    p = geocode("Berlin", "zh-TW", True, http)
    assert (p.region, p.locality) == ("柏林", "Tiergarten")


def test_coordinates_abroad_are_localized_too():
    http = FakeHttp({NOMINATIM_REVERSE: lambda u: BERLIN_LOCAL if "accept-language" not in u else BERLIN_ZH})
    p = resolve_place("52.5,13.37", {}, "zh-TW", False, http)
    assert p.region == "Berlin" and len(http.calls) == 2


def test_default_completion_abroad_is_localized(config_dir):
    cfg = {"default": {"name": "x", "lat": 52.5, "lon": 13.37, "timezone": "Europe/Berlin"}}
    http = FakeHttp({NOMINATIM_REVERSE: lambda u: BERLIN_LOCAL if "accept-language" not in u else BERLIN_ZH})
    ensure_default_complete(cfg, config_dir, "zh-TW", http)
    assert cfg["default"]["region"] == "Berlin"


# Real-shaped Nominatim answers (2026-10, reverse without accept-language)
HONG_KONG = {"lat": "22.28", "lon": "114.16",
             "display_name": "西半山 Mid-Levels West, 中西區 Central and Western District, 香港島 Hong Kong Island, 香港 Hong Kong, 中国",
             "address": {"quarter": "西半山 Mid-Levels West", "suburb": "中西區 Central and Western District",
                         "city_district": "香港島 Hong Kong Island", "city": "香港 Hong Kong", "region": "香港 Hong Kong",
                         "ISO3166-2-lvl3": "CN-HK", "country": "中国", "country_code": "cn"}}
OSAKA_KITA = {"lat": "34.7055", "lon": "135.4983", "display_name": "芝田一丁目, 北区, 大阪市, 大阪府, 530-0012, 日本",
              "address": {"neighbourhood": "芝田一丁目", "suburb": "北区", "city": "大阪市", "province": "大阪府",
                          "ISO3166-2-lvl4": "JP-27", "postcode": "530-0012", "country": "日本", "country_code": "jp"}}


def test_hong_kong_is_hk_not_mainland_china():
    p = geocode("香港", "zh-TW", True, FakeHttp({NOMINATIM: [HONG_KONG], NOMINATIM_REVERSE: HONG_KONG}))
    assert p.country_code == "hk"
    macau = {**HONG_KONG, "address": {**HONG_KONG["address"], "ISO3166-2-lvl3": "CN-MO"}}
    assert geocode("澳門", "zh-TW", True, FakeHttp({NOMINATIM: [macau], NOMINATIM_REVERSE: macau})).country_code == "mo"


def test_osaka_ward_keeps_the_city_for_jma_matching():
    p = geocode("大阪市北区", "ja", True, FakeHttp({NOMINATIM: [OSAKA_KITA], NOMINATIM_REVERSE: OSAKA_KITA}))
    assert (p.country_code, p.region, p.locality, p.district) == ("jp", "大阪府", "北区", "大阪市")


# Real Nominatim search answer with accept-language=zh-TW (2026-10-23): a town in a 郡, the prefecture
# in simplified characters, which JMA's area table never matches.
YAKUSHIMA_ZH = {"class": "boundary", "type": "administrative", "lat": "30.3580", "lon": "130.5280",
                "display_name": "屋久岛町, 熊毛郡, 鹿儿岛县, 日本",
                "address": {"town": "屋久岛町", "county": "熊毛郡", "province": "鹿儿岛县", "ISO3166-2-lvl4": "JP-46",
                            "country": "日本", "country_code": "jp"}}


def test_japan_prefecture_comes_from_the_iso_code():
    p = geocode("屋久島町", "zh-TW", True, FakeHttp({NOMINATIM: [YAKUSHIMA_ZH], NOMINATIM_REVERSE: HttpError(429)}))
    assert (p.region, p.district) == ("鹿児島県", "熊毛郡")


def test_japan_town_in_a_gun_without_a_province_is_not_filed_under_the_gun():
    no_province = {**YAKUSHIMA_ZH, "address": {k: v for k, v in YAKUSHIMA_ZH["address"].items() if k != "province"}}
    p = geocode("屋久島町", "zh-TW", True, FakeHttp({NOMINATIM: [no_province], NOMINATIM_REVERSE: HttpError(429)}))
    assert p.region == "鹿児島県"  # would otherwise be 熊毛郡


def test_japan_without_an_iso_code_keeps_the_old_logic():
    old = {**YAKUSHIMA_ZH, "address": {k: v for k, v in YAKUSHIMA_ZH["address"].items() if k != "ISO3166-2-lvl4"}}
    p = geocode("屋久島町", "zh-TW", True, FakeHttp({NOMINATIM: [old], NOMINATIM_REVERSE: HttpError(429)}))
    assert p.region == "鹿儿岛县"


def test_a_bare_fetcher_still_gets_one_pause_between_live_nominatim_requests(monkeypatch):
    berlin = {"display_name": "Berlin, Deutschland", "lat": "52.517", "lon": "13.389",
              "address": {"city": "Berlin", "state": "Berlin", "country_code": "de"}}
    sleeps = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    http = FakeHttp({NOMINATIM: lambda u: [] if "countrycodes" in u else [berlin], NOMINATIM_REVERSE: berlin})
    geocode("Berlin", "de", False, http)
    assert len(http.calls) == 3 and len(sleeps) == 2  # Taiwan, worldwide, reverse for local names


def test_default_abroad_with_a_country_but_no_district_is_localized_once(config_dir):
    cfg = {"default": {"name": "柏林", "lat": 52.5, "lon": 13.37, "timezone": "Europe/Berlin",
                       "country_code": "de", "region": "柏林", "locality": "Tiergarten"}}
    http = FakeHttp({NOMINATIM_REVERSE: BERLIN_LOCAL})
    ensure_default_complete(cfg, config_dir, "zh-TW", http)
    saved = load_config(config_dir)["default"]
    assert (saved["region"], saved["district"], saved["name"]) == ("Berlin", "Berlin", "柏林")
    assert len(http.calls) == 1 and "accept-language" not in http.calls[0][0]
    ensure_default_complete(load_config(config_dir), config_dir, "zh-TW", http)
    assert len(http.calls) == 1  # complete now: no further lookup


def test_taiwan_default_without_a_district_is_left_alone(config_dir):
    cfg = {"default": {**TAIPEI_DEFAULT, "region": "臺北市"}}
    ensure_default_complete(cfg, config_dir, "zh-TW", FakeHttp({}))  # any request would fail the test
