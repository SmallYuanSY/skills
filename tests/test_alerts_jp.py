import json
from datetime import datetime, timedelta, timezone

import pytest

import ww_alerts
import ww_alerts_jp
from conftest import FakeHttp, fixture
from ww_model import Place

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
CHIYODA = Place("千代田区", 35.694, 139.754, "Asia/Tokyo", "jp", "東京", "千代田区")
CHUO = Place("中央区", 35.67, 139.77, "Asia/Tokyo", "jp", "東京", "中央区")
HACHIJO = Place("八丈町", 33.11, 139.79, "Asia/Tokyo", "jp", "東京", "八丈町")
NOWHERE = Place("どこか", 35.0, 139.0, "Asia/Tokyo", "jp", "東京", "存在しない市")
NO_LOCALITY = Place("東京", 35.68, 139.77, "Asia/Tokyo", "jp", "東京")


def http():
    return FakeHttp({ww_alerts_jp.AREA_URL: json.loads(fixture("jma_area.json")),
                     ww_alerts_jp.WARNING_URL.format("130000"): json.loads(fixture("jma_130000.json"))})


def run(places, h=None):
    return ww_alerts_jp.alerts_for(places, h or http(), NOW)


def test_jma_finds_chiyoda_by_municipality_name():
    (alerts,) = run([CHIYODA])
    assert alerts and all(a.key.startswith("jma:1310100:") for a in alerts)


def test_jma_matches_without_the_trailing_suffix():
    p = Place("千代田", 35.694, 139.754, "Asia/Tokyo", "jp", "東京", "千代田")
    (alerts,) = run([p])
    assert alerts


def test_jma_unknown_municipality_is_none():
    assert run([NOWHERE, NO_LOCALITY]) == [None, None]


def test_jma_lists_active_warning_with_severity():
    (alerts,) = run([CHIYODA])
    by_key = {a.key: a for a in alerts}
    heavy = by_key["jma:1310100:03"]
    assert (heavy.kind, heavy.severity, heavy.title) == ("rain", "severe", "大雨警報")
    assert heavy.source == "jma" and heavy.expires is None
    assert heavy.updated == datetime.fromisoformat("2026-05-28T10:16:00+09:00")
    assert 0 < len(heavy.summary) <= 60
    wind = by_key["jma:1310100:15"]
    assert (wind.kind, wind.severity, wind.title) == ("wind", "moderate", "強風注意報")


def test_jma_skips_cleared_warnings():
    (alerts,) = run([CHIYODA])
    assert sorted(a.key for a in alerts) == ["jma:1310100:03", "jma:1310100:15"]  # 16 cleared, none-entry skipped


def test_jma_place_without_warnings_is_empty_not_none():
    assert run([CHUO]) == [[]]


def with_warnings(warnings):
    data = json.loads(fixture("jma_130000.json"))
    data["areaTypes"][0]["areas"][0]["warnings"] = warnings
    return FakeHttp({ww_alerts_jp.AREA_URL: json.loads(fixture("jma_area.json")),
                     ww_alerts_jp.WARNING_URL.format("130000"): data})


def test_jma_special_warning_is_extreme():
    (alerts,) = run([CHIYODA], with_warnings([{"code": "33", "status": "発表"}]))
    assert (alerts[0].title, alerts[0].kind, alerts[0].severity) == ("大雨特別警報", "rain", "extreme")


def test_jma_thunder_advisory_is_listed():
    (alerts,) = run([CHIYODA], with_warnings([{"code": "14", "status": "継続"}]))
    assert [(a.title, a.kind, a.severity) for a in alerts] == [("雷注意報", "thunder", "moderate")]


def test_jma_unknown_code_is_listed_not_dropped():
    (alerts,) = run([CHIYODA], with_warnings([{"code": "99", "status": "発表"}, {"code": "09", "status": "発表"}]))
    assert [(a.title, a.kind, a.severity) for a in alerts] == [
        ("気象注意報 (code 99)", "other", "extreme"), ("気象注意報 (code 09)", "other", "severe")]


def test_jma_same_name_in_several_prefectures_is_picked_by_region():
    area = json.loads(fixture("jma_area.json"))
    area["offices"]["270000"] = {"name": "大阪府", "parent": "010300"}
    area["class10s"]["270010"] = {"name": "x", "parent": "270000"}
    area["class15s"]["270011"] = {"name": "y", "parent": "270010"}
    area["class20s"]["2712000"] = {"name": "中央区", "parent": "270011"}
    routes = {ww_alerts_jp.AREA_URL: area, ww_alerts_jp.WARNING_URL.format("130000"): json.loads(fixture("jma_130000.json")),
              ww_alerts_jp.WARNING_URL.format("270000"): {"reportDatetime": "2026-10-22T10:00:00+09:00", "areaTypes": []}}
    assert ww_alerts_jp.alerts_for([CHUO], FakeHttp(routes), NOW) == [[]]
    osaka = Place("中央区", 34.68, 135.52, "Asia/Tokyo", "jp", "大阪", "中央区")
    no_region = Place("中央区", 34.68, 135.52, "Asia/Tokyo", "jp", None, "中央区")
    assert ww_alerts_jp.alerts_for([osaka, no_region], FakeHttp(routes), NOW) == [[], None]
    h = FakeHttp(routes)
    ww_alerts_jp.alerts_for([osaka], h, NOW)
    assert [u for u, _ in h.calls][-1].endswith("/270000.json")


def test_jma_one_request_per_office_for_two_tokyo_places():
    h = http()
    out = run([CHIYODA, CHUO, HACHIJO], h)
    assert len(out) == 3 and out[2]
    urls = [u for u, _ in h.calls]
    assert urls.count(ww_alerts_jp.WARNING_URL.format("130000")) == 1
    assert urls.count(ww_alerts_jp.AREA_URL) == 1


def test_jma_collect_integration():
    results, _, _ = ww_alerts.collect([CHIYODA], http(), NOW)
    assert results[0].status == "ok" and len(results[0].alerts) == 2


# Places as Nominatim describes them (locality = ward or town, district = city, region = prefecture);
# the JMA entries in the fixture are trimmed from the real area.json.
def place(region, locality, district=None):
    return Place(locality, 35.0, 135.0, "Asia/Tokyo", "jp", region, locality, district)


def area():
    return json.loads(fixture("jma_area.json"))


def match(p):
    m = ww_alerts_jp._match(area(), p)
    return m and (m[0], m[1])


def test_jma_osaka_ward_is_osaka_city_not_tokyo_kita():
    assert match(place("大阪府", "北区", "大阪市")) == (["2710000"], "270000")
    assert match(place("大阪府", "北区")) is None  # never Tokyo's 北区


def test_jma_sapporo_ward_is_sapporo_city():
    assert match(place("北海道", "中央区", "札幌市")) == (["0110000"], "016000")


def test_jma_kyoto_ward_falls_back_to_kyoto_city():
    assert match(place("京都府", "中京区", "京都市")) == (["2610000"], "260000")


def test_jma_kobe_ward_matches_city_and_ward_name():
    assert match(place("兵庫県", "北区", "神戸市")) == (["2810900"], "280000")


def test_jma_yokohama_is_kanagawa_never_aomori():
    m = match(place("神奈川県", "西区", "横浜市"))
    assert m == (["1410011", "1410012"], "140000")  # JMA splits the city in two; we cannot tell which half
    assert match(place("神奈川県", "横浜市", "横浜市")) == m


def test_jma_tokyo_still_matches_with_full_and_short_prefecture_name():
    assert match(place("東京都", "千代田区", "千代田区")) == (["1310100"], "130000")
    assert match(place("東京", "北区")) == (["1311700"], "130000")


def test_jma_unknown_prefecture_is_none():
    assert match(place("どこか県", "千代田区")) is None


def test_jma_split_city_lists_each_warning_once():
    report = {"reportDatetime": "2026-10-22T10:00:00+09:00", "headlineText": "",
              "areaTypes": [{"areas": [
                  {"code": "1410011", "warnings": [{"code": "03", "status": "発表"}, {"code": "15", "status": "発表"}]},
                  {"code": "1410012", "warnings": [{"code": "03", "status": "継続"}]}]}]}
    h = FakeHttp({ww_alerts_jp.AREA_URL: area(), ww_alerts_jp.WARNING_URL.format("140000"): report})
    (alerts,) = ww_alerts_jp.alerts_for([place("神奈川県", "西区", "横浜市")], h, NOW)
    assert sorted(a.title for a in alerts) == ["大雨警報", "強風注意報"]
