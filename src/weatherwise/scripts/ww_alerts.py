"""Alert pipeline: dispatch places to country providers, drop expired and duplicate alerts, merge cyclones."""
import re
from collections import defaultdict
from datetime import datetime
from typing import Callable, NamedTuple

import ww_alerts_ca
import ww_alerts_eu
import ww_alerts_hk
import ww_alerts_jp
import ww_alerts_tw
import ww_alerts_us
import ww_cyclones
from ww_errors import WwError
from ww_http import HttpError
from ww_model import SEVERITY_ORDER, Alert, Cyclone, Place, PlaceAlerts

CAP = 6  # alerts listed per place

# country code -> alerts_for(places, http, now) -> list[list[Alert] | None]
PROVIDERS: dict[str, Callable] = {
    "tw": ww_alerts_tw.alerts_for, "jp": ww_alerts_jp.alerts_for,
    "hk": ww_alerts_hk.alerts_for, "us": ww_alerts_us.alerts_for, "ca": ww_alerts_ca.alerts_for,
    **{cc: ww_alerts_eu.alerts_for for cc in ww_alerts_eu.COUNTRIES},
}


class Collected(NamedTuple):
    places: list[PlaceAlerts]  # one per place
    cyclones: list[tuple[Cyclone, list[int]]]  # not named by a local alert, with their place indices
    cyclone_error: str | None  # why the GDACS list could not be read; None when it was


def _reason(cc: str, e: Exception) -> str:
    if isinstance(e, HttpError):
        return f"{cc} HTTP {e.status}"
    if isinstance(e, WwError):
        return f"{e.code}: {e.detail[:80]}" if e.detail else e.code
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


def collect(places: list[Place], http, now: datetime) -> Collected:
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

    cyclone_error = None
    try:
        found = ww_cyclones.nearby(places, http, now)
    except Exception as e:  # GDACS failing must not change any place's status, but must not read as "no cyclone"
        found, cyclone_error = [], _reason("gdacs", e)

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
    return Collected(results, standalone, cyclone_error)
