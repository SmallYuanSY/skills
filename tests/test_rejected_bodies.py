"""A body the provider rejects (rate-limit page, garbage) must never be served from the cache."""
import json
from datetime import datetime, timezone

import pytest

import ww_alerts
import ww_alerts_ca
import ww_alerts_eu
import ww_alerts_hk
import ww_alerts_jp
import ww_alerts_tw
import ww_alerts_us
import ww_cyclones
from conftest import FakeHttp, fixture
from ww_cache import Cached
from ww_model import Place

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
TS = int(NOW.timestamp())
BANQIAO = Place("板橋", 25.01, 121.46, "Asia/Taipei", "tw", "新北市", "板橋區")
RATE_LIMITED = "<WarningMessage><Warning>限制存取間隔時間為3秒</Warning></WarningMessage>"


def ncdr_run(body, ts, d):
    h = FakeHttp({ww_alerts_tw.FEED: body, ww_cyclones.LIST_URL: {"features": []}})
    res, *_ = ww_alerts.collect([BANQIAO], Cached(h, ts, d), NOW)
    return res[0], h


def test_rate_limited_ncdr_is_refetched_by_the_next_run(tmp_path):
    first, _ = ncdr_run(RATE_LIMITED, TS, tmp_path)
    assert first.status == "unavailable" and first.reason == "service_error: ncdr rate limited"
    second, h = ncdr_run(fixture("ncdr.xml"), TS + 120, tmp_path)
    assert second.status == "ok" and ww_alerts_tw.FEED in [u for u, _ in h.calls]


def test_rate_limited_ncdr_serves_the_last_good_copy(tmp_path):
    ncdr_run(fixture("ncdr.xml"), TS, tmp_path)
    again, _ = ncdr_run(RATE_LIMITED, TS + 400, tmp_path)
    assert again.status == "ok" and again.alerts


def test_unparseable_ncdr_is_not_cached(tmp_path):
    ncdr_run("<html>busy", TS, tmp_path)
    _, h = ncdr_run(fixture("ncdr.xml"), TS + 60, tmp_path)
    assert ww_alerts_tw.FEED in [u for u, _ in h.calls]


TOKYO = Place("千代田区", 35.694, 139.754, "Asia/Tokyo", "jp", "東京都", "千代田区")
NEW_YORK = Place("New York", 40.71, -74.0, "America/New_York", "us", "New York", "Manhattan")
TORONTO = Place("Toronto", 43.65, -79.38, "America/Toronto", "ca", "Ontario", "Toronto")
BERLIN = Place("Berlin", 52.52, 13.4, "Europe/Berlin", "de", "Berlin", "Mitte", "Berlin")
HONG_KONG = Place("香港", 22.28, 114.16, "Asia/Hong_Kong", "hk", "香港", "中西區")
ECCC = "https://api.weather.gc.ca/collections/weather-alerts/items"
CASES = [
    (ww_alerts_jp.alerts_for, TOKYO, {ww_alerts_jp.AREA_URL: json.loads(fixture("jma_area.json"))},
     ww_alerts_jp.WARNING_URL.format("130000")),
    (ww_alerts_jp.alerts_for, TOKYO, {ww_alerts_jp.WARNING_URL.format("130000"): json.loads(fixture("jma_130000.json"))},
     ww_alerts_jp.AREA_URL),
    (ww_alerts_us.alerts_for, NEW_YORK, {}, "https://api.weather.gov/alerts/active"),
    (ww_alerts_ca.alerts_for, TORONTO, {}, ECCC),
    (ww_alerts_eu.alerts_for, BERLIN, {}, ww_alerts_eu.URL.format("germany")),
    (ww_alerts_hk.alerts_for, HONG_KONG, {}, ww_alerts_hk.URL),
]


@pytest.mark.parametrize("provider,place,routes,bad_url", CASES)
def test_rejected_json_body_is_evicted(tmp_path, provider, place, routes, bad_url):
    c = Cached(FakeHttp({**routes, bad_url: "Too Many Requests"}), TS, tmp_path)
    try:
        (got,) = provider([place], c, NOW)
    except Exception:
        got = None
    else:
        assert isinstance(got, Exception)  # NWS reports a failed point per place
    assert not any(u.startswith(bad_url) for u, _ in c.memo)
    assert not Cached(FakeHttp({}), TS + 1, tmp_path).is_fresh(next(u for u, _ in c.http.calls if u.startswith(bad_url)))


def test_rejected_gdacs_list_is_evicted(tmp_path):
    c = Cached(FakeHttp({ww_cyclones.LIST_URL: "Too Many Requests"}), TS, tmp_path)
    with pytest.raises(Exception):
        ww_cyclones.nearby([BANQIAO], c, NOW)
    assert not Cached(FakeHttp({}), TS + 1, tmp_path).is_fresh(ww_cyclones.LIST_URL)


# An error object served with HTTP 200 must read as "unavailable", never as "no alerts".
ERROR_JSON = {"error": "Service temporarily unavailable"}
JMA_AREA = json.loads(fixture("jma_area.json"))
JMA_130000 = json.loads(fixture("jma_130000.json"))
ERROR_CASES = [
    ("jma area", TOKYO, {ww_alerts_jp.WARNING_URL.format("130000"): JMA_130000}, ww_alerts_jp.AREA_URL, ERROR_JSON),
    ("jma warnings", TOKYO, {ww_alerts_jp.AREA_URL: JMA_AREA}, ww_alerts_jp.WARNING_URL.format("130000"), ERROR_JSON),
    ("jma warnings empty", TOKYO, {ww_alerts_jp.AREA_URL: JMA_AREA}, ww_alerts_jp.WARNING_URL.format("130000"), {}),
    ("nws", NEW_YORK, {}, "https://api.weather.gov/alerts/active", ERROR_JSON),
    ("nws empty", NEW_YORK, {}, "https://api.weather.gov/alerts/active", {}),
    ("eccc", TORONTO, {}, ECCC, ERROR_JSON),
    ("meteoalarm", BERLIN, {}, ww_alerts_eu.URL.format("germany"), ERROR_JSON),
    ("meteoalarm empty", BERLIN, {}, ww_alerts_eu.URL.format("germany"), {}),
    ("hko", HONG_KONG, {}, ww_alerts_hk.URL, ERROR_JSON),
    ("hko error object", HONG_KONG, {}, ww_alerts_hk.URL, {"error": {"code": 503, "message": "busy"}}),
    ("ncdr", BANQIAO, {}, ww_alerts_tw.FEED, "<?xml version='1.0'?><Error><Message>busy</Message></Error>"),
]


@pytest.mark.parametrize("label,place,routes,bad_url,body", ERROR_CASES, ids=[c[0] for c in ERROR_CASES])
def test_error_shaped_body_is_unavailable_not_none(tmp_path, label, place, routes, bad_url, body):
    h = FakeHttp({**routes, bad_url: body, ww_cyclones.LIST_URL: {"features": []}})
    c = Cached(h, TS, tmp_path)
    (got,), *_ = ww_alerts.collect([place], c, NOW)
    assert got.status == "unavailable"
    url = next(u for u, _ in h.calls if u.startswith(bad_url))
    assert not Cached(FakeHttp({}), TS + 1, tmp_path).is_fresh(url, text=isinstance(body, str))


def test_error_shaped_body_falls_back_to_the_last_good_copy(tmp_path):
    good = {"type": "FeatureCollection", "features": []}
    url = "https://api.weather.gov/alerts/active"
    ww_alerts.collect([NEW_YORK], Cached(FakeHttp({url: good, ww_cyclones.LIST_URL: {"features": []}}), TS, tmp_path), NOW)
    h = FakeHttp({url: ERROR_JSON, ww_cyclones.LIST_URL: {"features": []}})
    (got,), *_ = ww_alerts.collect([NEW_YORK], Cached(h, TS + 400, tmp_path), NOW)
    assert got.status == "ok" and got.alerts == []


def test_hko_empty_summary_is_still_no_warnings(tmp_path):
    h = FakeHttp({ww_alerts_hk.URL: {}, ww_cyclones.LIST_URL: {"features": []}})
    (got,), *_ = ww_alerts.collect([HONG_KONG], Cached(h, TS, tmp_path), NOW)
    assert (got.status, got.alerts) == ("ok", [])


@pytest.mark.parametrize("body", [ERROR_JSON, {}])
def test_error_shaped_gdacs_list_is_cyclones_unavailable(tmp_path, body):
    h = FakeHttp({ww_alerts_tw.FEED: fixture("ncdr.xml"), ww_cyclones.LIST_URL: body})
    got = ww_alerts.collect([BANQIAO], Cached(h, TS, tmp_path), NOW)
    assert got.cyclone_error is not None
    assert not Cached(FakeHttp({}), TS + 1, tmp_path).is_fresh(ww_cyclones.LIST_URL)


def test_error_shaped_gdacs_geometry_is_not_cached_and_gives_no_track(tmp_path):
    geo = "https://www.gdacs.org/gdacsapi/api/polygons/getgeometry?eventtype=TC&eventid=1001338&episodeid=33"
    h = FakeHttp({ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")), geo: ERROR_JSON})
    found = ww_cyclones.nearby([BANQIAO], Cached(h, TS, tmp_path), NOW)
    assert found and found[0][0].track == []
    assert not Cached(FakeHttp({}), TS + 1, tmp_path).is_fresh(geo)
