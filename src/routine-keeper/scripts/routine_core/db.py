"""SQLite schema, and the settings stored with the data (meta)."""
from __future__ import annotations

import sqlite3

from .errors import RkError

SCHEMA_VERSION = 1
DEFAULT_BOUNDARY = "05:00"
TABLES = ("items", "aliases", "logs", "skips", "log_edits", "notes", "meta")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('chore', 'dose')),
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    schedule TEXT NOT NULL,
    window_early INTEGER NOT NULL,
    window_late INTEGER NOT NULL,
    slot TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    start_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aliases (
    key TEXT PRIMARY KEY,
    alias TEXT NOT NULL,
    item_id INTEGER NOT NULL REFERENCES items(id)
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    at TEXT NOT NULL,
    for_date TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS logs_item_day ON logs(item_id, for_date);
CREATE TABLE IF NOT EXISTS skips (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    for_date TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS log_edits (
    id INTEGER PRIMARY KEY,
    log_id INTEGER NOT NULL REFERENCES logs(id),
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    edited_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by_log INTEGER REFERENCES logs(id)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))


def init(conn, default_tz: str) -> None:
    conn.executescript(_SCHEMA)
    version = get_meta(conn, "schema_version")
    if version is not None and int(version) > SCHEMA_VERSION:
        raise RkError("data_version_newer", f"data v{version}, skill v{SCHEMA_VERSION}")
    for key, value in (("schema_version", str(SCHEMA_VERSION)), ("day_boundary", DEFAULT_BOUNDARY),
                       ("timezone", default_tz)):
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)", (key, value))
    conn.commit()
