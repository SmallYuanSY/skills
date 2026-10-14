"""config show | set, data where | move, export"""
import json
import os
from pathlib import Path

from . import VERSION, db, storage
from .context import Ctx, Result
from .dates import parse_boundary, zone
from .errors import RkError


def config_show(ctx: Ctx, a) -> Result:
    d = storage.data_dir(ctx.root)
    data = {"data_dir": str(d), "database": str(d / storage.DB_NAME), "timezone": db.get_meta(ctx.conn, "timezone"),
            "day_boundary": db.get_meta(ctx.conn, "day_boundary"), "version": VERSION}
    return Result([f"{k}: {v}" for k, v in data.items()], data)


def config_set(ctx: Ctx, a) -> Result:
    if a.key == "day-boundary":
        value = parse_boundary(a.value).strftime("%H:%M")
        db.set_meta(ctx.conn, "day_boundary", value)
        confirm = (f"a new day starts at {value}; anything logged before that counts for the previous day; "
                   "past records keep their day")
        key = "day_boundary"
    else:
        value = zone(a.value.strip()).key
        db.set_meta(ctx.conn, "timezone", value)
        confirm = f"times are now read and shown in {value}; past records keep their day"
        key = "timezone"
    return Result([f"ok: {key} set to {value}", f"confirm: {confirm}"], {"ok": True, key: value, "confirm": confirm})


def data_command(args, *, root, now, default_tz) -> Result:
    if args.sub == "where":
        d = storage.data_dir(root)
        path = d / storage.DB_NAME
        data = {"data_dir": str(d), "database": str(path), "exists": path.exists()}
        return Result([f"data_dir: {d}", f"database: {path}", f"exists: {'yes' if path.exists() else 'no'}"], data)
    mode = "use_existing" if args.use_existing else "overwrite" if args.overwrite else "copy"
    r = storage.move_data(root, Path(args.to), mode=mode, now=now, default_tz=default_tz)
    if not r["changed"]:
        return Result([f"ok: data is already in {r['to']}"], {"ok": True, **r})
    head = f"ok: now using the data in {r['to']}" if mode == "use_existing" else f"ok: data moved to {r['to']}"
    lines = [head]
    if r["kept_as"]:
        lines.append(f"kept_old_copy: {r['kept_as']}")
    if r["replaced_as"]:
        lines.append(f"replaced_copy: {r['replaced_as']}")
    confirm = f"routine-keeper now keeps its data in {r['to']}"
    lines.append(f"confirm: {confirm}")
    return Result(lines, {"ok": True, **r, "confirm": confirm})


def export(ctx: Ctx, a) -> Result:
    tables = {t: [dict(r) for r in ctx.conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in db.TABLES}
    data = {"version": VERSION, "exported_at": ctx.now.isoformat(timespec="seconds"), "tables": tables}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if not a.file:
        return Result([text], data)
    path = Path(a.file).expanduser()
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass   # e.g. an ancestor is a file: there is nothing to clean up
        raise RkError("data_unavailable", f"{path}: {type(e).__name__}") from None
    n_items, n_logs = len(tables["items"]), len(tables["logs"])
    return Result([f"ok: exported {n_items} items, {n_logs} logs to {path}"],
                  {"ok": True, "file": str(path), "items": n_items, "logs": n_logs})
