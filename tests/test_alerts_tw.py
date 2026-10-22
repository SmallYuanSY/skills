from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import ww_alerts
import ww_alerts_tw
import ww_cyclones
from conftest import FakeHttp, fixture
from ww_errors import WwError
from ww_model import Place

TPE = ZoneInfo("Asia/Taipei")
NCDR_NOW = datetime(2026, 10, 22, 20, 30, tzinfo=TPE)
BANQIAO = Place("板橋區", 25.011, 121.459, "Asia/Taipei", "tw", "新北市", "板橋區")
JIAOXI = Place("礁溪鄉", 24.827, 121.775, "Asia/Taipei", "tw", "宜蘭縣", "礁溪鄉")
NANTOU = Place("x", 23.9, 120.69, "Asia/Taipei", "tw", "南投縣", "x")  # not in the rain list
NO_REGION = Place("板橋", 25.01, 121.46, "Asia/Taipei", "tw")


def http():
    return FakeHttp({ww_alerts_tw.FEED: fixture("ncdr.xml")})


def run(places):
    return ww_alerts_tw.alerts_for(places, http(), NCDR_NOW)


def kinds(alerts):
    return sorted(a.kind for a in alerts)


def test_ncdr_keeps_only_cwa_weather_alerts():
    (alerts,) = run([BANQIAO])
    assert alerts and all(a.source == "ncdr" and a.key.startswith("ncdr:") for a in alerts)
    assert not any("道路" in a.title + a.detail for a in alerts)
    assert {a.key for a in alerts} <= {"ncdr:颱風", "ncdr:降雨", "ncdr:強風", "ncdr:高溫"}


def test_ncdr_is_requested_once_as_text():
    h = http()
    ww_alerts_tw.alerts_for([BANQIAO, JIAOXI, NANTOU], h, NCDR_NOW)
    assert h.calls == [(ww_alerts_tw.FEED, None)]


def test_ncdr_filters_by_county():
    banqiao, jiaoxi, nantou = run([BANQIAO, JIAOXI, NANTOU])
    assert "rain" in kinds(banqiao) and "rain" in kinds(jiaoxi)
    assert "rain" not in kinds(nantou)


def test_ncdr_typhoon_covers_every_place():
    for alerts in run([BANQIAO, JIAOXI, NANTOU]):
        assert "typhoon" in kinds(alerts)


def test_ncdr_severity_and_display_title():
    (alerts,) = run([JIAOXI])
    by = {a.kind: a for a in alerts}
    assert by["rain"].severity == "extreme" and by["rain"].title == "超大豪雨"
    assert by["wind"].severity == "severe" and by["wind"].title == "強風 橙色燈號"
    assert by["typhoon"].title == "颱風警報 中度颱風 薔琵"
    assert by["typhoon"].severity == "extreme"  # its text carries a 超大豪雨 warning


def test_ncdr_fields_come_from_the_newest_entry():
    (alerts,) = run([BANQIAO])
    rain = next(a for a in alerts if a.kind == "rain")
    assert rain.updated == datetime(2026, 10, 22, 19, 54, 10, tzinfo=TPE)
    assert rain.expires == datetime(2026, 10, 23, 20, 0, tzinfo=TPE)
    assert rain.detail.startswith("第29號颱風及其外圍環流影響")


def test_ncdr_summary_is_short_and_about_the_place():
    (alerts,) = run([JIAOXI])
    rain = next(a for a in alerts if a.kind == "rain")
    assert len(rain.summary) <= 60 and "宜蘭" in rain.summary
    ty = next(a for a in alerts if a.kind == "typhoon")
    assert len(ty.summary) <= 60 and "中心位置" in ty.summary and "2026" not in ty.summary


def test_ncdr_time_parses_noon_and_midnight():
    p = ww_alerts_tw.parse_ncdr_time
    assert p("2026/10/23 下午 08:00:00") == datetime(2026, 10, 23, 20, 0, tzinfo=TPE)
    assert p("2026/10/23 上午 12:30:00") == datetime(2026, 10, 23, 0, 30, tzinfo=TPE)
    assert p("2026/10/23 下午 12:30:00") == datetime(2026, 10, 23, 12, 30, tzinfo=TPE)


def test_ncdr_rate_limit_message_raises():
    h = FakeHttp({ww_alerts_tw.FEED: "<WarningMessage><Warning>限制存取間隔時間為3秒</Warning></WarningMessage>"})
    with pytest.raises(WwError) as e:
        ww_alerts_tw.alerts_for([BANQIAO], h, NCDR_NOW)
    assert e.value.code == "service_error" and e.value.detail == "ncdr rate limited"


def test_ncdr_place_without_region_is_none():
    assert run([NO_REGION, BANQIAO])[0] is None
    assert run([NO_REGION, BANQIAO])[1] is not None


def test_ncdr_taiwan_character_variants_match():
    feed = fixture("ncdr.xml").replace("臺", "台")
    got = ww_alerts_tw.alerts_for([BANQIAO], FakeHttp({ww_alerts_tw.FEED: feed}), NCDR_NOW)
    assert "rain" in kinds(got[0])


def test_ncdr_through_collect_dedupes_versions_and_drops_expired(monkeypatch):
    monkeypatch.setattr(ww_cyclones, "nearby", lambda p, h, n: [])
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", ww_alerts_tw.alerts_for)
    res, _ = ww_alerts.collect([BANQIAO, NANTOU], http(), NCDR_NOW)
    for r in res:
        assert r.status == "ok"
        assert [a.kind for a in r.alerts].count("wind") == 1
        assert "heat" not in [a.kind for a in r.alerts]  # the only heat entry expired yesterday
