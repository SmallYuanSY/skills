import pytest

from conftest import TAIPEI_DEFAULT, FakeHttp
from ww_errors import WwError
from ww_model import Place
from ww_places import NOMINATIM, OPEN_METEO, resolve_place, with_timezone

TAICHUNG = [{"display_name": "臺中市, 40001, 臺灣", "lat": "24.1477", "lon": "120.6736"}]


def test_no_query_uses_the_default():
    place = resolve_place(None, {"default": TAIPEI_DEFAULT}, "zh-TW", False, FakeHttp({}))
    assert place == Place("台北市", 25.033, 121.565, "Asia/Taipei")


def test_no_query_and_no_default_asks_for_a_place():
    with pytest.raises(WwError) as e:
        resolve_place(None, {}, "zh-TW", False, FakeHttp({}))
    assert e.value.code == "no_default_location"


@pytest.mark.parametrize("query", ["24.15,120.67", " 24.15 , 120.67 "])
def test_coordinates_skip_geocoding(query):
    place = resolve_place(query, {}, "zh-TW", False, FakeHttp({}))
    assert (place.lat, place.lon, place.timezone) == (24.15, 120.67, None)


@pytest.mark.parametrize("query", ["200,10", "10,-181"])
def test_out_of_range_coordinates_are_rejected(query):
    with pytest.raises(WwError) as e:
        resolve_place(query, {}, "zh-TW", False, FakeHttp({}))
    assert e.value.code == "place_not_found"


def test_place_name_searches_taiwan_first_and_drops_postcodes():
    http = FakeHttp({NOMINATIM: TAICHUNG})
    place = resolve_place("台中", {}, "zh-TW", False, http)
    assert place == Place("臺中市, 臺灣", 24.1477, 120.6736)
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
