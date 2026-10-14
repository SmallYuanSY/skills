"""Days, the day boundary, and time zones. A record's day is its local time minus the boundary."""
import os
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import RkError

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_AT = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})$")
_HM = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_boundary(text: str) -> time:
    m = _HM.match(text.strip())
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        raise RkError("bad_setting", f"day-boundary {text!r}")
    return time(int(m[1]), int(m[2]))


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise RkError("bad_setting", f"timezone {name!r}") from None


def _localtime_name() -> str:
    target = os.path.realpath("/etc/localtime")
    marker = "zoneinfo/"
    return target.split(marker, 1)[1] if marker in target else ""


def system_timezone() -> str:
    for cand in (os.environ.get("TZ", "").lstrip(":"), _localtime_name()):
        if cand:
            try:
                ZoneInfo(cand)
                return cand
            except (ZoneInfoNotFoundError, ValueError):
                continue
    return "UTC"


def day_of(at: datetime, boundary: time) -> date:
    d = at.date()
    return d - timedelta(days=1) if at.time() < boundary else d


def parse_day(text: str, today: date) -> date:
    t = text.strip().lower()
    if t == "today":
        return today
    if t == "yesterday":
        return today - timedelta(days=1)
    if _DAY.match(t):
        try:
            return date.fromisoformat(t)
        except ValueError:
            pass
    raise RkError("bad_date", text)


def parse_at(text: str, tz: ZoneInfo) -> datetime:
    m = _AT.match(text.strip())
    if m:
        try:
            d = date.fromisoformat(m[1])
            return datetime(d.year, d.month, d.day, int(m[2]), int(m[3]), tzinfo=tz)
        except ValueError:
            pass
    raise RkError("bad_time", text)


def short_day(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()].capitalize()} {d.isoformat()}"


def long_day(d: date) -> str:
    return f"{d.isoformat()} ({WEEKDAYS[d.weekday()].capitalize()})"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def ago(d: date, q: date) -> str:
    n = (q - d).days
    if n == 0:
        return "today"
    return f"{plural(n, 'day')} ago" if n > 0 else f"in {plural(-n, 'day')}"
