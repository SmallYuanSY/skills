"""Where the skill lives, its config.json, and where the data is."""
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from . import db
from .errors import RkError

SKILL_ROOT = Path(__file__).resolve().parents[2]   # routine_core/ -> scripts/ -> the skill folder
CONFIG_NAME = "config.json"
DB_NAME = "routine.db"


def load_config(root: Path) -> dict:
    path = Path(root) / CONFIG_NAME
    if not path.exists():
        return {}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RkError("data_unavailable", f"{path} is not valid JSON") from None
    if not isinstance(cfg, dict):
        raise RkError("data_unavailable", f"{path} is not a JSON object")
    return cfg


def save_config(root: Path, cfg: dict) -> None:
    """Write to a temp file, then rename: a crash never leaves a half-written config."""
    root = Path(root)
    fd, tmp = tempfile.mkstemp(dir=root, prefix=".config-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, root / CONFIG_NAME)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def data_dir(root: Path) -> Path:
    raw = load_config(root).get("data_dir")
    return Path(raw).expanduser() if raw else Path(root) / "data"


def open_db(root: Path, default_tz: str) -> sqlite3.Connection:
    d = data_dir(root)
    try:
        d.mkdir(parents=True, exist_ok=True)
        conn = db.connect(d / DB_NAME)
        db.init(conn, default_tz)
    except RkError:
        raise
    except (OSError, sqlite3.Error) as e:
        raise RkError("data_unavailable", f"{d}: {type(e).__name__}") from None
    return conn


def _quiet_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def count_rows(conn) -> dict:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in db.TABLES}


def _point_config_to(root: Path, target: Path) -> None:
    cfg = load_config(root)
    cfg["data_dir"] = str(target)
    save_config(root, cfg)


def move_data(root: Path, target: Path, *, mode: str, now, default_tz: str) -> dict:
    """Copy the database to target (verified by row counts), point config.json at it, and keep the old
    file renamed. use_existing only switches; overwrite keeps the replaced file renamed."""
    target = Path(target).expanduser().resolve()
    old_dir = data_dir(root).resolve()
    result = {"from": str(old_dir), "to": str(target), "kept_as": None, "replaced_as": None, "changed": True}
    if target == old_dir:
        return {**result, "changed": False}
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RkError("data_unavailable", f"{target}: {type(e).__name__}") from None
    old_db, new_db = old_dir / DB_NAME, target / DB_NAME
    stamp = now.strftime("%Y%m%d%H%M%S")
    if mode == "use_existing":
        if not new_db.exists():
            raise RkError("data_unavailable", f"no {DB_NAME} in {target}")
        try:
            conn = db.connect(new_db)
            db.init(conn, default_tz)
            conn.close()
        except sqlite3.Error as e:
            raise RkError("data_unavailable", f"{new_db}: {type(e).__name__}") from None
        try:
            _point_config_to(root, target)
        except OSError as e:
            raise RkError("data_unavailable", f"{root}: {type(e).__name__}") from None
        return result
    if new_db.exists() and mode != "overwrite":
        raise RkError("target_exists", str(new_db))
    src = open_db(root, default_tz)
    incoming = target / f".{DB_NAME}.incoming-{stamp}"
    try:
        dst = db.connect(incoming)
        src.backup(dst)
        same = count_rows(src) == count_rows(dst)
        dst.close()
    except sqlite3.Error as e:
        _quiet_unlink(incoming)
        raise RkError("data_unavailable", f"{target}: {type(e).__name__}") from None
    finally:
        src.close()
    if not same:
        _quiet_unlink(incoming)
        raise RkError("move_verify_failed", "row counts differ after copying")
    replaced = new_db.with_name(f"{DB_NAME}.replaced-{stamp}")
    undo = []   # (what, how to take it back); the source database is not touched before the switch
    try:
        if new_db.exists():
            new_db.rename(replaced)
            undo.append((f"{replaced} (the database that was in {target})", lambda: replaced.rename(new_db)))
            result["replaced_as"] = str(replaced)
        os.replace(incoming, new_db)
        undo.append((f"{new_db} (the new copy)", lambda: new_db.unlink()))
        _point_config_to(root, target)   # the switch
    except OSError as e:
        left = []
        for what, step in reversed(undo):
            try:
                step()
            except OSError:
                left.append(what)
        _quiet_unlink(incoming)
        detail = f"{target}: {type(e).__name__}; your data is unchanged in {old_dir}"
        if left:
            detail += "; could not clean up: " + ", ".join(left)
        raise RkError("data_unavailable", detail) from None
    kept = old_db.with_name(f"{DB_NAME}.moved-{stamp}")
    try:
        old_db.rename(kept)
        result["kept_as"] = str(kept)
    except OSError:
        result["kept_as"] = str(old_db)   # switched already; the old file just keeps its name
    return result
