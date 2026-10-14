from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from routine_core.dates import (
    ago, day_of, long_day, parse_at, parse_boundary, parse_day, plural, short_day, system_timezone, zone)
from routine_core.errors import RkError

TPE = ZoneInfo("Asia/Taipei")
FIVE = time(5, 0)


def local(text):
    return datetime.fromisoformat(text).replace(tzinfo=TPE)


def test_before_the_boundary_counts_for_the_previous_day():
    assert day_of(local("2026-10-02 03:10"), FIVE) == date(2026, 10, 1)


def test_exactly_at_boundary_counts_for_that_day():
    assert day_of(local("2026-10-02 05:00"), FIVE) == date(2026, 10, 2)


def test_midnight_boundary_means_calendar_days():
    assert day_of(local("2026-10-02 00:00"), time(0, 0)) == date(2026, 10, 2)


def test_parse_boundary():
    assert parse_boundary("5:00") == FIVE
    assert parse_boundary(" 04:30 ") == time(4, 30)
    for bad in ("24:00", "5", "05:60", "five"):
        with pytest.raises(RkError) as e:
            parse_boundary(bad)
        assert e.value.code == "bad_setting"


def test_zone():
    assert zone("Asia/Taipei") == TPE
    for bad in ("Mars/Base", "", "../etc"):
        with pytest.raises(RkError) as e:
            zone(bad)
        assert e.value.code == "bad_setting"


def test_system_timezone_is_a_real_zone(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris")
    assert system_timezone() == "Europe/Paris"
    monkeypatch.setenv("TZ", "Not/AZone")
    assert ZoneInfo(system_timezone())


def test_parse_day():
    today = date(2026, 10, 14)
    assert parse_day("today", today) == today
    assert parse_day("Yesterday", today) == date(2026, 10, 13)
    assert parse_day("2026-10-01", today) == date(2026, 10, 1)
    for bad in ("2026-13-01", "10/13", "tomorrow", "2026-1-1"):
        with pytest.raises(RkError) as e:
            parse_day(bad, today)
        assert e.value.code == "bad_date"


def test_parse_at():
    assert parse_at("2026-10-02 03:10", TPE) == local("2026-10-02 03:10")
    assert parse_at("2026-10-02T3:10", TPE) == local("2026-10-02 03:10")
    for bad in ("2026-10-02", "2026-10-02 25:00", "now"):
        with pytest.raises(RkError) as e:
            parse_at(bad, TPE)
        assert e.value.code == "bad_time"


def test_formatting():
    d = date(2026, 10, 14)
    assert short_day(d) == "Wed 2026-10-14"
    assert long_day(d) == "2026-10-14 (Wed)"
    assert plural(1, "day") == "1 day" and plural(0, "day") == "0 days"
    assert ago(d, d) == "today"
    assert ago(date(2026, 10, 13), d) == "1 day ago"
    assert ago(date(2026, 10, 7), d) == "7 days ago"
    assert ago(date(2026, 10, 16), d) == "in 2 days"
