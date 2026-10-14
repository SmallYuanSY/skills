"""Completions, skips, and fixes to past records. Deletes are soft and can be undone."""
from datetime import date

from .dates import day_of
from .errors import RkError


def _ts(now) -> str:
    return now.isoformat(timespec="seconds")


def check_not_future(at, for_date, now, today) -> None:
    if at is not None and at > now:
        raise RkError("future_time", f"{at:%Y-%m-%d %H:%M} is later than now ({now:%Y-%m-%d %H:%M})")
    if for_date is not None and for_date > today:
        raise RkError("future_time", f"{for_date} is after today ({today})")


def logs_on(conn, item_id: int, day: date):
    return conn.execute("SELECT * FROM logs WHERE item_id=? AND for_date=? AND deleted_at IS NULL"
                        " ORDER BY julianday(at), id",
                        (item_id, day.isoformat())).fetchall()


def _check_dose_once(conn, item_id: int, kind: str, name: str, day: date, *, force: bool, exclude: int | None = None):
    if kind != "dose" or force:
        return
    same = [r for r in logs_on(conn, item_id, day) if r["id"] != exclude]
    if same:
        raise RkError("already_logged", f'{name} for {day} as #{same[0]["id"]} at {same[0]["at"][11:16]}')


def add_log(conn, item, *, at, for_date, note, force, now, today) -> int:
    check_not_future(at, for_date, now, today)
    _check_dose_once(conn, item["id"], item["kind"], item["name"], for_date, force=force)
    cur = conn.execute("INSERT INTO logs(item_id, at, for_date, note, created_at) VALUES (?, ?, ?, ?, ?)",
                       (item["id"], at.isoformat(timespec="minutes"), for_date.isoformat(), note, _ts(now)))
    return cur.lastrowid


def done_logs(conn, item_id: int, until: date):
    return conn.execute("SELECT * FROM logs WHERE item_id=? AND deleted_at IS NULL AND for_date<=?"
                        " ORDER BY for_date, julianday(at), id", (item_id, until.isoformat())).fetchall()


def done_days(conn, item_id: int, until: date) -> list[date]:
    return [date.fromisoformat(r["for_date"]) for r in done_logs(conn, item_id, until)]


def skip_days(conn, item_id: int) -> dict:
    rows = conn.execute("SELECT for_date, reason FROM skips WHERE item_id=? AND deleted_at IS NULL", (item_id,))
    return {date.fromisoformat(r["for_date"]): r["reason"] for r in rows}


def add_skip(conn, item, *, for_date, reason, now) -> bool:
    """Unlike logs, a skip may be planned ahead ("away on Saturday")."""
    if for_date in skip_days(conn, item["id"]):
        return False
    conn.execute("INSERT INTO skips(item_id, for_date, reason, created_at) VALUES (?, ?, ?, ?)",
                 (item["id"], for_date.isoformat(), reason, _ts(now)))
    return True


def undo_skip(conn, item, *, for_date, now) -> bool:
    cur = conn.execute("UPDATE skips SET deleted_at=? WHERE item_id=? AND for_date=? AND deleted_at IS NULL",
                       (_ts(now), item["id"], for_date.isoformat()))
    return cur.rowcount > 0


def get_log(conn, log_id: int, *, deleted: bool | None = False):
    sql = ("SELECT logs.*, items.name AS item_name, items.kind AS item_kind FROM logs"
           " JOIN items ON items.id = logs.item_id WHERE logs.id=?")
    if deleted is True:
        sql += " AND logs.deleted_at IS NOT NULL"
    elif deleted is False:
        sql += " AND logs.deleted_at IS NULL"
    row = conn.execute(sql, (log_id,)).fetchone()
    if row is None:
        raise RkError("unknown_log", f"#{log_id}" + (" is not deleted" if deleted is True else ""))
    return row


def list_logs(conn, *, item_id=None, start=None, end=None, limit=50):
    sql = ("SELECT logs.*, items.name AS item_name FROM logs JOIN items ON items.id = logs.item_id"
           " WHERE logs.deleted_at IS NULL")
    args = []
    if item_id is not None:
        sql += " AND logs.item_id=?"
        args.append(item_id)
    if start is not None:
        sql += " AND logs.for_date>=?"
        args.append(start.isoformat())
    if end is not None:
        sql += " AND logs.for_date<=?"
        args.append(end.isoformat())
    sql += " ORDER BY logs.for_date DESC, julianday(logs.at) DESC, logs.id DESC LIMIT ?"
    args.append(max(1, limit))
    return conn.execute(sql, args).fetchall()


def edit_log(conn, log_id: int, *, at=None, for_date=None, note=None, force=False, boundary, now, today) -> dict:
    row = get_log(conn, log_id)
    if at is not None and for_date is None:
        for_date = day_of(at, boundary)
    check_not_future(at, for_date, now, today)
    if for_date is not None and for_date.isoformat() != row["for_date"]:
        _check_dose_once(conn, row["item_id"], row["item_kind"], row["item_name"], for_date, force=force,
                         exclude=log_id)
    new = {}
    if at is not None:
        new["at"] = at.isoformat(timespec="minutes")
    if for_date is not None:
        new["for_date"] = for_date.isoformat()
    if note is not None:
        new["note"] = note.strip() or None
    changes = {k: (row[k], v) for k, v in new.items() if row[k] != v}
    for field_name, (old, value) in changes.items():
        conn.execute(f"UPDATE logs SET {field_name}=? WHERE id=?", (value, log_id))
        conn.execute("INSERT INTO log_edits(log_id, field, old_value, new_value, edited_at) VALUES (?, ?, ?, ?, ?)",
                     (log_id, field_name, old, value, _ts(now)))
    return changes


def delete_log(conn, log_id: int, now):
    row = get_log(conn, log_id)
    conn.execute("UPDATE logs SET deleted_at=? WHERE id=?", (_ts(now), log_id))
    return row


def restore_log(conn, log_id: int, *, force: bool = False):
    row = get_log(conn, log_id, deleted=True)
    _check_dose_once(conn, row["item_id"], row["item_kind"], row["item_name"], date.fromisoformat(row["for_date"]),
                     force=force)
    conn.execute("UPDATE logs SET deleted_at=NULL WHERE id=?", (log_id,))
    return row
