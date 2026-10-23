"""Distance, bearing and polygon helpers in pure Python (no third-party dependencies)."""
import math

EARTH_RADIUS_KM = 6371.0
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine great-circle distance."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)  # sin() of the raw difference handles the dateline
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Compass direction (8 points) of point 2 as seen from point 1."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    degrees = (math.degrees(math.atan2(x, y)) + 360) % 360
    return COMPASS[int((degrees + 22.5) // 45) % 8]


def _wrap_lon(dlon: float) -> float:
    return (dlon + 180) % 360 - 180


def distance_to_path_km(lat: float, lon: float, path: list[tuple[float, float]]) -> float:
    """Shortest distance to a (lat, lon) polyline. An equirectangular projection around the
    point is accurate enough for segments within a few hundred km."""
    if not path:
        raise ValueError("empty path")
    k = math.cos(math.radians(lat)) * math.radians(1) * EARTH_RADIUS_KM  # km per degree of lon
    d = math.radians(1) * EARTH_RADIUS_KM  # km per degree of lat
    pts = [(_wrap_lon(plon - lon) * k, (plat - lat) * d) for plat, plon in path]  # point is the origin
    best = math.hypot(*pts[0])
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / length2))
        best = min(best, math.hypot(x1 + t * dx, y1 + t * dy))
    return best


def point_in_polygon(lat: float, lon: float, ring: list[tuple[float, float]]) -> bool:
    """Ray casting; ring is a (lat, lon) sequence. Longitudes are unwrapped first (the first vertex near
    the point, each next one within 180° of the previous), so a ring crossing the antimeridian
    (179°E -> 179°W) stays one small shape instead of spanning the globe."""
    unwrapped: list[tuple[float, float]] = []
    prev = lon
    for plat, plon in ring:
        prev = prev + _wrap_lon(plon - prev)
        unwrapped.append((plat, prev))
    ring = unwrapped
    inside = False
    for (lat1, lon1), (lat2, lon2) in zip(ring, ring[1:] + ring[:1]):
        if (lat1 > lat) != (lat2 > lat):
            if lon < lon1 + (lat - lat1) / (lat2 - lat1) * (lon2 - lon1):
                inside = not inside
    return inside
