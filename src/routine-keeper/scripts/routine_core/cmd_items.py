"""item add | edit | pause | resume | list"""
from .context import Ctx, Result
from .items import add_item, aliases_of, describe_item, edit_item, item_data, list_items, set_active


def _confirmed(ctx: Ctx, item, head: str) -> Result:
    aliases = aliases_of(ctx.conn, item["id"])
    text = describe_item(item, aliases)
    return Result([head, f"confirm: {text}"], {"ok": True, "item": item_data(item, aliases), "confirm": text})


def item_add(ctx: Ctx, a) -> Result:
    item_id = add_item(ctx.conn, kind=a.kind, name=a.name, schedule=a.schedule, window=a.window, slot=a.slot,
                       aliases=a.alias, today=ctx.today, now=ctx.now)
    item = ctx.conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return _confirmed(ctx, item, f"ok: added {item['name']} ({item['kind']})")


def item_edit(ctx: Ctx, a) -> Result:
    item = edit_item(ctx.conn, a.item, name=a.name, schedule=a.schedule, window=a.window, slot=a.slot,
                     add_aliases=a.alias, remove_aliases=a.remove_alias, today=ctx.today, now=ctx.now)
    return _confirmed(ctx, item, f"ok: updated {item['name']}")


def item_pause(ctx: Ctx, a) -> Result:
    item = set_active(ctx.conn, a.item, False, ctx.now)
    return _confirmed(ctx, item, f"ok: paused {item['name']}")


def item_resume(ctx: Ctx, a) -> Result:
    item = set_active(ctx.conn, a.item, True, ctx.now)
    return _confirmed(ctx, item, f"ok: resumed {item['name']}")


def item_list(ctx: Ctx, a) -> Result:
    rows = list_items(ctx.conn, kind=a.kind, include_paused=a.all)
    lines, data = [], []
    for item in rows:
        aliases = aliases_of(ctx.conn, item["id"])
        line = f"- {item['name']} ({item['kind']}) {item['schedule']}"
        if item["schedule"].startswith("weekly:"):
            line += f" window -{item['window_early']},+{item['window_late']}"
        if item["slot"]:
            line += f" | slot: {item['slot']}"
        if aliases:
            line += " | also: " + ", ".join(aliases)
        if not item["active"]:
            line += " [paused]"
        lines.append(line)
        data.append(item_data(item, aliases))
    return Result(lines or ["items: none yet"], {"items": data})
