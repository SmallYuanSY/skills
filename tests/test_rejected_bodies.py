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
