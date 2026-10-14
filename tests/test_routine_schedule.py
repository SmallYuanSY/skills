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


from datetime import date

from routine_core.schedule import evaluate_weekly

WED_SAT = (2, 5)


def d(text):
    return date.fromisoformat(text)


def statuses(occ):
    return {o.day.isoformat(): o.status for o in occ}


def run_week(completions, until, skips=(), days=WED_SAT, early=1, late=2, start="2026-10-07"):
    return evaluate_weekly(days, early, late, [d(c) for c in completions], {d(s) for s in skips}, d(start), d(until))


# The spec's example table (weekly:wed,sat, window -1,+2), starting after a normal Wed 10-07.

def test_done_the_day_before_counts_early():
    occ, sets = run_week(["2026-10-07", "2026-10-10", "2026-10-13"], "2026-10-13")
    assert statuses(occ)["2026-10-14"] == "done_early"
    assert sets[-1].claimed == d("2026-10-14") and sets[-1].offset == -1


def test_saturday_made_up_on_monday():
    occ, sets = run_week(["2026-10-07", "2026-10-12"], "2026-10-12")
    assert statuses(occ)["2026-10-10"] == "done_late"
    assert sets[-1].claimed == d("2026-10-10") and sets[-1].offset == 2
    # Wednesday is still open: on Tue 10-13 it is due
    assert statuses(run_week(["2026-10-07", "2026-10-12"], "2026-10-13")[0])["2026-10-14"] == "due"


def test_saturday_missed_then_done_tuesday_merges_it():
    occ, sets = run_week(["2026-10-07", "2026-10-13"], "2026-10-13")
    s = statuses(occ)
    assert s["2026-10-10"] == "merged"
    assert s["2026-10-14"] == "done_early"
    assert sets[-1].merged == [d("2026-10-10")]


def test_saturday_missed_then_done_wednesday():
    occ, sets = run_week(["2026-10-07", "2026-10-14"], "2026-10-14")
    s = statuses(occ)
    assert s["2026-10-10"] == "merged"
    assert s["2026-10-14"] == "done"
    assert sets[-1].offset == 0 and sets[-1].merged == [d("2026-10-10")]


def test_skipped_saturday_is_not_merged():
    occ, _ = run_week(["2026-10-07", "2026-10-14"], "2026-10-14", skips=["2026-10-10"])
    s = statuses(occ)
    assert s["2026-10-10"] == "skipped"
    assert s["2026-10-14"] == "done"


# Pending states relative to `until`

def test_pending_states():
    s = statuses(run_week(["2026-10-07"], "2026-10-11")[0])
    assert s["2026-10-10"] == "makeup"
    s = statuses(run_week(["2026-10-07"], "2026-10-13")[0])
    assert s["2026-10-10"] == "missed" and s["2026-10-14"] == "due"
    s = statuses(run_week(["2026-10-07"], "2026-10-08")[0])
    assert "2026-10-10" not in s   # beyond the early window; day_status works out "next" itself
    s = statuses(run_week(["2026-10-07"], "2026-10-09")[0])
    assert s["2026-10-10"] == "due"


def test_many_missed_then_one_completion_settles_all():
    occ, sets = run_week(["2026-10-07", "2026-10-28"], "2026-10-28")
    s = statuses(occ)
    assert [k for k, v in s.items() if v == "merged"] == [
        "2026-10-10", "2026-10-14", "2026-10-17", "2026-10-21", "2026-10-24"]
    assert s["2026-10-28"] == "done"
    assert not [v for v in s.values() if v == "missed"]


def test_completion_outside_every_window_with_nothing_missed_is_extra():
    # weekly:mon only, window -1,+2 covers Sun..Wed; Thu 10-08 is outside, Mon 10-05 was done.
    occ, sets = run_week(["2026-10-05", "2026-10-08"], "2026-10-08", days=(0,), start="2026-10-05")
    assert sets[-1].extra
    assert statuses(occ) == {"2026-10-05": "done"}


def test_completion_outside_every_window_still_merges_earlier_misses():
    # Mon 10-05 never done; Thu 10-08 merges it and does not claim next Mon.
    occ, sets = run_week(["2026-10-08"], "2026-10-08", days=(0,), start="2026-10-05")
    assert sets[-1].merged == [d("2026-10-05")] and sets[-1].claimed is None
    assert not sets[-1].extra


def test_overlapping_windows_prefer_the_earlier_day():
    # weekly:fri,sat, window -1,+2: a Saturday completion makes up Friday; Saturday stays due.
    occ, sets = run_week(["2026-10-17"], "2026-10-17", days=(4, 5), start="2026-10-16")
    s = statuses(occ)
    assert s["2026-10-16"] == "done_late"
    assert s["2026-10-17"] == "due"


def test_one_completion_merges_every_open_day_before_it():
    # weekly:mon,tue,wed, window -1,+2: Wednesday makes up Monday, settles Tuesday, Wednesday stays due.
    occ, sets = run_week(["2026-10-14"], "2026-10-14", days=(0, 1, 2), start="2026-10-12")
    s = statuses(occ)
    assert (s["2026-10-12"], s["2026-10-13"], s["2026-10-14"]) == ("done_late", "merged", "due")
    assert sets[0].claimed == d("2026-10-12") and sets[0].merged == [d("2026-10-13")]


def test_settlements_follow_the_input_order():
    _, sets = run_week(["2026-10-07", "2026-10-13", "2026-10-13"], "2026-10-13", days=(2,))
    assert [s.claimed for s in sets] == [d("2026-10-07"), d("2026-10-14"), None]


def test_two_completions_in_one_window_claim_two_days():
    occ, sets = run_week(["2026-10-16", "2026-10-17"], "2026-10-17", days=(4, 5), start="2026-10-16")
    s = statuses(occ)
    assert s["2026-10-16"] == "done" and s["2026-10-17"] == "done"


def test_crossing_a_year():
    occ, _ = run_week(["2026-12-30", "2027-01-02"], "2027-01-02", start="2026-12-30")
    s = statuses(occ)
    assert s["2026-12-30"] == "done" and s["2027-01-02"] == "done"
