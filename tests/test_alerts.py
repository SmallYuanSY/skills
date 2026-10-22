from datetime import datetime, timedelta, timezone

import pytest

import ww_alerts
import ww_cyclones
from conftest import NOW
from ww_errors import WwError
from ww_http import HttpError
from ww_model import Alert, Cyclone, Place

BANQIAO = Place("板橋", 25.01, 121.46, "Asia/Taipei", "tw")
PINGLIN = Place("坪林", 24.94, 121.71, "Asia/Taipei", "tw")
TOKYO = Place("東京", 35.68, 139.69, "Asia/Tokyo", "jp")
SEOUL = Place("Seoul", 37.57, 126.98, "Asia/Seoul", "kr")


def alert(key="k", severity="minor", updated=0, expires=1, kind="rain", title="t", detail=""):
    return Alert(kind, severity, title, "s", detail, NOW + timedelta(hours=expires),
                 NOW + timedelta(minutes=updated), "ncdr", key)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(ww_alerts, "PROVIDERS", {})
    monkeypatch.setattr(ww_cyclones, "nearby", lambda places, http, now: [])


def test_each_provider_is_called_once_for_all_its_places(monkeypatch):
    calls = []

    def tw(places, http, now):
        calls.append(places)
        return [[] for _ in places]

    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", tw)
    res, _ = ww_alerts.collect([BANQIAO, TOKYO, PINGLIN], None, NOW)
    assert len(calls) == 1 and calls[0] == [BANQIAO, PINGLIN]
    assert [r.status for r in res] == ["ok", "unsupported", "ok"]


def test_country_without_provider_is_unsupported():
    res, _ = ww_alerts.collect([SEOUL], None, NOW)
    assert res[0].status == "unsupported" and res[0].alerts == []


def test_place_without_country_is_unsupported():
    res, _ = ww_alerts.collect([Place("x", 0.0, 0.0)], None, NOW)
    assert res[0].status == "unsupported"


def test_provider_none_result_is_unsupported(monkeypatch):
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [None])
    res, _ = ww_alerts.collect([BANQIAO], None, NOW)
    assert res[0].status == "unsupported"


def test_provider_crash_marks_unavailable_not_internal_error(monkeypatch):
    def boom(places, http, now):
        raise ValueError("bad")

    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", boom)
    res, _ = ww_alerts.collect([BANQIAO, PINGLIN], None, NOW)
    assert all(r.status == "unavailable" and "ValueError" in r.reason for r in res)


def test_reason_for_http_and_ww_errors(monkeypatch):
    def http_500(places, http, now):
        raise HttpError(500)

    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", http_500)
    assert ww_alerts.collect([BANQIAO], None, NOW)[0][0].reason == "tw HTTP 500"

    def ww(places, http, now):
        raise WwError("network_error")

    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", ww)
    assert ww_alerts.collect([BANQIAO], None, NOW)[0][0].reason == "network_error"


def test_expired_alerts_are_dropped(monkeypatch):
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [[alert("a", expires=-1), alert("b", expires=1)]])
    res, _ = ww_alerts.collect([BANQIAO], None, NOW)
    assert [a.key for a in res[0].alerts] == ["b"]


def test_only_the_newest_alert_per_key_is_kept(monkeypatch):
    three = [alert("w", updated=5, title="mid"), alert("w", updated=30, title="new"), alert("w", updated=1, title="old")]
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [three])
    res, _ = ww_alerts.collect([BANQIAO], None, NOW)
    assert [a.title for a in res[0].alerts] == ["new"]


def test_alerts_sorted_by_severity(monkeypatch):
    mixed = [alert("a", "minor"), alert("b", "extreme"), alert("c", "moderate"), alert("d", "severe")]
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [mixed])
    res, _ = ww_alerts.collect([BANQIAO], None, NOW)
    assert [a.severity for a in res[0].alerts] == ["extreme", "severe", "moderate", "minor"]


CHAMPI = Cyclone("CHAMPI-26", "Orange", 21.2, 125.0, [], [], "")


def test_cyclone_named_in_a_local_alert_is_merged(monkeypatch):
    ty = alert("ty", "severe", kind="typhoon", title="薔琵颱風海上警報", detail="…國際命名 champi…")
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [[ty]])
    monkeypatch.setattr(ww_cyclones, "nearby", lambda p, h, n: [(CHAMPI, [0])])
    res, cyclones = ww_alerts.collect([BANQIAO], None, NOW)
    assert cyclones == []
    assert res[0].alerts[0].cyclone.name == "CHAMPI-26"


def test_cyclone_not_named_locally_is_listed_on_its_own(monkeypatch):
    ty = alert("ty", kind="typhoon", title="某颱風", detail="國際命名 OTHER")
    rain = alert("r", kind="rain", detail="CHAMPI")  # not a typhoon alert, no merge
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [[ty, rain]])
    monkeypatch.setattr(ww_cyclones, "nearby", lambda p, h, n: [(CHAMPI, [0])])
    res, cyclones = ww_alerts.collect([BANQIAO], None, NOW)
    assert cyclones == [(CHAMPI, [0])]
    assert all(a.cyclone is None for a in res[0].alerts)


def test_cyclone_merge_is_per_place(monkeypatch):
    ty = alert("ty", kind="typhoon", detail="CHAMPI")
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [[ty], []])
    monkeypatch.setattr(ww_cyclones, "nearby", lambda p, h, n: [(CHAMPI, [0, 1])])
    _, cyclones = ww_alerts.collect([BANQIAO, PINGLIN], None, NOW)
    assert cyclones == [(CHAMPI, [1])]


def test_gdacs_failure_does_not_change_alert_status(monkeypatch):
    def boom(p, h, n):
        raise HttpError(503)

    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [[alert("a")]])
    monkeypatch.setattr(ww_cyclones, "nearby", boom)
    res, cyclones = ww_alerts.collect([BANQIAO], None, NOW)
    assert res[0].status == "ok" and len(res[0].alerts) == 1 and cyclones == []


def test_naive_datetime_from_a_provider_marks_the_country_unavailable(monkeypatch):
    naive = Alert("rain", "minor", "t", "s", "", datetime(2030, 1, 1), None, "ncdr", "k")
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [[naive]])
    res, _ = ww_alerts.collect([BANQIAO], None, NOW)
    assert res[0].status == "unavailable" and "TypeError" in res[0].reason


def test_cyclone_with_an_empty_local_name_never_merges(monkeypatch):
    ty = alert("ty", kind="typhoon", title="某颱風", detail="anything")
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [[ty]])
    nameless = Cyclone("-26", "Orange", 21.2, 125.0, [], [], "")
    monkeypatch.setattr(ww_cyclones, "nearby", lambda p, h, n: [(nameless, [0])])
    res, cyclones = ww_alerts.collect([BANQIAO], None, NOW)
    assert cyclones == [(nameless, [0])] and res[0].alerts[0].cyclone is None


def test_collect_dedupes_two_versions_of_one_key(monkeypatch):
    versions = [alert("ncdr:強風", updated=1, title="old"), alert("ncdr:強風", updated=9, title="new")]
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", lambda p, h, n: [versions])
    res, _ = ww_alerts.collect([BANQIAO], None, NOW)
    assert [a.title for a in res[0].alerts] == ["new"]
