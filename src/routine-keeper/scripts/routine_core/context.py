"""What every command gets: the open database, the time, and the day settings."""
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from . import db
from .dates import day_of, parse_boundary, zone


@dataclass
class Ctx:
    conn: object
    root: Path
    now: datetime        # aware, in the configured timezone, seconds dropped
    tz: ZoneInfo
    boundary: time

    @property
    def today(self) -> date:
        return day_of(self.now, self.boundary)

    @classmethod
    def build(cls, conn, root: Path, now: datetime) -> "Ctx":
        tz = zone(db.get_meta(conn, "timezone"))
        boundary = parse_boundary(db.get_meta(conn, "day_boundary"))
        return cls(conn, root, now.astimezone(tz).replace(second=0, microsecond=0), tz, boundary)


@dataclass
class Result:
    lines: list[str]
    data: dict = field(default_factory=dict)
