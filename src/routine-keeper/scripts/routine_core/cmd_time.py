"""time today | yesterday | YYYY-MM-DD"""
from __future__ import annotations

from datetime import date

from .cmd_logs import item_status
from .context import Ctx, Result
from .dates import ago, long_day, parse_day, plural, short_day
from .items import list_items
from .logs import logs_on, skip_days
from .notes import open_notes
from .status import DayStatus

MISSED_LIST_MAX = 3


def state_text(st: DayStatus, q: date, times: list[str], skip_reason: str | None, today: date) -> str:
    s = st.state
    if s == "done":
        text = "done " + ", ".join(times)
        if st.also_due:
            text += f" | still due {short_day(st.also_due)}"
    elif s == "skipped":
        text = "skipped" + (f" ({skip_reason})" if skip_reason else "")
    elif s == "idle":
        text = "no schedule"
    elif s == "never_done":
        text = "never done"
    elif s == "upcoming":
        text = f"next {short_day(st.ref)} ({ago(st.ref, q)})"
    elif s == "due":
        if st.ref == q:
            text = "due today" if q == today else "due on the day"
        elif st.ref < q:
            text = f"due since {short_day(st.ref)} ({plural((q - st.ref).days, 'day')})"
        else:
            text = f"due {short_day(st.ref)} (can be done from today)"
    elif s == "makeup":
        text = f"makeup for {short_day(st.ref)}"
    elif s == "missed":
        text = f"missed {short_day(st.ref)}"
    else:
        text = s   # not_done
    parts = [text]
    if s != "done" and st.last_done:
        parts.append(f"last done {st.last_done.isoformat()} ({ago(st.last_done, q)})")
    elif s == "idle":
        parts.append("never done")
    others = [m for m in st.missed if not (s == "missed" and m == st.ref)]
    if len(others) > MISSED_LIST_MAX:
        parts.append(f"missed {len(others)} times since {others[0].isoformat()}")
    elif others:
        parts.append("missed: " + ", ".join(short_day(m) for m in others))
    return " | ".join(parts)


def time_day(ctx: Ctx, a) -> Result:
    q = parse_day(a.day, ctx.today)
    lines = [f"date: {long_day(q)}", f"now: {ctx.now:%Y-%m-%d %H:%M} {ctx.tz.key}",
             f"day_boundary: {ctx.boundary:%H:%M}"]
    data = {"date": q.isoformat(), "now": ctx.now.isoformat(timespec="minutes"), "timezone": ctx.tz.key,
            "day_boundary": f"{ctx.boundary:%H:%M}", "items": []}
    for kind, title in (("dose", "doses"), ("chore", "chores")):
        lines += ["", f"{title}:"]
        items = list_items(ctx.conn, kind=kind)
        if not items:
            lines.append("- (none)")
        for item in items:
            st = item_status(ctx, item, q)
            times = [r["at"][11:16] for r in logs_on(ctx.conn, item["id"], q)]
            text = state_text(st, q, times, skip_days(ctx.conn, item["id"]).get(q), ctx.today)
            label = item["schedule"] + (f", {item['slot']}" if item["slot"] else "")
            lines.append(f"- {item['name']} [{label}]: {text}")
            notes = open_notes(ctx.conn, item["id"])
            lines += [f"  note #{n['id']}: {n['text']}" for n in notes]
            data["items"].append({
                "name": item["name"], "kind": kind, "schedule": item["schedule"], "slot": item["slot"],
                "state": st.state, "ref": st.ref.isoformat() if st.ref else None,
                "last_done": st.last_done.isoformat() if st.last_done else None,
                "missed": [m.isoformat() for m in st.missed], "done_times": times,
                "also_due": st.also_due.isoformat() if st.also_due else None,
                "notes": [{"id": n["id"], "text": n["text"]} for n in notes], "text": text})
    return Result(lines, data)
