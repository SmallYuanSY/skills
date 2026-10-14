"""done, skip, log list|edit|delete|restore, note add|list|resolve"""
from datetime import date, timedelta

from .context import Ctx, Result
from .dates import day_of, long_day, parse_at, parse_day, plural, short_day
from .errors import RkError
from .items import find_item
from .logs import (add_log, add_skip, delete_log, done_days, done_logs, edit_log, get_log, list_logs,
                   restore_log, skip_days, undo_skip)
from .notes import add_note, open_notes, resolve_for_item, resolve_note
from .schedule import evaluate_weekly, parse_schedule
from .status import DayStatus, day_status


def item_status(ctx: Ctx, item, q: date) -> DayStatus:
    return day_status(parse_schedule(item["schedule"]), item["window_early"], item["window_late"],
                      date.fromisoformat(item["start_date"]), done_days(ctx.conn, item["id"], q),
                      set(skip_days(ctx.conn, item["id"])), q)


def _offset_text(offset: int) -> str:
    if offset == 0:
        return "on the day"
    return f"{plural(abs(offset), 'day')} {'early' if offset < 0 else 'after'}"


def _settlement_of(ctx: Ctx, item, log_id: int, for_date: date):
    """The settlement of this very log, not just the last one that day (backfills change the order)."""
    start = date.fromisoformat(item["start_date"])
    rows = [r for r in done_logs(ctx.conn, item["id"], for_date)
            if date.fromisoformat(r["for_date"]) >= start - timedelta(days=item["window_early"])]
    sch = parse_schedule(item["schedule"])
    _, settlements = evaluate_weekly(sch.days, item["window_early"], item["window_late"],
                                     [date.fromisoformat(r["for_date"]) for r in rows],
                                     set(skip_days(ctx.conn, item["id"])), start, for_date)
    return next((s for r, s in zip(rows, settlements) if r["id"] == log_id), None)


def _schedule_lines(ctx: Ctx, item, log_id: int, for_date: date) -> list[str]:
    sch = parse_schedule(item["schedule"])
    if sch.kind == "interval":
        before = [d for d in done_days(ctx.conn, item["id"], for_date) if d < for_date]
        nxt = short_day(for_date + timedelta(days=sch.n))
        if not before:
            return [f"schedule: first time; next due {nxt}"]
        planned = before[-1] + timedelta(days=sch.n)
        diff = (for_date - planned).days
        how = "on the planned day" if diff == 0 else f"{plural(abs(diff), 'day')} {'before' if diff < 0 else 'after'}"
        return [f"schedule: planned for {short_day(planned)}, done {how}; next due {nxt}"]
    if sch.kind != "weekly":
        return []
    s = _settlement_of(ctx, item, log_id, for_date)
    if s is None:
        return []
    lines = []
    if s.claimed:
        lines.append(f"schedule: counts for {short_day(s.claimed)} ({_offset_text(s.offset)})")
    lines += [f"schedule: {short_day(m)} merged into this" for m in s.merged]
    if s.extra:
        lines.append("schedule: extra (no scheduled day nearby)")
    return lines


def done(ctx: Ctx, a) -> Result:
    item = find_item(ctx.conn, a.item)
    if not item["active"]:
        raise RkError("item_paused", item["name"])
    at = parse_at(a.at, ctx.tz) if a.at else ctx.now
    for_date = parse_day(a.for_day, ctx.today) if a.for_day else day_of(at, ctx.boundary)
    log_id = add_log(ctx.conn, item, at=at, for_date=for_date, note=a.note, force=a.force, now=ctx.now,
                     today=ctx.today)
    lines = [f"ok: logged #{log_id} {item['name']} for {long_day(for_date)} at {at:%Y-%m-%d %H:%M}"]
    lines += _schedule_lines(ctx, item, log_id, for_date)
    resolved = [] if a.keep_notes else resolve_for_item(ctx.conn, item["id"], log_id, for_date, ctx.now)
    lines += [f"notes_resolved: #{n['id']} {n['text']}" for n in resolved]
    data = {"ok": True, "log": {"id": log_id, "item": item["name"], "for_date": for_date.isoformat(),
                                "at": at.isoformat(timespec="minutes")},
            "schedule": [line.split(": ", 1)[1] for line in lines if line.startswith("schedule: ")],
            "notes_resolved": [{"id": n["id"], "text": n["text"]} for n in resolved]}
    return Result(lines, data)


def skip(ctx: Ctx, a) -> Result:
    item = find_item(ctx.conn, a.item)
    sch = parse_schedule(item["schedule"])
    if sch.kind not in ("daily", "weekly"):
        raise RkError("skip_not_applicable", f"{item['name']} is {item['schedule']}")
    day = parse_day(a.for_day, ctx.today)
    if sch.kind == "weekly" and day.weekday() not in sch.days:
        raise RkError("not_scheduled", f"{item['name']} is not scheduled on {short_day(day)}")
    if a.undo:
        changed = undo_skip(ctx.conn, item, for_date=day, now=ctx.now)
        text = (f"ok: {item['name']} is no longer skipped on {short_day(day)}" if changed
                else f"ok: {item['name']} was not skipped on {short_day(day)}")
    else:
        changed = add_skip(ctx.conn, item, for_date=day, reason=a.reason, now=ctx.now)
        text = (f"ok: skipped {item['name']} on {short_day(day)}" + (f" ({a.reason})" if a.reason else "")
                if changed else f"ok: {item['name']} was already skipped on {short_day(day)}")
    return Result([text], {"ok": True, "item": item["name"], "for_date": day.isoformat(), "changed": changed,
                           "undo": a.undo})


def _log_line(r) -> str:
    line = f"#{r['id']} {long_day(date.fromisoformat(r['for_date']))} {r['item_name']} at {r['at'][:16].replace('T', ' ')}"
    return line + (f" | note: {r['note']}" if r["note"] else "")


def _log_data(r) -> dict:
    return {"id": r["id"], "item": r["item_name"], "for_date": r["for_date"], "at": r["at"], "note": r["note"]}


def log_list(ctx: Ctx, a) -> Result:
    item_id = find_item(ctx.conn, a.item)["id"] if a.item else None
    start = parse_day(a.start, ctx.today) if a.start else None
    end = parse_day(a.end, ctx.today) if a.end else None
    rows = list_logs(ctx.conn, item_id=item_id, start=start, end=end, limit=a.limit)
    return Result([_log_line(r) for r in rows] or ["logs: none"], {"logs": [_log_data(r) for r in rows]})


def log_edit(ctx: Ctx, a) -> Result:
    at = parse_at(a.at, ctx.tz) if a.at else None
    for_date = parse_day(a.for_day, ctx.today) if a.for_day else None
    changes = edit_log(ctx.conn, a.id, at=at, for_date=for_date, note=a.note, force=a.force, boundary=ctx.boundary,
                       now=ctx.now, today=ctx.today)
    row = get_log(ctx.conn, a.id)
    if not changes:
        return Result([f"ok: nothing changed on #{a.id}"], {"ok": True, "changes": {}})
    lines = [f"ok: edited #{a.id} {row['item_name']}"]
    lines += [f"changed: {k} {old} -> {new}" for k, (old, new) in changes.items()]
    return Result(lines, {"ok": True, "log": _log_data(row),
                          "changes": {k: [old, new] for k, (old, new) in changes.items()}})


def log_delete(ctx: Ctx, a) -> Result:
    row = delete_log(ctx.conn, a.id, ctx.now)
    return Result([f"ok: deleted #{a.id} {row['item_name']} (restore with: log restore {a.id})"],
                  {"ok": True, "log": _log_data(row)})


def log_restore(ctx: Ctx, a) -> Result:
    row = restore_log(ctx.conn, a.id, force=a.force)
    return Result([f"ok: restored #{a.id} {row['item_name']}"], {"ok": True, "log": _log_data(row)})


def note_add(ctx: Ctx, a) -> Result:
    item = find_item(ctx.conn, a.item)
    note_id = add_note(ctx.conn, item, a.text, ctx.now)
    text = " ".join(a.text.split())
    return Result([f"ok: note #{note_id} on {item['name']}: {text} (shown until {item['name']} is next logged)"],
                  {"ok": True, "note": {"id": note_id, "item": item["name"], "text": text}})


def note_list(ctx: Ctx, a) -> Result:
    rows = open_notes(ctx.conn)
    lines = [f"#{n['id']} {n['item_name']}: {n['text']} (since {n['created_at'][:10]})" for n in rows]
    return Result(lines or ["notes: none open"],
                  {"notes": [{"id": n["id"], "item": n["item_name"], "text": n["text"]} for n in rows]})


def note_resolve(ctx: Ctx, a) -> Result:
    row = resolve_note(ctx.conn, a.id, ctx.now)
    if row["resolved_at"] is not None:
        return Result([f"ok: note #{a.id} was already resolved"], {"ok": True, "changed": False})
    return Result([f"ok: resolved note #{a.id} ({row['item_name']}: {row['text']})"], {"ok": True, "changed": True})
