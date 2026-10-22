"""Canadian alerts from ECCC (MSC GeoMet): one bbox query for all places, matched by polygon."""
from datetime import datetime

from ww_alerts_us import NON_WEATHER, _kind
from ww_geo import point_in_polygon
from ww_model import Alert, Place

URL = "https://api.weather.gc.ca/collections/weather-alerts/items?f=json&bbox={},{},{},{}&limit=500"
MARGIN = 0.5  # degrees added around the places so polygons that only just reach them are returned
LIMIT = 60
SEVERITY = {"red": "severe", "orange": "moderate", "yellow": "minor"}  # risk_colour_en


def _time(s) -> datetime | None:
    if not s:
        return None
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))  # Python 3.10 rejects a trailing Z
    if t.tzinfo is None:
        raise ValueError("naive time")
    return t


def _covers(geometry: dict, lat: float, lon: float) -> bool:
    polygons = {"Polygon": [geometry["coordinates"]], "MultiPolygon": geometry["coordinates"]}[geometry["type"]]
    # GeoJSON is [lon, lat]; only the outer ring matters for a warning area
    return any(point_in_polygon(lat, lon, [(y, x) for x, y in poly[0]]) for poly in polygons)


def _alert(f: dict) -> Alert:
    p = f["properties"]
    name = p["alert_name_en"]
    if any(w in name.lower() for w in NON_WEATHER):
        raise ValueError("not weather")
    title = name.title()
    area = p.get("feature_name_en") or ""
    text = p.get("alert_text_en") or ""
    summary = f"{title} for {area}" if area else title
    return Alert(_kind(name), SEVERITY.get((p.get("risk_colour_en") or "").lower(), "minor"), title,
                 summary[:LIMIT], text or summary,
                 _time(p.get("expiration_datetime") or p.get("event_end_datetime")),
                 _time(p.get("publication_datetime")), "eccc", f"eccc:{f['id']}")


def alerts_for(places: list[Place], http, now: datetime) -> list[list[Alert] | None]:
    lats, lons = [p.lat for p in places], [p.lon for p in places]
    data = http(URL.format(*(f"{v:g}" for v in (
        min(lons) - MARGIN, min(lats) - MARGIN, max(lons) + MARGIN, max(lats) + MARGIN))))
    out: list[list[Alert]] = [[] for _ in places]
    for f in data.get("features", []):
        try:
            alert = _alert(f)
            hits = [i for i, p in enumerate(places) if _covers(f["geometry"], p.lat, p.lon)]
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            continue  # one malformed feature must not make every place unavailable
        for i in hits:
            out[i].append(alert)
    return out
