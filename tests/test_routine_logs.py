import json

from rk_helpers import at_tpe, run, root  # noqa: F401


def setup_items(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D", "--slot", "after breakfast")
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium", "--slot", "bedtime")
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat")
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Bed sheets", "--schedule", "interval:14")
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Litter box")


def test_done_now(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "vitamin d")
    assert code == 0
    assert out.splitlines() == ["ok: logged #1 Vitamin D for 2026-10-14 (Wed) at 2026-10-14 16:20"]


def test_after_midnight_counts_for_the_night_before(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "Magnesium", now=at_tpe("2026-10-15 02:30"))
    assert out == "ok: logged #1 Magnesium for 2026-10-14 (Wed) at 2026-10-15 02:30"


def test_done_earlier_with_at_and_for(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "Litter box", "--at", "2026-10-13 23:00", "--note", "all clean")
    assert out == "ok: logged #1 Litter box for 2026-10-13 (Tue) at 2026-10-13 23:00"
    code, out = run(root, capsys, "done", "Litter box", "--at", "2026-10-14 02:00", "--for", "2026-10-14")
    assert out.startswith("ok: logged #2 Litter box for 2026-10-14 (Wed)")


def test_never_log_ahead(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "Magnesium", "--at", "2026-10-14 23:00")
    assert code == 2 and out.startswith("error: future_time")
    code, out = run(root, capsys, "done", "Magnesium", "--for", "2026-10-15")
    assert code == 2 and out.startswith("error: future_time")
    code, out = run(root, capsys, "log", "list")
    assert out == "logs: none"


def test_a_dose_twice_in_one_day_needs_force(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-14 10:42")
    code, out = run(root, capsys, "done", "Vitamin D")
    assert code == 2
    assert out.splitlines()[0] == "error: already_logged (Vitamin D for 2026-10-14 as #1 at 10:42)"
    code, out = run(root, capsys, "done", "Vitamin D", "--force")
    assert code == 0


def test_a_chore_can_be_done_twice(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "done", "Litter box", "--at", "2026-10-14 09:00")
    assert run(root, capsys, "done", "Litter box")[0] == 0


def test_paused_item_cannot_be_logged(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "item", "pause", "Laundry")
    code, out = run(root, capsys, "done", "Laundry")
    assert code == 2 and out.startswith("error: item_paused")


def test_weekly_done_explains_what_it_settled(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Mop", "--schedule", "weekly:wed,sat",
        now=at_tpe("2026-10-07 09:00"))
    run(root, capsys, "done", "Mop", "--at", "2026-10-07 10:00", now=at_tpe("2026-10-07 10:00"))
    code, out = run(root, capsys, "done", "Mop", "--at", "2026-10-14 18:00", now=at_tpe("2026-10-14 18:20"))
    assert out.splitlines() == [
        "ok: logged #2 Mop for 2026-10-14 (Wed) at 2026-10-14 18:00",
        "schedule: counts for Wed 2026-10-14 (on the day)",
        "schedule: Sat 2026-10-10 merged into this",
    ]


def test_weekly_done_early_and_extra(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Mop", "--schedule", "weekly:wed",
        now=at_tpe("2026-10-07 09:00"))
    code, out = run(root, capsys, "done", "Mop", "--at", "2026-10-13 10:00", now=at_tpe("2026-10-13 10:00"))
    assert out.splitlines()[1:] == ["schedule: counts for Wed 2026-10-14 (1 day early)",
                                    "schedule: Wed 2026-10-07 merged into this"]
    code, out = run(root, capsys, "done", "Mop", "--at", "2026-10-13 11:00", now=at_tpe("2026-10-13 11:00"))
    assert out.splitlines()[1:] == ["schedule: extra (no scheduled day nearby)"]


def test_backfilled_earlier_log_reports_its_own_settlement(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Mop", "--schedule", "weekly:wed",
        now=at_tpe("2026-10-07 09:00"))
    run(root, capsys, "done", "Mop", "--at", "2026-10-13 11:00", now=at_tpe("2026-10-13 11:30"))
    code, out = run(root, capsys, "done", "Mop", "--at", "2026-10-13 10:00", now=at_tpe("2026-10-13 11:30"))
    assert out.splitlines()[1] == "schedule: counts for Wed 2026-10-14 (1 day early)"


def test_order_within_a_day_follows_the_real_instant_across_timezones(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Mop", "--schedule", "weekly:wed",
        now=at_tpe("2026-10-07 09:00"))
    run(root, capsys, "done", "Mop", "--at", "2026-10-13 10:00")   # 02:00 UTC
    run(root, capsys, "config", "set", "timezone", "UTC")
    code, out = run(root, capsys, "done", "Mop", "--at", "2026-10-13 03:00", "--for", "2026-10-13")   # later
    assert out.splitlines()[1:] == ["schedule: extra (no scheduled day nearby)"]


def test_interval_done_early(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "done", "Bed sheets", "--at", "2026-09-29 12:00")
    code, out = run(root, capsys, "done", "Bed sheets", "--at", "2026-10-11 12:00")
    assert out.splitlines()[1] == "schedule: planned for Tue 2026-10-13, done 2 days before; next due Sun 2026-10-25"


def test_interval_done_reports_the_plan(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "Bed sheets", "--at", "2026-09-19 12:00")
    assert out.splitlines()[1:] == ["schedule: first time; next due Sat 2026-10-03"]
    code, out = run(root, capsys, "done", "Bed sheets")
    assert out.splitlines()[1:] == ["schedule: planned for Sat 2026-10-03, done 11 days after; next due Wed 2026-10-28"]


def test_notes_are_resolved_by_done(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "note", "add", "laundry", "wash the jacket")
    assert out == "ok: note #1 on Laundry: wash the jacket (shown until Laundry is next logged)"
    run(root, capsys, "note", "add", "Laundry", "use less soap")
    code, out = run(root, capsys, "note", "list")
    assert out.splitlines() == ["#1 Laundry: wash the jacket (since 2026-10-14)",
                                "#2 Laundry: use less soap (since 2026-10-14)"]
    code, out = run(root, capsys, "done", "Laundry")
    assert out.splitlines()[-2:] == ["notes_resolved: #1 wash the jacket", "notes_resolved: #2 use less soap"]
    assert run(root, capsys, "note", "list") == (0, "notes: none open")


def test_keep_notes_and_resolve_by_hand(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "note", "add", "Laundry", "wash the jacket")
    code, out = run(root, capsys, "done", "Laundry", "--keep-notes")
    assert "notes_resolved" not in out
    assert run(root, capsys, "note", "resolve", "1") == (0, "ok: resolved note #1 (Laundry: wash the jacket)")
    code, out = run(root, capsys, "note", "resolve", "1")
    assert out == "ok: note #1 was already resolved"
    code, out = run(root, capsys, "note", "resolve", "9")
    assert code == 2 and out.startswith("error: unknown_note")


def test_skip(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "skip", "Laundry", "--for", "2026-10-14", "--reason", "too tired")
    assert out == "ok: skipped Laundry on Wed 2026-10-14 (too tired)"
    assert run(root, capsys, "skip", "Laundry", "--for", "2026-10-14")[1] == "ok: Laundry was already skipped on Wed 2026-10-14"
    assert run(root, capsys, "skip", "Laundry", "--for", "2026-10-14", "--undo")[1] == "ok: Laundry is no longer skipped on Wed 2026-10-14"
    code, out = run(root, capsys, "skip", "Laundry", "--for", "2026-10-13")
    assert code == 2 and out.startswith("error: not_scheduled")
    code, out = run(root, capsys, "skip", "Bed sheets", "--for", "2026-10-14")
    assert code == 2 and out.startswith("error: skip_not_applicable")
    code, out = run(root, capsys, "skip", "Vitamin D", "--for", "2026-10-15")
    assert code == 2 and out.startswith("error: future_time")


def test_log_list_edit_delete_restore(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-13 09:00", "--note", "with toast")
    run(root, capsys, "done", "Litter box", "--at", "2026-10-14 14:10")
    code, out = run(root, capsys, "log", "list")
    assert out.splitlines() == [
        "#2 2026-10-14 (Wed) Litter box at 2026-10-14 14:10",
        "#1 2026-10-13 (Tue) Vitamin D at 2026-10-13 09:00 | note: with toast",
    ]
    assert run(root, capsys, "log", "list", "--item", "vitamin d")[1].startswith("#1 ")
    assert run(root, capsys, "log", "list", "--from", "2026-10-14")[1].startswith("#2 ")
    assert run(root, capsys, "log", "list", "--limit", "1")[1].count("\n") == 0

    code, out = run(root, capsys, "log", "edit", "1", "--at", "2026-10-14 01:00")
    assert out.splitlines() == ["ok: edited #1 Vitamin D", "changed: at 2026-10-13T09:00+08:00 -> 2026-10-14T01:00+08:00"]
    code, out = run(root, capsys, "log", "edit", "1", "--for", "2026-10-14")
    assert out.splitlines()[1] == "changed: for_date 2026-10-13 -> 2026-10-14"
    assert run(root, capsys, "log", "edit", "1", "--note", "with toast")[1] == "ok: nothing changed on #1"
    code, out = run(root, capsys, "log", "edit", "1", "--for", "2026-10-20")
    assert code == 2 and out.startswith("error: future_time")

    assert run(root, capsys, "log", "delete", "2")[1] == "ok: deleted #2 Litter box (restore with: log restore 2)"
    assert "#2" not in run(root, capsys, "log", "list")[1]
    code, out = run(root, capsys, "log", "delete", "2")
    assert code == 2 and out.startswith("error: unknown_log")
    assert run(root, capsys, "log", "restore", "2")[1] == "ok: restored #2 Litter box"
    assert "#2" in run(root, capsys, "log", "list")[1]


def test_moving_a_dose_onto_a_taken_day_needs_force(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-13 09:00")   # 1
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-14 09:00")   # 2
    code, out = run(root, capsys, "log", "edit", "1", "--for", "2026-10-14")
    assert code == 2 and out.startswith("error: already_logged")
    assert run(root, capsys, "log", "edit", "1", "--for", "2026-10-14", "--force")[0] == 0


def test_restoring_a_dose_onto_a_taken_day_needs_force(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-14 09:00")   # 1
    run(root, capsys, "log", "delete", "1")
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-14 10:00")   # 2 takes the day
    code, out = run(root, capsys, "log", "restore", "1")
    assert code == 2 and out.startswith("error: already_logged")
    assert run(root, capsys, "log", "restore", "1", "--force")[0] == 0


def test_done_json(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "note", "add", "Laundry", "wash the jacket")
    code, out = run(root, capsys, "--json", "done", "Laundry")
    data = json.loads(out)
    assert data["log"]["id"] == 1 and data["log"]["for_date"] == "2026-10-14"
    assert data["notes_resolved"] == [{"id": 1, "text": "wash the jacket"}]


def test_done_reports_offsets_without_the_word_late(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Mop", "--schedule", "weekly:sat",
        now=at_tpe("2026-10-07 09:00"))
    code, out = run(root, capsys, "done", "Mop", "--at", "2026-10-12 10:00")
    assert out.splitlines()[1] == "schedule: counts for Sat 2026-10-10 (2 days after)"


def test_a_backdated_done_keeps_newer_reminders(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "note", "add", "Laundry", "wash the jacket")
    code, out = run(root, capsys, "done", "Laundry", "--at", "2026-10-10 18:00")
    assert "notes_resolved" not in out
    assert "#1 Laundry: wash the jacket" in run(root, capsys, "note", "list")[1]
