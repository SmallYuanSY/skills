"""Schedule rules, and how completions settle weekly scheduled days. Pure: no database, no clock."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from .dates import WEEKDAYS, plural
from .errors import RkError

_WINDOW = re.compile(r"^-(\d),\+?(\d)$")


@dataclass(frozen=True)
class Schedule:
    kind: str                    # "daily" | "none" | "interval" | "weekly"
    n: int = 0                   # interval: days between
    days: tuple[int, ...] = ()   # weekly: 0=Mon .. 6=Sun, sorted, unique


def parse_schedule(text: str) -> Schedule:
    t = text.strip().lower().replace(" ", "")
    if t in ("daily", "none"):
        return Schedule(t)
    if t.startswith("interval:"):
        n = t[len("interval:"):]
        if n.isdigit() and 1 <= int(n) <= 365:
            return Schedule("interval", n=int(n))
    if t.startswith("weekly:"):
        parts = [p for p in t[len("weekly:"):].split(",") if p]
        if parts and all(p in WEEKDAYS for p in parts):
            return Schedule("weekly", days=tuple(sorted({WEEKDAYS.index(p) for p in parts})))
    raise RkError("bad_schedule", text)


def format_schedule(s: Schedule) -> str:
    if s.kind == "interval":
        return f"interval:{s.n}"
    if s.kind == "weekly":
        return "weekly:" + ",".join(WEEKDAYS[d] for d in s.days)
    return s.kind


def parse_window(text: str) -> tuple[int, int]:
    m = _WINDOW.match(text.strip().replace(" ", ""))
    if not m or int(m[1]) > 6 or int(m[2]) > 6:
        raise RkError("bad_window", text)
    return int(m[1]), int(m[2])


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def describe(s: Schedule, early: int, late: int) -> str:
    if s.kind == "daily":
        return "every day"
    if s.kind == "none":
        return "no schedule, log only"
    if s.kind == "interval":
        return f"every {plural(s.n, 'day')} after the last time it was done"
    days = _join([WEEKDAYS[d].capitalize() for d in s.days])
    if early == 0 and late == 0:
        return f"every {days}, only on the day"
    return f"every {days}, can be done {plural(early, 'day')} early or {plural(late, 'day')} late"


@dataclass
class Occurrence:
    day: date
    status: str               # due|makeup|missed|done|done_early|done_late|merged|skipped
    by: date | None = None    # the completion day that settled it


@dataclass
class Settlement:
    day: date                  # the completion
    claimed: date | None       # the scheduled day it counted for
    offset: int                # completion minus claimed day, in days
    merged: list[date] = field(default_factory=list)

    @property
    def extra(self) -> bool:
        return self.claimed is None and not self.merged


def evaluate_weekly(days, early, late, completions, skips, start, until):
    """Settle each scheduled day in [start, until + early] against the completions (all <= until).

    A completion claims the earliest open day whose window holds it, so making up comes before
    doing early. It also settles every other open day before it as "merged": doing it once clears
    what was missed, nothing piles up. Skipped days are never claimed or merged.
    `completions` must already be in time order; settlements[i] belongs to completions[i].
    """
    before, after = timedelta(days=early), timedelta(days=late)
    occ_days = []
    d = start
    while d <= until + before:
        if d.weekday() in days:
            occ_days.append(d)
        d += timedelta(days=1)
    state: dict[date, tuple[str, date | None]] = {o: ("skipped", None) for o in occ_days if o in skips}
    settlements = []
    for c in completions:
        open_days = [o for o in occ_days if o not in state]
        holding = [o for o in open_days if o - before <= c <= o + after]
        claimed = min(holding) if holding else None
        offset = (c - claimed).days if claimed else 0
        if claimed:
            state[claimed] = ("done" if offset == 0 else "done_early" if offset < 0 else "done_late", c)
        merged = [o for o in open_days if o != claimed and o < c]
        for o in merged:
            state[o] = ("merged", c)
        settlements.append(Settlement(c, claimed, offset, merged))
    result = []
    for o in occ_days:
        if o in state:
            status, by = state[o]
        elif o >= until:   # only days up to until + early are listed, so this is inside the early window
            status, by = "due", None
        elif o + after >= until:
            status, by = "makeup", None
        else:
            status, by = "missed", None
        result.append(Occurrence(o, status, by))
    return result, settlements
