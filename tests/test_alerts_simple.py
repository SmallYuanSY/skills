import json
from datetime import datetime, timezone

import ww_alerts
import ww_alerts_hk
import ww_alerts_us
from conftest import FakeHttp, fixture
from ww_model import Place

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
HK1 = Place("香港", 22.32, 114.17, "Asia/Hong_Kong", "hk")
HK2 = Place("九龍", 22.31, 114.18, "Asia/Hong_Kong", "hk")
NYC = Place("紐約", 40.7128, -74.006, "America/New_York", "us", "New York")
FLAGSTAFF = Place("Flagstaff", 36.0633, -111.4152, "America/Phoenix", "us", "Arizona")


def hko(data=None):
    return FakeHttp({ww_alerts_hk.URL: json.loads(fixture("hko_warnsum.json")) if data is None else data})


def test_hko_empty_is_no_alerts():
    assert ww_alerts_hk.alerts_for([HK1], hko({}), NOW) == [[]]


def test_hko_signal_8_is_severe_typhoon():
    (alerts,) = ww_alerts_hk.alerts_for([HK1], hko(), NOW)
    by_key = {a.key: a for a in alerts}
    signal = by_key["hko:TC8NE"]
    assert (signal.kind, signal.severity, signal.title) == ("typhoon", "severe", "八號東北烈風或暴風信號")
    assert signal.expires is None and signal.updated.utcoffset().total_seconds() == 8 * 3600
    rain = by_key["hko:WRAINA"]
    assert (rain.kind, rain.severity) == ("rain", "moderate")
    assert rain.expires == datetime.fromisoformat("2026-10-22T10:15:00+08:00")


def test_hko_unknown_code_is_still_listed():
    h = hko({"WNEW": {"name": "新警告", "code": "WNEW1", "updateTime": "2026-10-22T07:15:00+08:00"}})
    (alerts,) = ww_alerts_hk.alerts_for([HK1], h, NOW)
    assert [(a.kind, a.title, a.key) for a in alerts] == [("other", "新警告", "hko:WNEW1")]


def test_hko_one_request_for_two_places():
    h = hko()
    out = ww_alerts_hk.alerts_for([HK1, HK2], h, NOW)
    assert len(h.calls) == 1 and len(out) == 2 and out[0] and out[0] == out[1]


def nws(features):
    return FakeHttp({"https://api.weather.gov/alerts/active": {"features": features}})


def feature(**props):
    base = {"id": "urn:x:1", "event": "Flood Watch", "severity": "Severe", "headline": "h", "description": "d",
            "expires": "2026-10-22T23:00:00-07:00", "sent": "2026-10-22T05:53:00-07:00"}
    return {"properties": {**base, **props}}


def test_nws_maps_fields():
    h = FakeHttp({"https://api.weather.gov/alerts/active": json.loads(fixture("nws_point.json"))})
    (alerts,) = ww_alerts_us.alerts_for([FLAGSTAFF], h, NOW)
    a = next(a for a in alerts if a.title == "Flood Watch")
    assert (a.kind, a.severity, a.source) == ("flood", "severe", "nws")
    assert a.key.startswith("nws:") and a.expires.utcoffset() is not None
    assert 0 < len(a.summary) <= 60 and a.detail and a.detail != a.summary
    assert h.calls[0][0].endswith("point=36.0633,-111.4152")


def test_nws_unknown_severity_is_minor_and_ends_replaces_expires():
    h = nws([feature(severity="Unknown", expires=None, ends="2026-10-23T01:00:00+00:00", headline="x" * 90)])
    (alerts,) = ww_alerts_us.alerts_for([NYC], h, NOW)
    assert alerts[0].severity == "minor" and len(alerts[0].summary) == 60
    assert alerts[0].expires == datetime(2026, 10, 23, 1, tzinfo=timezone.utc)


def test_nws_one_request_per_place():
    h = nws([])
    out = ww_alerts_us.alerts_for([NYC, FLAGSTAFF], h, NOW)
    assert out == [[], []] and len(h.calls) == 2
    assert h.calls[0][0].endswith("point=40.7128,-74.0060")


def test_nws_hurricane_is_typhoon_kind():
    h = nws([feature(event="Hurricane Warning"), feature(id="urn:x:2", event="Tropical Storm Watch"),
             feature(id="urn:x:3", event="Special Weather Statement")])
    (alerts,) = ww_alerts_us.alerts_for([NYC], h, NOW)
    assert [a.kind for a in alerts] == ["typhoon", "typhoon", "other"]


def test_providers_registered():
    assert ww_alerts.PROVIDERS["hk"] is ww_alerts_hk.alerts_for
    assert ww_alerts.PROVIDERS["us"] is ww_alerts_us.alerts_for


def test_hko_signal_title_is_the_specific_signal_from_type():
    (alerts,) = ww_alerts_hk.alerts_for([HK1], hko(), NOW)
    assert "八號東北烈風或暴風信號" in {a.title for a in alerts}


def test_hko_cancel_entries_are_skipped():
    h = hko({"WTCSGNL": {"name": "熱帶氣旋警告信號", "code": "CANCEL", "actionCode": "CANCEL"},
             "WRAIN": {"name": "黃色暴雨警告信號", "code": "WRAINA", "actionCode": "CANCEL"}})
    assert ww_alerts_hk.alerts_for([HK1], h, NOW) == [[]]


def test_hko_missing_expire_time_is_none():
    h = hko({"WHOT": {"name": "酷熱天氣警告", "code": "WHOT", "updateTime": "2026-10-22T07:00:00+08:00"}})
    (alerts,) = ww_alerts_hk.alerts_for([HK1], h, NOW)
    assert alerts[0].expires is None and alerts[0].kind == "heat"


def test_hko_landslip_and_tsunami_are_not_listed():
    h = hko({"WL": {"name": "山泥傾瀉警告", "code": "WL"}, "WTMW": {"name": "海嘯警告", "code": "WTMW"},
             "WTCPRE8": {"name": "預警八號熱帶氣旋警告信號之通知", "code": "WTCPRE8"}})
    (alerts,) = ww_alerts_hk.alerts_for([HK1], h, NOW)
    assert [(a.key, a.kind) for a in alerts] == [("hko:WTCPRE8", "typhoon")]


def test_nws_non_weather_events_are_dropped():
    h = nws([feature(event="Earthquake Warning", category="Geo"),
             feature(id="urn:x:2", event="Civil Emergency Message", category="Safety"),
             feature(id="urn:x:3", event="Tsunami Warning"),  # no category: the name check catches it
             feature(id="urn:x:4", event="Flood Watch", category="Met")])
    (alerts,) = ww_alerts_us.alerts_for([NYC], h, NOW)
    assert [a.title for a in alerts] == ["Flood Watch"]


def test_nws_kind_keywords():
    h = nws([feature(event="Hurricane Force Wind Warning"), feature(id="urn:x:2", event="Extreme Cold Warning"),
             feature(id="urn:x:3", event="Hurricane Watch")])
    (alerts,) = ww_alerts_us.alerts_for([NYC], h, NOW)
    assert [a.kind for a in alerts] == ["wind", "cold", "typhoon"]


def test_nws_malformed_feature_is_skipped_not_fatal():
    bad_id = feature()
    del bad_id["properties"]["id"]
    h = nws([bad_id, feature(id="urn:x:2", expires="2026-10-22T23:00:00"),
             feature(id="urn:x:3", expires="not a time"), feature(id="urn:x:4")])
    (alerts,) = ww_alerts_us.alerts_for([NYC], h, NOW)
    assert [a.key for a in alerts] == ["nws:urn:x:4"]


def test_nws_failed_point_is_unavailable_for_that_place_only():
    from ww_http import HttpError
    h = FakeHttp({"https://api.weather.gov/alerts/active?point=36.0633": HttpError(500),
                  "https://api.weather.gov/alerts/active": {"features": []}})
    ny, flag = ww_alerts_us.alerts_for([NYC, FLAGSTAFF], h, NOW)
    assert ny == [] and isinstance(flag, HttpError)
    res, _, _ = ww_alerts.collect([NYC, FLAGSTAFF], h, NOW)
    assert (res[0].status, res[1].status, res[1].reason) == ("ok", "unavailable", "us HTTP 500")
