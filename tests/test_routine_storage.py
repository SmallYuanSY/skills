import json
import sqlite3

import pytest

from routine_core import db, storage
from routine_core.errors import RkError


def test_skill_root_is_two_levels_above_the_package():
    assert (storage.SKILL_ROOT / "scripts" / "routine_core" / "storage.py").is_file()


def test_default_data_dir_is_inside_the_skill(tmp_path):
    assert storage.data_dir(tmp_path) == tmp_path / "data"


def test_config_points_somewhere_else(tmp_path):
    storage.save_config(tmp_path, {"data_dir": str(tmp_path / "elsewhere")})
    assert storage.data_dir(tmp_path) == tmp_path / "elsewhere"
    assert json.loads((tmp_path / "config.json").read_text())["data_dir"].endswith("elsewhere")


def test_save_config_leaves_no_temp_files(tmp_path):
    storage.save_config(tmp_path, {"data_dir": "x"})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]


def test_broken_config_is_data_unavailable(tmp_path):
    (tmp_path / "config.json").write_text("{not json")
    with pytest.raises(RkError) as e:
        storage.data_dir(tmp_path)
    assert e.value.code == "data_unavailable"


def test_open_db_creates_schema_and_defaults(tmp_path):
    conn = storage.open_db(tmp_path, "Asia/Taipei")
    assert (tmp_path / "data" / "routine.db").is_file()
    assert db.get_meta(conn, "timezone") == "Asia/Taipei"
    assert db.get_meta(conn, "day_boundary") == "05:00"
    assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
    for table in db.TABLES:
        conn.execute(f"SELECT COUNT(*) FROM {table}")


def test_open_db_keeps_existing_settings(tmp_path):
    conn = storage.open_db(tmp_path, "Asia/Taipei")
    db.set_meta(conn, "timezone", "Europe/Paris")
    conn.commit()
    conn.close()
    assert db.get_meta(storage.open_db(tmp_path, "Asia/Taipei"), "timezone") == "Europe/Paris"


def test_newer_data_is_refused(tmp_path):
    conn = storage.open_db(tmp_path, "UTC")
    db.set_meta(conn, "schema_version", str(db.SCHEMA_VERSION + 1))
    conn.commit()
    conn.close()
    with pytest.raises(RkError) as e:
        storage.open_db(tmp_path, "UTC")
    assert e.value.code == "data_version_newer"


def test_corrupt_database_is_data_unavailable(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "routine.db").write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(RkError) as e:
        storage.open_db(tmp_path, "UTC")
    assert e.value.code == "data_unavailable"


def test_unwritable_data_dir_is_data_unavailable(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    storage.save_config(tmp_path, {"data_dir": str(blocker / "sub")})
    with pytest.raises(RkError) as e:
        storage.open_db(tmp_path, "UTC")
    assert e.value.code == "data_unavailable"
