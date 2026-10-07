from datetime import datetime
from zoneinfo import ZoneInfo

from conftest import NOW
from ww_errors import WwError
from ww_model import Current, Day, Place, Report
from ww_render import ALERTS_UNSUPPORTED, render_error, render_report

PLACE = Place("台北市", 25.033, 121.565, "Asia/Taipei")
LOCAL_NOW = NOW.astimezone(ZoneInfo("Asia/Taipei"))
CURRENT = Current("Partly Cloudy", 27.0, 29.1, 70, 12.3, 6.0)
DAYS = [Day("2026-10-07", "Cloudy", 21.9, 25.8, 0), Day("2026-10-08", "Rain", 23.2, 27.4, 80)]


def test_full_report_for_the_model():
    out = render_report(Report("open-meteo", CURRENT, DAYS, None), PLACE, LOCAL_NOW)
    assert out == "\n".join([
        "source: open-meteo",
        "location: 台北市 (25.033, 121.565) timezone=Asia/Taipei",
        "local_time: 2026-10-07T20:41 Wed",
        "current: Partly Cloudy, 27.0°C, feels 29.1°C, humidity 70%, wind 12 km/h, UV 6",
        "daily:",
        "  2026-10-07 Wed: Cloudy, 22–26°C, precipitation chance 0%",
        "  2026-10-08 Thu: Rain, 23–27°C, precipitation chance 80%",
        ALERTS_UNSUPPORTED,
    ])


def test_alerts_none_and_listed():
    none = render_report(Report("weatherkit", CURRENT, DAYS, []), PLACE, LOCAL_NOW)
    assert none.endswith("\nalerts: none")
    listed = render_report(Report("weatherkit", CURRENT, DAYS, ["Heavy Rain Advisory (CWA)"]), PLACE, LOCAL_NOW)
    assert listed.endswith("\nalerts:\n  - Heavy Rain Advisory (CWA)")


def test_unsupported_alerts_tell_the_model_not_to_say_none():
    assert "do not tell the user there are none" in ALERTS_UNSUPPORTED
    assert ALERTS_UNSUPPORTED.startswith("alerts: unsupported")


def test_notice_comes_first():
    out = render_report(Report("open-meteo", CURRENT, DAYS, None), PLACE, LOCAL_NOW, notice="weatherkit_auth_failed (HTTP 401)")
    assert out.splitlines()[0] == "notice: weatherkit_auth_failed (HTTP 401)"


def test_missing_values_say_unknown():
    current = Current("Clear", 20.0, 20.0, 50, 5, None)
    days = [Day("2026-10-07", "Clear", 18, 24, None)]
    out = render_report(Report("open-meteo", current, days, None), PLACE, LOCAL_NOW)
    assert "UV unknown" in out
    assert "precipitation chance unknown" in out


def test_local_time_uses_the_place_timezone():
    late_utc = datetime(2026, 10, 7, 23, 30, tzinfo=ZoneInfo("UTC"))
    out = render_report(Report("open-meteo", CURRENT, [], None), PLACE, late_utc.astimezone(ZoneInfo("Asia/Taipei")))
    assert "local_time: 2026-10-08T07:30 Thu" in out


def test_error_has_code_detail_and_action():
    assert render_error(WwError("place_not_found", "Atlantis")) == (
        "error: place_not_found (Atlantis)\n"
        "action: try another spelling, add --global for places outside Taiwan, or pass lat,lon"
    )
    assert render_error(WwError("no_default_location")).startswith("error: no_default_location\n")
