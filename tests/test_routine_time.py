import json

from rk_helpers import at_tpe, run, root  # noqa: F401


def test_empty(root, capsys):
    code, out = run(root, capsys, "time", "today")
    assert code == 0
    assert out.splitlines() == [
        "date: 2026-10-14 (Wed)", "now: 2026-10-14 16:20 Asia/Taipei", "day_boundary: 05:00", "",
        "doses:", "- (none)", "", "chores:", "- (none)"]


def test_a_full_day(root, capsys):
    t0 = at_tpe("2026-09-01 09:00")
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D", "--slot", "after breakfast", now=t0)
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium", "--slot", "bedtime", now=t0)
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat", now=t0)
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Bed sheets", "--schedule", "interval:14", now=t0)
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Litter box", now=t0)
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-14 10:42")
    run(root, capsys, "done", "Laundry", "--at", "2026-10-07 18:00")
    run(root, capsys, "done", "Laundry", "--at", "2026-10-10 18:00")
    run(root, capsys, "done", "Bed sheets", "--at", "2026-09-19 12:00")
    run(root, capsys, "done", "Litter box", "--at", "2026-10-14 14:10")
    run(root, capsys, "note", "add", "Laundry", "wash the jacket")
    code, out = run(root, capsys, "time", "today")
    assert out.splitlines()[4:] == [
        "doses:",
        "- Magnesium [daily, bedtime]: not_done",
        "- Vitamin D [daily, after breakfast]: done 10:42",
        "",
        "chores:",
        "- Bed sheets [interval:14]: due since Sat 2026-10-03 (11 days) | last done 2026-09-19 (25 days ago)",
        "- Laundry [weekly:wed,sat]: due today | last done 2026-10-10 (4 days ago)",
        "  note #1: wash the jacket",
        "- Litter box [none]: done 14:10",
    ]


def test_a_past_day_only_counts_records_up_to_it(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat",
        now=at_tpe("2026-10-01 09:00"))
    run(root, capsys, "done", "Laundry", "--at", "2026-10-07 18:00")
    run(root, capsys, "done", "Laundry", "--at", "2026-10-14 10:00")
    code, out = run(root, capsys, "time", "2026-10-11")
    assert "- Laundry [weekly:wed,sat]: makeup for Sat 2026-10-10 | last done 2026-10-07 (4 days ago)" in out.splitlines()
    code, out = run(root, capsys, "time", "yesterday")
    assert ("- Laundry [weekly:wed,sat]: due Wed 2026-10-14 (can be done from today) | last done 2026-10-07 "
            "(6 days ago) | missed: Sat 2026-10-10") in out.splitlines()


def test_done_today_but_another_scheduled_day_still_open(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Mop", "--schedule", "weekly:fri,sat",
        now=at_tpe("2026-10-16 09:00"))
    run(root, capsys, "done", "Mop", "--at", "2026-10-17 10:00", now=at_tpe("2026-10-17 10:30"))
    out = run(root, capsys, "time", "today", now=at_tpe("2026-10-17 10:30"))[1]
    assert "- Mop [weekly:fri,sat]: done 10:00 | still due Sat 2026-10-17" in out.splitlines()
    data = json.loads(run(root, capsys, "--json", "time", "today", now=at_tpe("2026-10-17 10:30"))[1])
    mop = [i for i in data["items"] if i["name"] == "Mop"][0]
    assert (mop["state"], mop["also_due"]) == ("done", "2026-10-17")


def test_changing_the_schedule_judges_from_then_on(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed",
        now=at_tpe("2026-09-01 09:00"))
    run(root, capsys, "done", "Laundry", "--at", "2026-10-07 18:00")
    run(root, capsys, "item", "edit", "Laundry", "--schedule", "weekly:sat")
    out = run(root, capsys, "time", "today")[1]
    assert ("- Laundry [weekly:sat]: next Sat 2026-10-17 (in 3 days) | last done 2026-10-07 (7 days ago)"
            in out.splitlines())
    out = run(root, capsys, "time", "2026-10-07")[1]
    assert "- Laundry [weekly:sat]: done 18:00" in out.splitlines()


def test_paused_items_are_hidden(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry")
    run(root, capsys, "item", "pause", "Laundry")
    assert "Laundry" not in run(root, capsys, "time", "today")[1]


def test_skipped_day(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium")
    run(root, capsys, "skip", "Magnesium", "--for", "today", "--reason", "ran out")
    assert "- Magnesium [daily]: skipped (ran out)" in run(root, capsys, "time", "today")[1].splitlines()


def test_many_missed_days_are_summarised(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat",
        now=at_tpe("2026-09-14 09:00"))
    out = run(root, capsys, "time", "today")[1]
    line = [x for x in out.splitlines() if x.startswith("- Laundry")][0]
    assert line == "- Laundry [weekly:wed,sat]: due today | missed 8 times since 2026-09-16"


def test_changing_timezone_keeps_past_days(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium")
    run(root, capsys, "done", "Magnesium", "--at", "2026-10-13 23:30")
    run(root, capsys, "config", "set", "timezone", "UTC")
    out = run(root, capsys, "time", "2026-10-13")[1]
    assert "- Magnesium [daily]: done 23:30" in out.splitlines()


def test_bad_day(root, capsys):
    code, out = run(root, capsys, "time", "someday")
    assert code == 1 and out.startswith("error: bad_date")


def test_time_json(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D")
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-14 10:42")
    data = json.loads(run(root, capsys, "time", "today", "--json")[1])
    assert data["date"] == "2026-10-14"
    assert data["items"][0] == {
        "name": "Vitamin D", "kind": "dose", "schedule": "daily", "slot": None, "state": "done", "ref": None,
        "last_done": "2026-10-14", "missed": [], "done_times": ["10:42"], "also_due": None, "notes": [],
        "text": "done 10:42"}
