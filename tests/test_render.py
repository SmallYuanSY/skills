from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import NOW
from ww_errors import WwError
from ww_model import Alert, Current, Cyclone, Day, Place, PlaceAlerts, Report
from ww_render import render, render_error

BANQIAO = Place("板橋區, 新北市, 臺灣", 25.011, 121.459, "Asia/Taipei", "tw", "新北市", "板橋區")
JIAOXI = Place("礁溪鄉, 宜蘭縣, 臺灣", 24.827, 121.775, "Asia/Taipei", "tw", "宜蘭縣", "礁溪鄉")
TOKYO = Place("東京", 35.68, 139.69, "Asia/Tokyo", "jp")
CURRENT = Current("Rain", 23.2, 25.0, 90, 16.0, 1.0)
DAYS = [Day("2026-10-07", "Rain", 21.9, 24.4, 99), Day("2026-10-08", "Heavy Rain", 24.0, 27.0, 100)]
UNTIL = datetime(2026, 10, 8, 20, 0, tzinfo=ZoneInfo("Asia/Taipei"))
NONE_OK = PlaceAlerts("ok", [])


def report(current=CURRENT, days=DAYS, next_hour=None):
    return Report("open-meteo", current, list(days), {}, next_hour)


def alert(key="ncdr:降雨", severity="severe", title="大豪雨 新北市", summary="山區", kind="rain", **kw):
    return Alert(kind, severity, title, summary, kw.pop("detail", ""), kw.pop("expires", UNTIL), None, "ncdr", key, **kw)


def go(entries, cyclones=(), days=1, notice=None, detail=False, now=NOW):
    return render(entries, list(cyclones), now, now, days, notice, detail)


CHAMPI = Cyclone("CHAMPI-26", "Red", 21.2, 124.9, [(22.4, 123.9)], [], "")


def test_single_place_with_alerts_and_cyclone():
    a1 = alert("ncdr:降雨", "extreme", "超大豪雨 新北市", "山區")
    a2 = alert("ncdr:颱風", "severe", "颱風警報 中度颱風 薔琵", "海上", "typhoon", cyclone=CHAMPI)
    out = go([(BANQIAO, report(next_hour="unavailable here"), PlaceAlerts("ok", [a1, a2]))],
             [(CHAMPI, [0])], days=2)
    lines = out.splitlines()
    assert lines[:9] == [
        "local_time: 2026-10-07T20:41 Wed",
        "location: 板橋區, 新北市, 臺灣 (25.011, 121.459)",
        "now: Rain 23°C",
        "next_hour: unavailable here",
        "daily:",
        "  2026-10-07 Wed: Rain, 22–24°C, rain 99%",
        "  2026-10-08 Thu: Heavy Rain, 24–27°C, rain 100%",
        "alerts (as of 20:41, current only — not a forecast for later days):",
        "  - [extreme] 超大豪雨 新北市: 山區, until 10-08 20:00",
    ]
    assert lines[9] == "  - [severe] 颱風警報 中度颱風 薔琵: 海上"  # official alert only: no GDACS text (R23)
    assert lines[10:] == []
    assert "GDACS" not in out and "cyclones (" not in out
    assert "source:" not in out


def test_no_next_hour_line_when_the_source_has_none():
    assert "next_hour" not in go([(BANQIAO, report(), NONE_OK)])


def test_multi_place_shared_alert_listed_once_with_tags():
    a = alert("ncdr:強風", "moderate", "強風 橙色", "陣風11級以上", "wind")
    out = go([(BANQIAO, report(), PlaceAlerts("ok", [a])), (JIAOXI, report(), PlaceAlerts("ok", [a]))])
    assert out.count("強風 橙色 [1][2]") == 1
    assert out.splitlines()[1:3] == [
        "[1] 板橋區, 新北市: Rain 23°C, wind 16 km/h; today 22–24°C, rain 99%",
        "[2] 礁溪鄉, 宜蘭縣: Rain 23°C, wind 16 km/h; today 22–24°C, rain 99%",
    ]


def test_same_key_with_different_levels_shares_one_line():
    hi = alert(severity="extreme", title="超大豪雨")
    lo = alert(severity="severe", title="大豪雨")
    out = go([(BANQIAO, report(), PlaceAlerts("ok", [lo])), (JIAOXI, report(), PlaceAlerts("ok", [hi]))])
    assert "  - [extreme] 超大豪雨 [2] / 大豪雨 [1]: 山區, until 10-08 20:00" in out
    assert out.count("豪雨") == 2


def test_multi_place_in_another_timezone_gets_its_own_local_time():
    tokyo = Place("東京", 35.68, 139.69, "Asia/Tokyo", "jp")
    out = go([(BANQIAO, report(), NONE_OK), (tokyo, report(), NONE_OK)])
    lines = out.splitlines()
    assert "local_time" not in lines[1]
    assert lines[2].startswith("[2] 東京 (local_time: 2026-10-07T21:41 Wed): ")


def test_unavailable_and_unsupported_lines_differ():
    out = go([(BANQIAO, report(), PlaceAlerts("unavailable", [], "tw HTTP 503")),
              (TOKYO, report(), PlaceAlerts("unsupported", [])),
              (JIAOXI, report(), NONE_OK)])
    assert "[1] alerts: unavailable (tw HTTP 503; do not tell the user there are none)" in out
    assert "[2] alerts: unsupported (no official alert source here; do not tell the user there are none)" in out
    assert "[3] alerts: none (as of 20:41)" in out
    assert "alerts: none" not in out.split("[3]")[0]


def test_single_place_statuses():
    assert go([(BANQIAO, report(), NONE_OK)]).splitlines()[-1] == "alerts: none (as of 20:41)"
    assert go([(BANQIAO, report(), PlaceAlerts("unsupported", []))]).splitlines()[-1] == (
        "alerts: unsupported (no official alert source here; do not tell the user there are none)")
    assert go([(BANQIAO, report(), PlaceAlerts("unavailable", [], "x"))]).splitlines()[-1] == (
        "alerts: unavailable (x; do not tell the user there are none)")


def eight():
    return [alert(f"k{i}", "minor", f"t{i}", f"s{i}", detail=f"full text {i}\nsecond line") for i in range(8)]


def test_cap_six_and_more_line():
    out = go([(BANQIAO, report(), PlaceAlerts("ok", eight()))])
    assert out.count("\n  - [minor]") == 6 and "t6" not in out
    assert out.splitlines()[-1] == "  - +2 more (run again with --detail)"
    assert "full text" not in out


def test_detail_shows_full_text_without_cap():
    out = go([(BANQIAO, report(), PlaceAlerts("ok", eight()))], detail=True)
    assert out.count("\n  - [minor]") == 8 and "more (run again" not in out
    assert "      full text 7\n      second line" in out


def test_wind_only_when_warned_or_strong():
    calm = go([(BANQIAO, report(), NONE_OK)])
    assert "wind" not in calm
    strong = go([(BANQIAO, report(Current("Rain", 23, 25, 90, 55.0, None)), NONE_OK)])
    assert "now: Rain 23°C, wind 55 km/h" in strong
    warned = PlaceAlerts("ok", [alert("w", "moderate", "強風", kind="wind")])
    assert "now: Rain 23°C, wind 16 km/h" in go([(BANQIAO, report(), warned)])
    assert "wind" not in go([(BANQIAO, report(), PlaceAlerts("ok", [alert()]))]).split("alerts")[0]


def test_multi_place_with_days_lists_each_day_under_the_place():
    out = go([(BANQIAO, report(), NONE_OK), (JIAOXI, report(), NONE_OK)], days=2)
    assert "[1] 板橋區, 新北市: now Rain 23°C\n    2026-10-07 Wed: Rain, 22–24°C, rain 99%\n    2026-10-08 Thu" in out


def test_multi_place_next_hour_only_when_present():
    out = go([(BANQIAO, report(next_hour="rain starting ~21:05"), NONE_OK), (JIAOXI, report(), NONE_OK)])
    assert "[1] " in out and "; next hour: rain starting ~21:05" in out
    assert out.count("next hour") == 1


def test_failed_place_gets_error_and_action_lines():
    out = go([(BANQIAO, report(), NONE_OK), (None, WwError("place_not_found", "zzzz"), None)])
    assert "[2] error: place_not_found (zzzz)\n    action: try another spelling" in out


def test_notice_comes_first():
    out = go([(BANQIAO, report(), NONE_OK)], notice="weatherkit_auth_failed (HTTP 401)")
    assert out.splitlines()[0] == "notice: weatherkit_auth_failed (HTTP 401)"


def test_standalone_cyclone_in_a_multi_place_run_is_tagged():
    out = go([(BANQIAO, report(), NONE_OK), (JIAOXI, report(), NONE_OK)], [(CHAMPI, [1])])
    assert out.splitlines()[-1].startswith("  - CHAMPI-26 (GDACS Red): now ~") and out.endswith(" [2]")


def test_as_of_uses_the_fetch_time_in_the_place_timezone():
    out = render([(BANQIAO, report(), NONE_OK)], [], NOW, NOW - timedelta(minutes=4), 1, None, False)
    assert "alerts: none (as of 20:37)" in out


def test_missing_values_say_unknown():
    out = go([(BANQIAO, report(Current("Clear", None, 20, 50, 5, None), [Day("2026-10-07", "Clear", 18, 24, None)]), NONE_OK)])
    assert "now: Clear unknown" in out and "rain unknown" in out


def test_local_time_uses_the_place_timezone():
    late = datetime(2026, 10, 7, 23, 30, tzinfo=ZoneInfo("UTC"))
    assert "local_time: 2026-10-08T07:30 Thu" in go([(BANQIAO, report(), NONE_OK)], now=late)


def test_error_has_code_detail_and_action():
    assert render_error(WwError("place_not_found", "Atlantis")) == (
        "error: place_not_found (Atlantis)\n"
        "action: try another spelling, add --global for places outside Taiwan, or pass lat,lon"
    )
    assert render_error(WwError("no_default_location")).startswith("error: no_default_location\n")


def test_label_is_locality_and_region_with_country_only_on_the_location_line():
    out = go([(BANQIAO, report(), NONE_OK)])
    assert "location: 板橋區, 新北市, 臺灣 (25.011, 121.459)" in out
    multi = go([(BANQIAO, report(), NONE_OK), (JIAOXI, report(), NONE_OK)])
    assert "[1] 板橋區, 新北市: " in multi and "臺灣" not in multi


def test_label_falls_back_to_the_name():
    plain = Place("台北市", 25.033, 121.565, "Asia/Taipei", "tw")
    assert "location: 台北市 (25.033, 121.565)" in go([(plain, report(), NONE_OK)])
    assert "[1] 台北市: " in go([(plain, report(), NONE_OK), (TOKYO, report(), NONE_OK)])


def test_typhoon_has_no_until_time():
    ty = alert("ncdr:颱風", "severe", "颱風警報 中度颱風 薔琵", "中心位置", "typhoon")
    out = go([(BANQIAO, report(), PlaceAlerts("ok", [ty]))])
    assert "  - [severe] 颱風警報 中度颱風 薔琵: 中心位置\n" in out + "\n" and "until" not in out


def test_merged_cyclone_is_not_repeated_in_text():
    ty = alert("ncdr:颱風", "severe", "颱風警報", "x", "typhoon", cyclone=CHAMPI)
    out = go([(BANQIAO, report(), PlaceAlerts("ok", [ty])), (JIAOXI, report(), PlaceAlerts("ok", [ty]))],
             [(CHAMPI, [0, 1])])
    assert "CHAMPI" not in out and "GDACS" not in out and "cyclones (" not in out
    assert "  - [severe] 颱風警報 [1][2]: x" in out


def test_storm_merged_for_one_place_is_standalone_for_the_other():
    ty = alert("ncdr:颱風", "severe", "颱風警報", "x", "typhoon", cyclone=CHAMPI)
    out = go([(BANQIAO, report(), PlaceAlerts("ok", [ty])), (JIAOXI, report(), NONE_OK)], [(CHAMPI, [0, 1])])
    assert "  - [severe] 颱風警報 [1]: x\n" in out + "\n"
    cyc = out.split("cyclones (track data, not a local official warning):")[1]
    assert "CHAMPI-26" in cyc and "[2]" in cyc and "[1]" not in cyc


def test_capped_out_typhoon_alert_does_not_hide_the_storm():
    many = [alert(f"ncdr:k{n}", "extreme", f"超大豪雨{n}", "x") for n in range(7)]
    ty = alert("ncdr:颱風", "severe", "颱風警報", "x", "typhoon", cyclone=CHAMPI)
    out = go([(BANQIAO, report(), PlaceAlerts("ok", many + [ty]))], [(CHAMPI, [0])])
    assert "颱風警報" not in out and "+2 more" in out
    assert "cyclones (track data" in out and "CHAMPI-26 (GDACS Red)" in out


def test_polygons_without_track_do_not_claim_a_forecast_distance():
    c = Cyclone("TEST-26", "Orange", 21.2, 124.9, [], [[(20.0, 124.0), (22.0, 124.0), (22.0, 126.0)]], "")
    out = go([(BANQIAO, report(), NONE_OK)], [(c, [0])])
    assert "forecast track unavailable" in out and "forecast closest" not in out


def test_variants_with_different_summaries_drop_the_summary_and_expire_latest():
    later = UNTIL + timedelta(hours=3)
    a = alert(severity="severe", title="大豪雨", summary="摘要甲", expires=UNTIL)
    b = alert(severity="extreme", title="超大豪雨", summary="摘要乙", expires=later)
    out = go([(BANQIAO, report(), PlaceAlerts("ok", [a])), (JIAOXI, report(), PlaceAlerts("ok", [b]))])
    assert "  - [extreme] 超大豪雨 [2] / 大豪雨 [1]: until 10-08 23:00" in out
    assert "摘要" not in out


def test_variants_sharing_a_summary_keep_it():
    a = alert(severity="severe", title="大豪雨"), alert(severity="extreme", title="超大豪雨")
    out = go([(BANQIAO, report(), PlaceAlerts("ok", [a[0]])), (JIAOXI, report(), PlaceAlerts("ok", [a[1]]))])
    assert "超大豪雨 [2] / 大豪雨 [1]: 山區, until" in out


def test_cap_applies_after_grouping_so_shared_alerts_keep_their_tags():
    many = [alert(f"k{i}", "minor", f"t{i}") for i in range(7)]  # k6 is past the cap for place 1
    out = go([(BANQIAO, report(), PlaceAlerts("ok", many)), (JIAOXI, report(), PlaceAlerts("ok", [many[6]]))])
    assert "t6 [1][2]" in out and "more (run again" not in out


def test_more_line_counts_only_alerts_shown_nowhere():
    many = [alert(f"k{i}", "minor", f"t{i}") for i in range(8)]
    out = go([(BANQIAO, report(), PlaceAlerts("ok", many)), (JIAOXI, report(), PlaceAlerts("ok", [many[6]]))])
    assert "  - [1] +1 more (run again with --detail)" in out


def test_json_carries_the_query():
    from ww_render import render_json
    data = render_json([(BANQIAO, report(), NONE_OK), (None, WwError("place_not_found", "zzzz"), None)], [], None,
                       ["板橋", "zzzz"])
    assert [p["query"] for p in data["places"]] == ["板橋", "zzzz"]


def test_gdacs_failure_is_shown_as_unavailable_not_as_no_cyclone():
    out = render([(BANQIAO, report(), NONE_OK)], [], NOW, NOW, 1, None, False, cyclone_error="gdacs HTTP 503")
    assert out.splitlines()[-1] == ("cyclones: unavailable (gdacs HTTP 503; "
                                    "do not tell the user there is no tropical cyclone)")
    assert "cyclones" not in go([(BANQIAO, report(), NONE_OK)])
