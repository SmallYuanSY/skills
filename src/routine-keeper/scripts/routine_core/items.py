"""Tracked items (chores and doses), their names, aliases, and schedules."""
from .errors import RkError
from .schedule import describe, format_schedule, parse_schedule, parse_window

DEFAULT_SCHEDULE = {"chore": "none", "dose": "daily"}
DEFAULT_WINDOW = (1, 2)


def _clean(text: str, what: str = "name") -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        raise RkError("bad_arguments", f"empty {what}")
    return cleaned


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _owner(conn, key: str) -> int | None:
    row = (conn.execute("SELECT id FROM items WHERE name_key=?", (key,)).fetchone()
           or conn.execute("SELECT item_id AS id FROM aliases WHERE key=?", (key,)).fetchone())
    return row["id"] if row else None


def _claim(conn, name: str, item_id: int | None = None) -> None:
    owner = _owner(conn, _key(name))
    if owner is not None and owner != item_id:
        raise RkError("name_taken", name)


def _get(conn, item_id: int):
    return conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()


def find_item(conn, ref: str):
    item_id = _owner(conn, _key(ref))
    if item_id is None:
        names = [r["name"] for r in conn.execute("SELECT name FROM items WHERE active=1 ORDER BY name")]
        raise RkError("unknown_item", f'no item named "{ref}"; existing: {", ".join(names) or "none yet"}')
    return _get(conn, item_id)


def aliases_of(conn, item_id: int) -> list[str]:
    return [r["alias"] for r in conn.execute("SELECT alias FROM aliases WHERE item_id=? ORDER BY rowid", (item_id,))]


def _add_alias(conn, item, alias: str) -> None:
    alias = _clean(alias, "alias")
    _claim(conn, alias, item["id"])
    if _key(alias) != item["name_key"]:
        conn.execute("INSERT OR IGNORE INTO aliases(key, alias, item_id) VALUES (?, ?, ?)",
                     (_key(alias), alias, item["id"]))


def add_item(conn, *, kind, name, schedule, window, slot, aliases, today, now) -> int:
    name = _clean(name)
    _claim(conn, name)
    sch = format_schedule(parse_schedule(schedule or DEFAULT_SCHEDULE[kind]))
    early, late = parse_window(window) if window else DEFAULT_WINDOW
    ts = now.isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO items(kind, name, name_key, schedule, window_early, window_late, slot, start_date,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (kind, name, _key(name), sch, early, late, (slot or "").strip() or None, today.isoformat(), ts, ts))
    item = _get(conn, cur.lastrowid)
    for alias in aliases:
        _add_alias(conn, item, alias)
    return item["id"]


def edit_item(conn, ref, *, name=None, schedule=None, window=None, slot=None, add_aliases=(), remove_aliases=(),
              today, now):
    item = find_item(conn, ref)
    changes = {}
    if name is not None:
        name = _clean(name)
        _claim(conn, name, item["id"])
        conn.execute("DELETE FROM aliases WHERE key=? AND item_id=?", (_key(name), item["id"]))
        changes.update(name=name, name_key=_key(name))
    if schedule is not None:
        changes["schedule"] = format_schedule(parse_schedule(schedule))
    if window is not None:
        changes["window_early"], changes["window_late"] = parse_window(window)
    if slot is not None:
        changes["slot"] = slot.strip() or None
    rule_changed = any(k in changes and changes[k] != item[k] for k in ("schedule", "window_early", "window_late"))
    if rule_changed:
        changes["start_date"] = today.isoformat()   # judge the new rule from today on, not against old history
    if changes:
        changes["updated_at"] = now.isoformat(timespec="seconds")
        conn.execute(f"UPDATE items SET {', '.join(f'{k}=?' for k in changes)} WHERE id=?",
                     (*changes.values(), item["id"]))
    for alias in remove_aliases:
        if conn.execute("DELETE FROM aliases WHERE key=? AND item_id=?", (_key(alias), item["id"])).rowcount == 0:
            raise RkError("unknown_alias", f'"{alias}" is not an alias of {item["name"]}')
    item = _get(conn, item["id"])
    for alias in add_aliases:
        _add_alias(conn, item, alias)
    return item


def set_active(conn, ref, active: bool, now, today=None):
    """Resuming judges the schedule from today on, so the paused stretch never counts as missed."""
    item = find_item(conn, ref)
    conn.execute("UPDATE items SET active=?, updated_at=? WHERE id=?",
                 (int(active), now.isoformat(timespec="seconds"), item["id"]))
    if active and not item["active"] and today is not None:
        conn.execute("UPDATE items SET start_date=? WHERE id=?", (today.isoformat(), item["id"]))
    return _get(conn, item["id"])


def list_items(conn, kind=None, include_paused=False):
    sql, args = "SELECT * FROM items WHERE 1=1", []
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if not include_paused:
        sql += " AND active=1"
    return conn.execute(sql + " ORDER BY kind DESC, name", args).fetchall()


def describe_item(item, aliases: list[str]) -> str:
    parts = [item["name"], item["kind"],
             describe(parse_schedule(item["schedule"]), item["window_early"], item["window_late"])]
    if item["slot"]:
        parts.append(f"slot: {item['slot']}")
    if aliases:
        parts.append("also called: " + ", ".join(aliases))
    if not item["active"]:
        parts.append("paused")
    return ", ".join(parts)


def item_data(item, aliases: list[str]) -> dict:
    return {"id": item["id"], "name": item["name"], "kind": item["kind"], "schedule": item["schedule"],
            "window": [item["window_early"], item["window_late"]], "slot": item["slot"],
            "aliases": aliases, "active": bool(item["active"])}
