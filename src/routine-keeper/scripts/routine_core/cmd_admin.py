"""config show | set, data where | move, export"""
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
    raise RkError("bad_arguments", "data commands are not available yet")
