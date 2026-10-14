"""Schedule rules, and how completions settle weekly scheduled days. Pure: no database, no clock."""
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
