import json

import routine
from rk_helpers import run, root  # noqa: F401  (root is a fixture)


def test_add_a_dose_defaults_to_daily(root, capsys):
    code, out = run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D", "--slot", "after breakfast")
    assert code == 0
    assert out.splitlines() == [
        "ok: added Vitamin D (dose)",
        "confirm: Vitamin D, dose, every day, slot: after breakfast",
    ]


def test_add_a_chore_defaults_to_no_schedule(root, capsys):
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "Litter box")
    assert out.splitlines()[-1] == "confirm: Litter box, chore, no schedule, log only"


def test_add_weekly_with_window_and_aliases(root, capsys):
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry",
                    "--schedule", "weekly:sat,wed", "--alias", "washing", "--alias", "Clothes")
    assert code == 0
    assert out.splitlines()[-1] == (
        "confirm: Laundry, chore, every Wed and Sat, can be done 1 day early or 2 days late, "
        "also called: washing, Clothes")


def test_names_ignore_case_and_extra_spaces(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "魚油 EX")
    code, out = run(root, capsys, "item", "edit", "魚油   ex", "--slot", "bedtime")
    assert code == 0 and "slot: bedtime" in out
    code, out = run(root, capsys, "item", "add", "--kind", "dose", "--name", "魚油 ex")
    assert code == 2 and out.startswith("error: name_taken")


def test_names_match_full_width_letters(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "VitD")
    code, out = run(root, capsys, "item", "edit", "ＶｉｔＤ", "--slot", "bedtime")
    assert code == 0 and "slot: bedtime" in out


def test_alias_cannot_take_another_items_name(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry")
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "Sheets", "--alias", "laundry")
    assert code == 2 and out.startswith("error: name_taken")
    code, out = run(root, capsys, "item", "list", "--all")
    assert "Sheets" not in out  # nothing half-saved


def test_unknown_item_lists_existing_names(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D")
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium")
    code, out = run(root, capsys, "item", "edit", "Vitamin", "--slot", "x")
    assert code == 2
    assert out.splitlines()[0] == 'error: unknown_item (no item named "Vitamin"; existing: Magnesium, Vitamin D)'
    assert out.splitlines()[1].startswith("action: ")


def test_edit_schedule_window_name_and_aliases(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--alias", "washing")
    code, out = run(root, capsys, "item", "edit", "washing", "--name", "Wash", "--schedule", "weekly:wed",
                    "--window", "-0,+1", "--alias", "laundry", "--remove-alias", "washing")
    assert code == 0
    assert out.splitlines() == [
        "ok: updated Wash",
        "confirm: Wash, chore, every Wed, can be done 0 days early or 1 day late, also called: laundry",
    ]


def test_remove_unknown_alias(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry")
    code, out = run(root, capsys, "item", "edit", "Laundry", "--remove-alias", "nope")
    assert code == 2 and out.startswith("error: unknown_alias")


def test_bad_schedule_and_window(root, capsys):
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "X", "--schedule", "monthly:1")
    assert code == 1 and out.startswith("error: bad_schedule")
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "X", "--window", "1,2")
    assert code == 1 and out.startswith("error: bad_window")


def test_pause_resume_and_list(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat")
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D", "--slot", "after breakfast", "--alias", "D3")
    code, out = run(root, capsys, "item", "pause", "laundry")
    assert out.splitlines() == ["ok: paused Laundry", "confirm: Laundry, chore, every Wed and Sat, can be done 1 day early or 2 days late, paused"]
    code, out = run(root, capsys, "item", "list")
    assert out.splitlines() == ["- Vitamin D (dose) daily | slot: after breakfast | also: D3"]
    code, out = run(root, capsys, "item", "list", "--all")
    assert "- Laundry (chore) weekly:wed,sat window -1,+2 [paused]" in out.splitlines()
    run(root, capsys, "item", "resume", "Laundry")
    code, out = run(root, capsys, "item", "list", "--kind", "chore")
    assert out.splitlines() == ["- Laundry (chore) weekly:wed,sat window -1,+2"]


def test_empty_list(root, capsys):
    assert run(root, capsys, "item", "list") == (0, "items: none yet")


def test_config_show_and_set(root, capsys):
    code, out = run(root, capsys, "config", "show")
    assert code == 0
    assert f"data_dir: {root / 'data'}" in out.splitlines()
    assert "timezone: Asia/Taipei" in out.splitlines()
    assert "day_boundary: 05:00" in out.splitlines()
    code, out = run(root, capsys, "config", "set", "day-boundary", "4:30")
    assert out.splitlines() == [
        "ok: day_boundary set to 04:30",
        "confirm: a new day starts at 04:30; anything logged before that counts for the previous day; past records keep their day",
    ]
    code, out = run(root, capsys, "config", "set", "timezone", "Europe/Paris")
    assert out.splitlines()[0] == "ok: timezone set to Europe/Paris"
    code, out = run(root, capsys, "config", "set", "timezone", "Mars/Base")
    assert code == 1 and out.startswith("error: bad_setting")


def test_json_output(root, capsys):
    code, out = run(root, capsys, "--json", "item", "add", "--kind", "dose", "--name", "Vitamin D")
    data = json.loads(out)
    assert data["ok"] is True and data["item"]["name"] == "Vitamin D" and data["item"]["schedule"] == "daily"
    assert data["confirm"] == "Vitamin D, dose, every day"
    code, out = run(root, capsys, "item", "edit", "nope", "--slot", "x", "--json")
    assert code == 2 and json.loads(out)["error"] == "unknown_item"


def test_bad_arguments_never_print_usage(root, capsys):
    code, out = run(root, capsys, "item", "add", "--name", "X")
    assert code == 1 and out.startswith("error: bad_arguments")
    code, out = run(root, capsys, "fly")
    assert code == 1 and out.startswith("error: bad_arguments")
    assert capsys.readouterr().err == ""


def test_version(root, capsys):
    code, out = run(root, capsys, "--version")
    assert code == 0 and out.startswith("routine-keeper 1.0.0")


def test_unexpected_exception_never_shows_traceback(root, capsys, monkeypatch):
    from routine_core import cmd_items
    monkeypatch.setattr(cmd_items, "item_list", lambda ctx, a: 1 / 0)
    code, out = run(root, capsys, "item", "list")
    assert code == 1
    assert out.splitlines()[0] == "error: internal_error (ZeroDivisionError)"
    assert "Traceback" not in out


def test_errors_roll_back(root, capsys, monkeypatch):
    from routine_core import cmd_items
    real = cmd_items.item_add

    def add_then_fail(ctx, a):
        real(ctx, a)
        raise ZeroDivisionError
    monkeypatch.setattr(cmd_items, "item_add", add_then_fail)
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D")
    monkeypatch.undo()
    assert run(root, capsys, "item", "list") == (0, "items: none yet")
