from datetime import date

from routine_core.schedule import Schedule
from routine_core.status import day_status

WED_SAT = Schedule("weekly", days=(2, 5))
START = date(2026, 10, 1)


def d(text):
    return date.fromisoformat(text)


def ds(sch, done, q, skips=(), early=1, late=2, start=START):
    return day_status(sch, early, late, start, [d(x) for x in done], {d(s) for s in skips}, d(q))


def test_daily():
    sch = Schedule("daily")
    assert ds(sch, ["2026-10-14"], "2026-10-14").state == "done"
    st = ds(sch, ["2026-10-12"], "2026-10-14")
    assert st.state == "not_done" and st.last_done == d("2026-10-12")
    assert ds(sch, [], "2026-10-14", skips=["2026-10-14"]).state == "skipped"


def test_none():
    sch = Schedule("none")
    assert ds(sch, ["2026-10-14", "2026-10-14"], "2026-10-14").state == "done"
    st = ds(sch, ["2026-10-07"], "2026-10-14")
    assert st.state == "idle" and st.last_done == d("2026-10-07")
    assert ds(sch, [], "2026-10-14").last_done is None


def test_interval():
    sch = Schedule("interval", n=14)
    assert ds(sch, [], "2026-10-14").state == "never_done"
    st = ds(sch, ["2026-09-19"], "2026-10-14")
    assert (st.state, st.ref, st.last_done) == ("due", d("2026-10-03"), d("2026-09-19"))
    st = ds(sch, ["2026-10-10"], "2026-10-14")
    assert (st.state, st.ref) == ("upcoming", d("2026-10-24"))
    st = ds(sch, ["2026-09-19", "2026-10-14"], "2026-10-14")
    assert (st.state, st.ref) == ("done", d("2026-10-28"))


def test_interval_ignores_completions_after_the_day():
    st = ds(Schedule("interval", n=14), ["2026-09-19", "2026-10-20"], "2026-10-14")
    assert st.last_done == d("2026-09-19")


def test_weekly_due_today():
    st = ds(WED_SAT, ["2026-10-10"], "2026-10-14")
    assert (st.state, st.ref, st.last_done) == ("due", d("2026-10-14"), d("2026-10-10"))


def test_weekly_due_in_the_early_window():
    st = ds(WED_SAT, ["2026-10-10"], "2026-10-13")
    assert (st.state, st.ref) == ("due", d("2026-10-14"))


def test_weekly_upcoming():
    st = ds(WED_SAT, ["2026-10-10"], "2026-10-12")
    assert (st.state, st.ref) == ("upcoming", d("2026-10-14"))


def test_weekly_makeup():
    st = ds(WED_SAT, ["2026-10-07"], "2026-10-11")
    assert (st.state, st.ref) == ("makeup", d("2026-10-10"))


def test_weekly_missed_saturday_while_wednesday_is_due():
    st = ds(WED_SAT, ["2026-10-07"], "2026-10-13")
    assert (st.state, st.ref, st.missed) == ("due", d("2026-10-14"), [d("2026-10-10")])


def test_weekly_done_reports_its_settlement():
    st = ds(WED_SAT, ["2026-10-07", "2026-10-13"], "2026-10-13")
    assert st.state == "done"
    assert st.settlement.claimed == d("2026-10-14") and st.settlement.merged == [d("2026-10-10")]


def test_weekly_after_doing_it_early_the_next_day_is_the_one_after():
    st = ds(WED_SAT, ["2026-10-07", "2026-10-13"], "2026-10-14")
    assert (st.state, st.ref, st.missed) == ("upcoming", d("2026-10-17"), [])


def test_weekly_skipped_today():
    st = ds(WED_SAT, ["2026-10-10"], "2026-10-14", skips=["2026-10-14"])
    assert (st.state, st.ref) == ("skipped", d("2026-10-14"))


def test_weekly_only_missed():
    # weekly:mon only, nothing pending on Thu 10-08 after missing Mon 10-05
    st = ds(Schedule("weekly", days=(0,)), [], "2026-10-08", start=d("2026-10-05"))
    assert (st.state, st.ref) == ("missed", d("2026-10-05"))


def test_weekly_done_but_another_day_still_due():
    st = ds(Schedule("weekly", days=(4, 5)), ["2026-10-17"], "2026-10-17", start=d("2026-10-16"))
    assert (st.state, st.also_due) == ("done", d("2026-10-17"))


def test_weekly_next_day_is_never_before_start():
    st = ds(Schedule("weekly", days=(5,)), [], "2026-10-07", start=d("2026-10-14"))
    assert (st.state, st.ref) == ("upcoming", d("2026-10-17"))


def test_weekly_ignores_completions_long_before_start():
    st = ds(WED_SAT, ["2026-09-01"], "2026-10-14", start=d("2026-10-14"))
    assert (st.state, st.ref, st.last_done) == ("due", d("2026-10-14"), d("2026-09-01"))
