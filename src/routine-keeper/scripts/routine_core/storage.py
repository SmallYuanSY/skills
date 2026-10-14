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
