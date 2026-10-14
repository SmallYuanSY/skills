"""Reminders attached to an item, shown until the item is next logged."""
from .errors import RkError


def add_note(conn, item, text: str, now) -> int:
    text = " ".join(text.split())
    if not text:
        raise RkError("bad_arguments", "empty note")
    cur = conn.execute("INSERT INTO notes(item_id, text, created_at) VALUES (?, ?, ?)",
                       (item["id"], text, now.isoformat(timespec="seconds")))
    return cur.lastrowid


def open_notes(conn, item_id=None):
    sql = ("SELECT notes.*, items.name AS item_name FROM notes JOIN items ON items.id = notes.item_id"
           " WHERE notes.resolved_at IS NULL")
    args = []
    if item_id is not None:
        sql += " AND notes.item_id=?"
        args.append(item_id)
    return conn.execute(sql + " ORDER BY notes.id", args).fetchall()


def resolve_note(conn, note_id: int, now):
    row = conn.execute("SELECT notes.*, items.name AS item_name FROM notes JOIN items ON items.id = notes.item_id"
                       " WHERE notes.id=?", (note_id,)).fetchone()
    if row is None:
        raise RkError("unknown_note", f"#{note_id}")
    if row["resolved_at"] is None:
        conn.execute("UPDATE notes SET resolved_at=? WHERE id=?", (now.isoformat(timespec="seconds"), note_id))
    return row


def resolve_for_item(conn, item_id: int, log_id: int, now):
    rows = open_notes(conn, item_id)
    conn.execute("UPDATE notes SET resolved_at=?, resolved_by_log=? WHERE item_id=? AND resolved_at IS NULL",
                 (now.isoformat(timespec="seconds"), log_id, item_id))
    return rows
