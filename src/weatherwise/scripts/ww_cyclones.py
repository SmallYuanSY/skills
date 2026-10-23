"""Tropical cyclones near the places, from GDACS (global; one list request, geometry only for close events)."""
from datetime import datetime, timedelta, timezone

import ww_geo
from ww_cache import features, fetch_checked
from ww_model import Cyclone, Place

LIST_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=TC"
FETCH_KM = 3500  # only events this close to some place get their geometry fetched; a 5-day track outruns 2000 km
NEAR_KM = 800  # current position or forecast track within this distance triggers a note
MAX_AGE_HOURS = 24


def _latlon(coord) -> tuple[float, float]:
    return (coord[1], coord[0])  # GDACS is [lon, lat]


def _chain(segments: list[list[tuple[float, float]]], start: tuple[float, float]) -> list[tuple[float, float]]:
    """Join forecast segments into one path leaving `start`; GDACS lists them far end first."""
    path: list[tuple[float, float]] = []
    here = start
    left = [s for s in segments if len(s) == 2]
    while True:
        nxt = next((s for s in left if s[0] == here or s[1] == here), None)
        if nxt is None:
            break
        left.remove(nxt)
        here = nxt[1] if nxt[0] == here else nxt[0]
        path.append(here)
    for s in left:  # segments that do not connect still count as part of the forecast
        path.extend(p for p in s if p not in path)
    return path


def _parse_geometry(geo: dict, start: tuple[float, float]):
    centroid = start
    segments, polygons = [], []
    for f in geo.get("features", []):
        props, geom = f.get("properties", {}), f.get("geometry", {})
        cls, kind = props.get("Class", ""), geom.get("type")
        if cls == "Point_Centroid":
            centroid = _latlon(geom["coordinates"])
        elif kind == "LineString" and props.get("forecast") is True:
            segments.append([_latlon(c) for c in geom["coordinates"]])
        elif kind == "Polygon" and cls == "Poly_Green":
            polygons.append([_latlon(c) for c in geom["coordinates"][0]])
    return centroid, _chain(segments, centroid), polygons


def _events(body) -> list:
    """GDACS answers 204 No Content (body None) when there is no event at all; anything else must be a
    feature collection."""
    return [] if body is None else features(body)


def _recent(props: dict, now: datetime) -> bool:
    if props.get("iscurrent") != "true":
        return False
    try:
        end = datetime.fromisoformat(props["todate"]).replace(tzinfo=timezone.utc)  # GDACS times are UTC
    except (KeyError, ValueError):
        return False
    return now - end <= timedelta(hours=MAX_AGE_HOURS)


def _affects(c: Cyclone, place: Place) -> bool:
    if any(ww_geo.point_in_polygon(place.lat, place.lon, ring) for ring in c.wind_polygons):
        return True
    path = [(c.lat, c.lon)] + c.track
    return ww_geo.distance_to_path_km(place.lat, place.lon, path) <= NEAR_KM


def _cyclone(feature: dict, http) -> Cyclone:
    props = feature["properties"]
    start = _latlon(feature["geometry"]["coordinates"])
    sev = props.get("severitydata", {}).get("severitytext", "")
    try:
        geo = fetch_checked(http, props["url"]["geometry"], lambda b: (features(b), b)[1])
        centroid, track, polygons = _parse_geometry(geo, start)
    except Exception:  # keep a possibly close storm, judged by the list's position alone
        centroid, track, polygons = start, [], []
    return Cyclone(props["eventname"], props.get("alertlevel", ""), centroid[0], centroid[1],
                   track, polygons, sev)


def nearby(places: list[Place], http, now: datetime) -> list[tuple[Cyclone, list[int]]]:
    found = []
    for feature in fetch_checked(http, LIST_URL, _events):
        try:
            if not _recent(feature["properties"], now):
                continue
            lat, lon = _latlon(feature["geometry"]["coordinates"])
            if all(ww_geo.distance_km(p.lat, p.lon, lat, lon) > FETCH_KM for p in places):
                continue
            cyclone = _cyclone(feature, http)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):  # malformed entry
            continue
        indices = [i for i, p in enumerate(places) if _affects(cyclone, p)]
        if indices:
            found.append((cyclone, indices))
    return found


def _round10(km: float) -> int:
    return int(round(km / 10.0)) * 10


def _measure(c: Cyclone, place: Place) -> tuple[int, str, int]:
    now_km = ww_geo.distance_km(place.lat, place.lon, c.lat, c.lon)
    direction = ww_geo.bearing(place.lat, place.lon, c.lat, c.lon)
    closest = ww_geo.distance_to_path_km(place.lat, place.lon, [(c.lat, c.lon)] + c.track)
    return _round10(now_km), direction, _round10(closest)


NO_TRACK = "forecast track unavailable"


def _has_forecast(c: Cyclone) -> bool:
    return bool(c.track)  # closest is measured along the track; polygons only decide matching


def describe(c: Cyclone, place: Place) -> str:
    """No time: GDACS gives none for the forecast positions."""
    now_km, direction, closest = _measure(c, place)
    tail = f"forecast closest ~{closest} km" if _has_forecast(c) else NO_TRACK
    return f"{c.name} (GDACS {c.level}): now ~{now_km} km {direction}, {tail}"


def describe_many(c: Cyclone, places: list[tuple[int, Place]]) -> str:
    """One storm for several places: name and level once, distances tagged [n] per place."""
    m = [(i, _measure(c, p)) for i, p in places]
    now = ", ".join(f"~{n} km {d} of [{i + 1}]" for i, (n, d, _) in m)
    closest = ("forecast closest " + ", ".join(f"~{k} km [{i + 1}]" for i, (_, _, k) in m)
               if _has_forecast(c) else NO_TRACK)
    return f"{c.name} (GDACS {c.level}): now {now}; {closest}"
