import json
import sqlite3
from pathlib import Path

from routine_core import storage
from rk_helpers import run, root  # noqa: F401


def seed(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D")
    run(root, capsys, "done", "Vitamin D")


def test_data_where(root, capsys):
    code, out = run(root, capsys, "data", "where")
    assert out.splitlines() == [f"data_dir: {root / 'data'}", f"database: {root / 'data' / 'routine.db'}",
                                "exists: no"]


def test_move_copies_verifies_and_keeps_the_old_file(root, capsys, tmp_path):
    seed(root, capsys)
    target = tmp_path / "elsewhere"
    code, out = run(root, capsys, "data", "move", "--to", str(target))
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == f"ok: data moved to {target}"
    assert lines[1] == f"kept_old_copy: {root / 'data' / 'routine.db.moved-20261014082000'}"
    assert lines[2] == f"confirm: routine-keeper now keeps its data in {target}"
    assert not (root / "data" / "routine.db").exists()
    assert (target / "routine.db").exists()
    assert "Vitamin D" in run(root, capsys, "log", "list")[1]


def test_move_to_where_it_already_is(root, capsys):
    seed(root, capsys)
    code, out = run(root, capsys, "data", "move", "--to", str(root / "data"))
    assert out == f"ok: data is already in {root / 'data'}"


def test_move_refuses_to_overwrite_by_default(root, capsys, tmp_path):
    seed(root, capsys)
    target = tmp_path / "elsewhere"
    target.mkdir()
    sqlite3.connect(target / "routine.db").close()
    code, out = run(root, capsys, "data", "move", "--to", str(target))
    assert code == 2 and out.startswith("error: target_exists")
    assert (root / "data" / "routine.db").exists()


def test_use_existing_switches_without_copying(root, capsys, tmp_path):
    other = tmp_path / "other-root"
    other.mkdir()
    run(other, capsys, "item", "add", "--kind", "chore", "--name", "Laundry")
    seed(root, capsys)
    code, out = run(root, capsys, "data", "move", "--to", str(other / "data"), "--use-existing")
    assert code == 0 and out.splitlines()[0] == f"ok: now using the data in {other / 'data'}"
    assert "Laundry" in run(root, capsys, "item", "list")[1]
    assert (root / "data" / "routine.db").exists()   # left alone


def test_overwrite_keeps_the_replaced_file(root, capsys, tmp_path):
    seed(root, capsys)
    target = tmp_path / "elsewhere"
    target.mkdir()
    sqlite3.connect(target / "routine.db").close()
    code, out = run(root, capsys, "data", "move", "--to", str(target), "--overwrite")
    assert code == 0
    assert f"replaced_copy: {target / 'routine.db.replaced-20261014082000'}" in out.splitlines()
    assert "Vitamin D" in run(root, capsys, "item", "list")[1]


def test_failed_verification_changes_nothing(root, capsys, tmp_path, monkeypatch):
    seed(root, capsys)
    counts = iter([{"items": 1}, {"items": 0}])
    monkeypatch.setattr(storage, "count_rows", lambda conn: next(counts))
    target = tmp_path / "elsewhere"
    code, out = run(root, capsys, "data", "move", "--to", str(target))
    assert code == 3 and out.startswith("error: move_verify_failed")
    assert (root / "data" / "routine.db").exists()
    assert not (target / "routine.db").exists()
    assert list(target.iterdir()) == []
    monkeypatch.undo()
    assert storage.data_dir(root) == root / "data"


def _fail_on_config_save(monkeypatch):
    def boom(root, cfg):
        raise PermissionError("read-only")
    monkeypatch.setattr(storage, "save_config", boom)


def test_failed_config_write_rolls_the_move_back(root, capsys, tmp_path, monkeypatch):
    seed(root, capsys)
    target = tmp_path / "elsewhere"
    target.mkdir()
    sqlite3.connect(target / "routine.db").execute("CREATE TABLE marker(x)")
    _fail_on_config_save(monkeypatch)
    code, out = run(root, capsys, "data", "move", "--to", str(target), "--overwrite")
    assert code == 3 and out.startswith("error: data_unavailable")
    monkeypatch.undo()
    assert sorted(p.name for p in (root / "data").iterdir()) == ["routine.db"]
    assert sorted(p.name for p in target.iterdir()) == ["routine.db"]
    assert sqlite3.connect(target / "routine.db").execute(
        "SELECT name FROM sqlite_master WHERE name='marker'").fetchone()   # the original target is back
    assert storage.data_dir(root) == root / "data"
    assert "Vitamin D" in run(root, capsys, "item", "list")[1]


def test_a_failed_undo_is_reported_and_the_source_still_works(root, capsys, tmp_path, monkeypatch):
    seed(root, capsys)
    target = tmp_path / "elsewhere"
    target.mkdir()
    sqlite3.connect(target / "routine.db").close()
    _fail_on_config_save(monkeypatch)
    real_rename = Path.rename

    def rename(self, dest):
        if self.name.startswith("routine.db.replaced-"):
            raise PermissionError("stuck")
        return real_rename(self, dest)
    monkeypatch.setattr(Path, "rename", rename)
    code, out = run(root, capsys, "data", "move", "--to", str(target), "--overwrite")
    assert code == 3
    assert "could not clean up: " in out.splitlines()[0] and "routine.db.replaced-" in out.splitlines()[0]
    monkeypatch.undo()
    assert storage.data_dir(root) == root / "data"
    assert "Vitamin D" in run(root, capsys, "item", "list")[1]


def test_failed_config_write_on_use_existing(root, capsys, tmp_path, monkeypatch):
    other = tmp_path / "other-root"
    other.mkdir()
    run(other, capsys, "item", "add", "--kind", "chore", "--name", "Laundry")
    _fail_on_config_save(monkeypatch)
    code, out = run(root, capsys, "data", "move", "--to", str(other / "data"), "--use-existing")
    assert code == 3 and out.startswith("error: data_unavailable")


def test_export_to_an_unwritable_place(root, capsys, tmp_path):
    seed(root, capsys)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    code, out = run(root, capsys, "export", "--file", str(blocker / "sub" / "backup.json"))
    assert code == 3 and out.startswith("error: data_unavailable")


def test_move_options_are_exclusive(root, capsys, tmp_path):
    code, out = run(root, capsys, "data", "move", "--to", str(tmp_path), "--use-existing", "--overwrite")
    assert code == 1 and out.startswith("error: bad_arguments")


def test_export_to_stdout_and_file(root, capsys, tmp_path):
    seed(root, capsys)
    data = json.loads(run(root, capsys, "export")[1])
    assert data["version"] == "1.0.0"
    assert data["tables"]["items"][0]["name"] == "Vitamin D"
    assert len(data["tables"]["logs"]) == 1
    target = tmp_path / "backup.json"
    code, out = run(root, capsys, "export", "--file", str(target))
    assert out == f"ok: exported 1 items, 1 logs to {target}"
    assert json.loads(target.read_text())["tables"]["items"][0]["name"] == "Vitamin D"
