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
