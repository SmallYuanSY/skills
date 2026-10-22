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
TAIPEI = Place("士林區", 25.09, 121.52, "Asia/Taipei", "tw", "臺北市", "士林區")
NANTOU = Place("x", 23.9, 120.69, "Asia/Taipei", "tw", "南投縣", "x")  # only as bare "南投" in the rain text
PINGTUNG = Place("x", 22.67, 120.49, "Asia/Taipei", "tw", "屏東縣", "x")  # not in the rain list
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
    banqiao, jiaoxi, pingtung = run([BANQIAO, JIAOXI, PINGTUNG])
    assert "rain" in kinds(banqiao) and "rain" in kinds(jiaoxi)
    assert "rain" not in kinds(pingtung)


KEELUNG = Place("x", 25.13, 121.74, "Asia/Taipei", "tw", "基隆市", "x")
TAICHUNG = Place("x", 24.15, 120.67, "Asia/Taipei", "tw", "台中市", "x")


def test_ncdr_matches_counties_written_without_the_suffix():
    # real clause: "基隆、臺北、新竹、苗栗、花蓮地區及臺中、南投山區有局部大雨發生的機率"
    for alerts in run([KEELUNG, NANTOU, TAICHUNG]):
        rain = next(a for a in alerts if a.kind == "rain")
        assert (rain.title, rain.severity) == ("大雨", "moderate")
        assert "有局部大雨" in rain.summary and len(rain.summary) <= 60


def test_ncdr_typhoon_covers_every_place():
    for alerts in run([BANQIAO, JIAOXI, NANTOU]):
        assert "typhoon" in kinds(alerts)


def by_kind(place):
    (alerts,) = run([place])
    return {a.kind: a for a in alerts}


def test_ncdr_rain_severity_and_title_follow_the_place():
    assert (by_kind(JIAOXI)["rain"].severity, by_kind(JIAOXI)["rain"].title) == ("extreme", "超大豪雨")
    assert (by_kind(BANQIAO)["rain"].severity, by_kind(BANQIAO)["rain"].title) == ("severe", "大豪雨")


def test_ncdr_wind_light_follows_the_place():
    assert (by_kind(TAIPEI)["wind"].severity, by_kind(TAIPEI)["wind"].title) == ("moderate", "強風 黃色燈號")
    assert (by_kind(BANQIAO)["wind"].severity, by_kind(BANQIAO)["wind"].title) == ("severe", "強風 橙色燈號")


def test_ncdr_typhoon_is_severe_with_name():
    for place in (BANQIAO, JIAOXI, NANTOU):
        ty = by_kind(place)["typhoon"]
        assert ty.severity == "severe" and ty.title == "颱風警報 中度颱風 薔琵"


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


def test_ncdr_through_collect_drops_expired(monkeypatch):
    monkeypatch.setattr(ww_cyclones, "nearby", lambda p, h, n: [])
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", ww_alerts_tw.alerts_for)
    res, _, _ = ww_alerts.collect([BANQIAO, NANTOU], http(), NCDR_NOW)
    for r in res:
        assert r.status == "ok"
        kinds_ = [a.kind for a in r.alerts]
        assert kinds_.count("wind") == 1 and "heat" not in kinds_  # the only heat entry expired yesterday


def test_ncdr_unparseable_response_is_unavailable_through_collect(monkeypatch):
    monkeypatch.setattr(ww_cyclones, "nearby", lambda p, h, n: [])
    monkeypatch.setitem(ww_alerts.PROVIDERS, "tw", ww_alerts_tw.alerts_for)
    res, _, _ = ww_alerts.collect([BANQIAO], FakeHttp({ww_alerts_tw.FEED: "<feed><entry>"}), NCDR_NOW)
    assert res[0].status == "unavailable" and "ParseError" in res[0].reason


def test_wind_summary_keeps_the_hazard_text_not_the_county_list():
    (alerts,) = run([BANQIAO])
    wind = next(a for a in alerts if a.kind == "wind")
    assert "基隆市" not in wind.summary and "局部地區" not in wind.summary
    assert "平均風9級以上或陣風11級以上發生的機率(橙色燈號)" in wind.summary and len(wind.summary) <= 60


def test_a_single_county_in_a_summary_is_kept():
    (alerts,) = run([JIAOXI])
    assert "宜蘭縣" in next(a for a in alerts if a.kind == "rain").summary


def test_summary_uses_the_next_clause_when_the_first_is_only_a_county_list():
    text = "基隆市、新北市、桃園市局部地區，新北市山區有局部大雨"
    assert ww_alerts_tw._summary("wind", text, "新北市") == "新北市山區有局部大雨"


def test_full_county_name_decides_before_the_bare_one():
    hsinchu_county = Place("x", 24.8, 121.0, "Asia/Taipei", "tw", "新竹縣", "x")
    chiayi_city = Place("x", 23.48, 120.45, "Asia/Taipei", "tw", "嘉義市", "x")
    for p in (hsinchu_county, chiayi_city):  # yellow, although 新竹市 / 嘉義縣 are orange
        assert by_kind(p)["wind"].title == "強風 黃色燈號"


def test_summary_normalises_the_region_spelling():
    text = "今日臺中市山區有局部大雨，其他地區請注意"
    assert ww_alerts_tw._summary("rain", text, "台中市") == "今日臺中市山區有局部大雨"
