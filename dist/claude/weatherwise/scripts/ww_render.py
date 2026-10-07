"""Turns a Report into plain key: value lines for the model to read."""
from datetime import date, datetime

from ww_errors import ACTIONS, WwError
from ww_model import Place, Report

# Weekday names come from here, not strftime("%a"), which follows the machine's locale
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

ALERTS_UNSUPPORTED = (
    "alerts: unsupported (this source has no official alert data here; "
    "do not tell the user there are none)"
)


def _or_unknown(value: float | None, fmt: str, suffix: str = "") -> str:
    return "unknown" if value is None else f"{value:{fmt}}{suffix}"


def render_report(report: Report, place: Place, now: datetime, notice: str | None = None) -> str:
    lines = []
    if notice:
        lines.append(f"notice: {notice}")
    lines.append(f"source: {report.source}")
    lines.append(f"location: {place.name} ({place.lat:.3f}, {place.lon:.3f}) timezone={place.timezone}")
    lines.append(f"local_time: {now:%Y-%m-%dT%H:%M} {WEEKDAYS[now.weekday()]}")
    c = report.current
    if c:
        lines.append(
            f"current: {c.condition}, {c.temperature:.1f}°C, feels {c.feels_like:.1f}°C, "
            f"humidity {c.humidity:.0f}%, wind {c.wind_kmh:.0f} km/h, UV {_or_unknown(c.uv, '.0f')}"
        )
    if report.days:
        lines.append("daily:")
        for d in report.days:
            weekday = WEEKDAYS[date.fromisoformat(d.date).weekday()]
            lines.append(
                f"  {d.date} {weekday}: {d.condition}, {d.temp_min:.0f}–{d.temp_max:.0f}°C, "
                f"precipitation chance {_or_unknown(d.precip_chance, '.0f', '%')}"
            )
    if report.alerts is None:
        lines.append(ALERTS_UNSUPPORTED)
    elif not report.alerts:
        lines.append("alerts: none")
    else:
        lines.append("alerts:")
        lines += [f"  - {a}" for a in report.alerts]
    return "\n".join(lines)


def render_error(err: WwError) -> str:
    head = f"error: {err.code}" + (f" ({err.detail})" if err.detail else "")
    return f"{head}\naction: {ACTIONS[err.code]}"
