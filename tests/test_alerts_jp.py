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


def test_jma_special_warning_is_extreme():
    assert ww_alerts_jp.CODES["33"] == ("大雨特別警報", "rain", "extreme")
    assert ww_alerts_jp.CODES["08"][2] == "severe" and ww_alerts_jp.CODES["19"][2] == "moderate"


def test_jma_unknown_code_is_skipped():
    data = json.loads(fixture("jma_130000.json"))
    data["areaTypes"][0]["areas"][0]["warnings"] = [{"code": "99", "status": "発表"}, {"code": "15", "status": "発表"}]
    h = FakeHttp({ww_alerts_jp.AREA_URL: json.loads(fixture("jma_area.json")),
                  ww_alerts_jp.WARNING_URL.format("130000"): data})
    (alerts,) = run([CHIYODA], h)
    assert [a.key for a in alerts] == ["jma:1310100:15"]


def test_jma_one_request_per_office_for_two_tokyo_places():
    h = http()
    out = run([CHIYODA, CHUO, HACHIJO], h)
    assert len(out) == 3 and out[2]
    urls = [u for u, _ in h.calls]
    assert urls.count(ww_alerts_jp.WARNING_URL.format("130000")) == 1
    assert urls.count(ww_alerts_jp.AREA_URL) == 1


def test_jma_collect_integration():
    results, _ = ww_alerts.collect([CHIYODA], http(), NOW)
    assert results[0].status == "ok" and len(results[0].alerts) == 2
