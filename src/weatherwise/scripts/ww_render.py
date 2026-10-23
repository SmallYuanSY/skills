"""Turns reports, alerts and cyclones into plain key: value lines for the model to read."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import ww_cyclones
from ww_alerts import CAP
from ww_errors import ACTIONS, WwError
from ww_model import SEVERITY_ORDER, Alert, Cyclone, Place, PlaceAlerts, Report, one_variant

# Weekday names come from here, not strftime("%a"), which follows the machine's locale
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
STRONG_WIND_KMH = 40  # below this, wind is only mentioned while a wind alert is active
ASOF = "current only — not a forecast for later days"
NO_ALERTS = "do not tell the user there are none"
NO_CYCLONES = "do not tell the user there is no tropical cyclone"
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITY_ORDER)}

Entry = tuple  # (Place | None, Report | WwError, PlaceAlerts | None); place is None when it could not be resolved


def _or_unknown(value: float | None, fmt: str, suffix: str = "") -> str:
    return "unknown" if value is None else f"{value:{fmt}}{suffix}"


def _local(dt: datetime, place: Place) -> datetime:
    return dt.astimezone(ZoneInfo(place.timezone or "UTC"))


def _show_wind(report: Report, pa: PlaceAlerts | None) -> bool:
    if pa is not None and any(a.kind == "wind" for a in pa.alerts):
        return True
    w = report.current.wind_kmh if report.current else None
    return w is not None and w >= STRONG_WIND_KMH


def _now_text(report: Report, pa: PlaceAlerts | None) -> str:
    c = report.current
    text = f"{c.condition} {_or_unknown(c.temperature, '.0f', '°C')}"
    if _show_wind(report, pa):
        text += f", wind {_or_unknown(c.wind_kmh, '.0f', ' km/h')}"
    return text


def _day_text(d) -> str:
    weekday = WEEKDAYS[date.fromisoformat(d.date).weekday()]
    return (f"{d.date} {weekday}: {d.condition}, {_or_unknown(d.temp_min, '.0f')}–"
            f"{_or_unknown(d.temp_max, '.0f')}°C, rain {_or_unknown(d.precip_chance, '.0f', '%')}")


def _error_lines(err: WwError, prefix: str = "") -> list[str]:
    head = f"error: {err.code}" + (f" ({err.detail})" if err.detail else "")
    return [f"{prefix}{head}", f"    action: {ACTIONS[err.code]}"]


def _until(a: Alert, place: Place) -> str:
    # A typhoon's expiry is its next bulletin, not the end of the warning
    return f"until {_local(a.expires, place):%m-%d %H:%M}" if a.expires and a.kind != "typhoon" else ""


def _label(place: Place, country: bool = False) -> str:
    """Short place name: locality, region (and the country on the location line), else the full name."""
    parts = []
    for p in (place.locality, place.region):
        if p and one_variant(p) not in parts:
            parts.append(one_variant(p))
    name = one_variant(place.name)
    if not parts:
        return name
    tail = name.rsplit(", ", 1)[-1] if ", " in name else None
    if country and tail and tail not in parts:
        parts.append(tail)
    return ", ".join(parts)


def _shown_keys(entries: list, detail: bool) -> set[str]:
    """Alert keys that get a line: those within the per-place cap of at least one place."""
    return {a.key for e in entries if e[0] is not None and e[2] is not None
            for a in (e[2].alerts if detail else e[2].alerts[:CAP])}


def _alert_lines(entries: list, multi: bool, detail: bool) -> list[str]:
    """One line per alert key; places sharing a key are tagged [i], and per-place variants
    of the same key (rain levels differ between townships) share the line. The per-place cap
    is applied after grouping, so a key shown for one place keeps the tags of the others."""
    rank = lambda a: SEVERITY_RANK.get(a.severity, 9)  # noqa: E731
    live = [(i, e[2]) for i, e in enumerate(entries) if e[0] is not None and e[2] is not None]
    shown_keys = _shown_keys(entries, detail)
    groups: dict[str, list[tuple[int, Alert]]] = {}
    for i, pa in live:
        for a in pa.alerts:
            if a.key in shown_keys:
                groups.setdefault(a.key, []).append((i, a))

    lines = []
    for group in sorted(groups.values(), key=lambda g: min(rank(a) for _, a in g)):
        best_i, best = min(group, key=lambda x: rank(x[1]))
        titles: dict[str, list[int]] = {}
        for i, a in sorted(group, key=lambda x: rank(x[1])):
            titles.setdefault(a.title, []).append(i)
        if multi:
            title = " / ".join(t + " " + "".join(f"[{i + 1}]" for i in sorted(ix)) for t, ix in titles.items())
        else:
            title = best.title
        summary = best.summary if len({a.summary for _, a in group}) == 1 else ""
        dated = [(i, a) for i, a in group if a.expires]
        latest_i, latest = max(dated, key=lambda x: x[1].expires) if dated else (best_i, best)
        until = _until(latest, entries[latest_i][0]) if dated else ""
        rest = ", ".join(x for x in (summary, until) if x)
        line = f"  - [{best.severity}] {title}" + (f": {rest}" if rest else "")
        lines.append(line)
        if detail and best.detail:
            lines += [f"      {part}" for part in best.detail.splitlines()]
    for i, pa in live:
        n = sum(1 for a in pa.alerts if a.key not in shown_keys)
        if n:
            lines.append(f"  - {f'[{i + 1}] ' if multi else ''}+{n} more (run again with --detail)")
    return lines


def _status_lines(entries: list, fetched_at: datetime, multi: bool) -> list[str]:
    out = []
    for i, (place, report, pa) in enumerate(entries):
        if place is None or pa is None:
            continue
        tag = f"[{i + 1}] " if multi else ""
        if pa.status == "unsupported":
            out.append(f"{tag}alerts: unsupported (no official alert source here; {NO_ALERTS})")
        elif pa.status == "unavailable":
            out.append(f"{tag}alerts: unavailable ({pa.reason}; {NO_ALERTS})")
        elif not pa.alerts:
            out.append(f"{tag}alerts: none (as of {_local(fetched_at, place):%H:%M})")
    return out


def render(entries: list[Entry], cyclones: list[tuple[Cyclone, list[int]]], now: datetime,
           fetched_at: datetime, days: int, notice: str | None, detail: bool,
           cyclone_error: str | None = None) -> str:
    """Cyclone indices count entries from 0, the same as `entries`."""
    multi = len(entries) > 1
    lines = [f"notice: {notice}"] if notice else []
    first = next((e[0] for e in entries if e[0] is not None), None)
    home_tz = first.timezone if first else None
    here = _local(now, first) if first else now
    lines.append(f"local_time: {here:%Y-%m-%dT%H:%M} {WEEKDAYS[here.weekday()]}")

    if not multi:
        place, report, pa = entries[0]
        lines.append(f"location: {_label(place, True)} ({place.lat:.3f}, {place.lon:.3f})")
        if report.current:
            lines.append(f"now: {_now_text(report, pa)}")
        if report.next_hour is not None:
            lines.append(f"next_hour: {report.next_hour}")
        if report.days:
            lines.append("daily:")
            lines += [f"  {_day_text(d)}" for d in report.days[:days]]
    else:
        for i, (place, report, pa) in enumerate(entries):
            tag = f"[{i + 1}] "
            if place is None or isinstance(report, WwError):
                lines += _error_lines(report, tag)
                continue
            name = _label(place)
            if place.timezone != home_tz:
                t = _local(now, place)
                name += f" (local_time: {t:%Y-%m-%dT%H:%M} {WEEKDAYS[t.weekday()]})"
            parts = []
            if days > 1:
                head = f"{tag}{name}:" + (f" now {_now_text(report, pa)}" if report.current else "")
                if report.next_hour is not None:
                    head += f"; next hour: {report.next_hour}"
                lines.append(head)
                lines += [f"    {_day_text(d)}" for d in report.days[:days]]
                continue
            if report.current:
                parts.append(_now_text(report, pa))
            if report.days:
                d = report.days[0]
                parts.append(f"today {_or_unknown(d.temp_min, '.0f')}–{_or_unknown(d.temp_max, '.0f')}°C, "
                             f"rain {_or_unknown(d.precip_chance, '.0f', '%')}")
            line = f"{tag}{name}: " + "; ".join(parts)
            if report.next_hour is not None:
                line += f"; next hour: {report.next_hour}"
            lines.append(line)

    ok = [e for e in entries if e[0] is not None and e[2] is not None]
    alert_lines = _alert_lines(entries, multi, detail)
    if alert_lines:
        asof = f"{_local(fetched_at, first):%H:%M}" if first else ""
        lines.append(f"alerts (as of {asof}, {ASOF}):")
        lines += alert_lines
    if ok:
        lines += _status_lines(entries, fetched_at, multi)

    # Official OR GDACS, never both: a storm already carried by a place's official alert is not repeated.
    # (only alerts actually listed count: one cut by the cap must not hide the storm)
    shown = _shown_keys(entries, detail)
    covered = {(a.cyclone.name, i) for i, (_, _, pa) in enumerate(entries) if pa
               for a in pa.alerts if a.cyclone is not None and a.key in shown}
    standalone = [(c, left) for c, indices in cyclones
                  if (left := [i for i in indices if (c.name, i) not in covered])]
    if standalone:
        lines.append("cyclones (track data, not a local official warning):")
        for c, indices in standalone:
            lines.append("  - " + (ww_cyclones.describe_many(c, [(i, entries[i][0]) for i in indices]) if multi
                                   else ww_cyclones.describe(c, entries[indices[0]][0])))
    if cyclone_error:
        lines.append(f"cyclones: unavailable ({cyclone_error}; {NO_CYCLONES})")
    return "\n".join(lines)


def _alert_json(a: Alert) -> dict:
    iso = lambda dt: dt.isoformat() if dt else None  # noqa: E731
    out = {"kind": a.kind, "severity": a.severity, "title": a.title, "summary": a.summary, "detail": a.detail,
           "expires": iso(a.expires), "updated": iso(a.updated), "source": a.source, "key": a.key}
    if a.cyclone is not None:
        out["cyclone"] = _cyclone_json(a.cyclone)
    return out


def _cyclone_json(c: Cyclone) -> dict:
    return {"name": c.name, "level": c.level, "lat": c.lat, "lon": c.lon, "severity_text": c.severity_text,
            "track": [list(p) for p in c.track]}


def render_json(entries: list[Entry], cyclones: list[tuple[Cyclone, list[int]]], notice: str | None,
                queries: list[str | None] | None = None, cyclone_error: str | None = None,
                fetched_at: datetime | None = None) -> dict:
    """fetched_at is the alerts' as-of time, given in the first place's timezone like the text header."""
    places = []
    for n, (place, report, pa) in enumerate(entries):
        if isinstance(report, WwError):
            item = {"location": one_variant(place.name) if place else None,
                    "error": {"code": report.code, "detail": report.detail, "action": ACTIONS[report.code]}}
        else:
            item = {"location": one_variant(place.name), "source": report.source, "forecast": report.raw}
        item = {"query": queries[n] if queries else None, **item}
        if pa is not None:
            item["alerts"] = {"status": pa.status, "reason": pa.reason, "items": [_alert_json(a) for a in pa.alerts]}
        places.append(item)
    out: dict = {}
    if fetched_at is not None:
        first = next((e[0] for e in entries if e[0] is not None), None)
        out["alerts_as_of"] = (_local(fetched_at, first) if first else fetched_at).isoformat(timespec="seconds")
    out["places"] = places
    out["cyclones"] = [{**_cyclone_json(c), "places": [i + 1 for i in idx]} for c, idx in cyclones]
    if cyclone_error:
        out["cyclones_unavailable"] = cyclone_error
    if notice:
        out["notice"] = notice
    return out


def render_error(err: WwError) -> str:
    head = f"error: {err.code}" + (f" ({err.detail})" if err.detail else "")
    return f"{head}\naction: {ACTIONS[err.code]}"
