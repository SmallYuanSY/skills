import pytest

from routine_core.errors import RkError
from routine_core.schedule import Schedule, describe, format_schedule, parse_schedule, parse_window


@pytest.mark.parametrize("text,expected", [
    ("daily", Schedule("daily")),
    ("NONE", Schedule("none")),
    ("interval:14", Schedule("interval", n=14)),
    ("weekly:sat,wed", Schedule("weekly", days=(2, 5))),
    ("weekly: Wed, Sat, wed", Schedule("weekly", days=(2, 5))),
])
def test_parse_schedule(text, expected):
    assert parse_schedule(text) == expected


@pytest.mark.parametrize("text", ["", "weekly", "weekly:", "weekly:wednesday", "interval:0", "interval:366", "interval:x", "monthly:1"])
def test_bad_schedule(text):
    with pytest.raises(RkError) as e:
        parse_schedule(text)
    assert e.value.code == "bad_schedule"


def test_format_schedule_round_trips():
    for text in ("daily", "none", "interval:14", "weekly:wed,sat"):
        assert format_schedule(parse_schedule(text)) == text


def test_parse_window():
    assert parse_window("-1,+2") == (1, 2)
    assert parse_window("-0,3") == (0, 3)
    assert parse_window(" -2, +0 ") == (2, 0)
    for bad in ("1,2", "-7,+0", "-1", "+1,-2", "-1,+x"):
        with pytest.raises(RkError) as e:
            parse_window(bad)
        assert e.value.code == "bad_window"


def test_describe():
    assert describe(Schedule("daily"), 1, 2) == "every day"
    assert describe(Schedule("none"), 1, 2) == "no schedule, log only"
    assert describe(Schedule("interval", n=1), 1, 2) == "every 1 day after the last time it was done"
    assert describe(Schedule("interval", n=14), 1, 2) == "every 14 days after the last time it was done"
    assert describe(Schedule("weekly", days=(2, 5)), 1, 2) == "every Wed and Sat, can be done 1 day early or 2 days late"
    assert describe(Schedule("weekly", days=(0, 2, 4)), 0, 0) == "every Mon, Wed and Fri, only on the day"
