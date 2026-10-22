"""Tropical cyclones near the places, from GDACS (global; one list request, geometry only for close events)."""
from datetime import datetime, timedelta, timezone

import ww_geo
from ww_model import Cyclone, Place

LIST_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=TC"
FETCH_KM = 2000  # only events this close to some place get their geometry fetched
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
        centroid, track, polygons = _parse_geometry(http(props["url"]["geometry"]), start)
    except Exception:  # keep a possibly close storm, judged by the list's position alone
        centroid, track, polygons = start, [], []
    return Cyclone(props["eventname"], props.get("alertlevel", ""), centroid[0], centroid[1],
                   track, polygons, sev)


def nearby(places: list[Place], http, now: datetime) -> list[tuple[Cyclone, list[int]]]:
    found = []
    for feature in http(LIST_URL).get("features", []):
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


def describe(c: Cyclone, place: Place) -> str:
    """No time: GDACS gives none for the forecast positions."""
    now_km = ww_geo.distance_km(place.lat, place.lon, c.lat, c.lon)
    direction = ww_geo.bearing(place.lat, place.lon, c.lat, c.lon)
    closest = ww_geo.distance_to_path_km(place.lat, place.lon, [(c.lat, c.lon)] + c.track)
    return (f"{c.name} (GDACS {c.level}): now ~{_round10(now_km)} km {direction}, "
            f"forecast closest ~{_round10(closest)} km")
