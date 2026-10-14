"""Where an item stands on a given day. Pure: no database, no clock."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .schedule import Schedule, Settlement, evaluate_weekly


@dataclass
class DayStatus:
    state: str                    # done|not_done|skipped|idle|never_done|upcoming|due|makeup|missed
    ref: date | None = None       # the scheduled day (weekly) or due date (interval) the state is about
    last_done: date | None = None
    missed: list[date] = field(default_factory=list)
    settlement: Settlement | None = None
    also_due: date | None = None  # weekly: done today, yet a scheduled day is still open (e.g. fri,sat)


def _next_weekly(after: date, days: tuple[int, ...], skips: set[date]) -> date:
    d = after + timedelta(days=1)
    while d.weekday() not in days or d in skips:
        d += timedelta(days=1)
    return d


def day_status(sch: Schedule, early: int, late: int, start: date, done_days: list[date],
               skips: set[date], q: date) -> DayStatus:
    done = sorted(x for x in done_days if x <= q)
    last = done[-1] if done else None
    done_today = q in done
    if sch.kind == "daily":
        return DayStatus("done" if done_today else "skipped" if q in skips else "not_done", last_done=last)
    if sch.kind == "none":
        return DayStatus("done" if done_today else "idle", last_done=last)
    if sch.kind == "interval":
        if done_today:
            return DayStatus("done", ref=q + timedelta(days=sch.n), last_done=q)
        if last is None:
            return DayStatus("never_done")
        due = last + timedelta(days=sch.n)
        return DayStatus("upcoming" if q < due else "due", ref=due, last_done=last)
    counted = [x for x in done if x >= start - timedelta(days=early)]
    occ, settlements = evaluate_weekly(sch.days, early, late, counted, skips, start, q)
    missed = [o.day for o in occ if o.status == "missed"]
    pending = [o for o in occ if o.status in ("due", "makeup")]
    if done_today:
        mine = [s for s in settlements if s.day == q]
        return DayStatus("done", last_done=q, missed=missed, settlement=mine[-1] if mine else None,
                         also_due=pending[0].day if pending else None)
    if pending:
        return DayStatus(pending[0].status, ref=pending[0].day, last_done=last, missed=missed)
    if missed:
        return DayStatus("missed", ref=missed[-1], last_done=last, missed=missed)
    if any(o.day == q and o.status == "skipped" for o in occ):
        return DayStatus("skipped", ref=q, last_done=last)
    # every scheduled day up to q + early is settled, so the next one comes after that,
    # and never before the day the current rule started
    after = max(q + timedelta(days=early), start - timedelta(days=1))
    return DayStatus("upcoming", ref=_next_weekly(after, sch.days, skips), last_done=last)
