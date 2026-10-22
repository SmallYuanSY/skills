"""Alert pipeline: dispatch places to country providers, drop expired and duplicate alerts, merge cyclones."""
import re
from collections import defaultdict
from datetime import datetime
from typing import Callable

import ww_alerts_tw
import ww_cyclones
from ww_errors import WwError
from ww_http import HttpError
from ww_model import SEVERITY_ORDER, Alert, Cyclone, Place, PlaceAlerts

CAP = 6  # alerts listed per place

# country code -> alerts_for(places, http, now) -> list[list[Alert] | None]
PROVIDERS: dict[str, Callable] = {"tw": ww_alerts_tw.alerts_for}


def _reason(cc: str, e: Exception) -> str:
    if isinstance(e, HttpError):
        return f"{cc} HTTP {e.status}"
    if isinstance(e, WwError):
        return e.code
    return type(e).__name__


def _clean(alerts: list[Alert], now: datetime) -> list[Alert]:
    newest: dict[str, Alert] = {}
    for a in alerts:
        if a.expires is not None and a.expires < now:
            continue
        old = newest.get(a.key)
        if old is None or _stamp(a) > _stamp(old):
            newest[a.key] = a
    rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    return sorted(newest.values(), key=lambda a: rank.get(a.severity, len(rank)))


def _stamp(a: Alert):
    return (a.updated is not None, a.updated.timestamp() if a.updated else 0.0)


def _local_name(c: Cyclone) -> str:
    return re.sub(r"-\d+$", "", c.name)


def collect(places: list[Place], http, now: datetime):
    """Return (one PlaceAlerts per place, cyclones not named by a local alert with their place indices)."""
    results: list[PlaceAlerts | None] = [None] * len(places)
    groups: dict[str | None, list[int]] = defaultdict(list)
    for i, p in enumerate(places):
        groups[p.country_code].append(i)

    for cc, idx in groups.items():
        provider = PROVIDERS.get(cc) if cc else None
        if provider is None:  # unknown country is "no data", never "no alerts"
            for i in idx:
                results[i] = PlaceAlerts("unsupported", [])
            continue
        try:
            per_place = provider([places[i] for i in idx], http, now)
            if len(per_place) != len(idx):
                raise ValueError("provider returned the wrong number of results")
            cleaned = [None if a is None else _clean(a, now) for a in per_place]
        except Exception as e:
            for i in idx:
                results[i] = PlaceAlerts("unavailable", [], _reason(cc, e))
            continue
        for i, alerts in zip(idx, cleaned):
            results[i] = PlaceAlerts("unsupported", []) if alerts is None else PlaceAlerts("ok", alerts)

    try:
        found = ww_cyclones.nearby(places, http, now)
    except Exception:  # GDACS is extra information; its failure must not change any place's status
        found = []

    standalone = []
    for cyclone, indices in found:
        name = _local_name(cyclone).lower()
        left = []
        for i in indices:
            merged = False
            for a in results[i].alerts:
                if name and a.kind == "typhoon" and name in f"{a.title} {a.detail}".lower():
                    a.cyclone = cyclone
                    merged = True
            if not merged:
                left.append(i)
        if left:
            standalone.append((cyclone, left))
    return results, standalone
