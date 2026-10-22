"""European alerts from MeteoAlarm: one feed request per country, matched by polygon or area name."""
from datetime import datetime

from ww_alerts_us import NON_WEATHER, _kind, _time
from ww_cache import fetch_checked
from ww_geo import point_in_polygon
from ww_model import Alert, Place

URL = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-{}"
LIMIT = 60

# ISO 3166 alpha-2 -> feed slug, as listed on https://feeds.meteoalarm.org
COUNTRIES: dict[str, str] = {
    "ad": "andorra", "at": "austria", "be": "belgium", "ba": "bosnia-herzegovina", "bg": "bulgaria",
    "hr": "croatia", "cy": "cyprus", "cz": "czechia", "dk": "denmark", "ee": "estonia", "fi": "finland",
    "fr": "france", "de": "germany", "gr": "greece", "hu": "hungary", "is": "iceland", "ie": "ireland",
    "il": "israel", "it": "italy", "lv": "latvia", "lt": "lithuania", "lu": "luxembourg", "mt": "malta",
    "md": "moldova", "me": "montenegro", "nl": "netherlands", "no": "norway", "pl": "poland",
    "pt": "portugal", "mk": "republic-of-north-macedonia", "ro": "romania", "rs": "serbia",
    "sk": "slovakia", "si": "slovenia", "es": "spain", "se": "sweden", "ch": "switzerland",
    "ua": "ukraine", "gb": "united-kingdom",
}

# awareness_type parameter ("4; Fog") -> kind; independent of the warning's language
AWARENESS = {1: "wind", 2: "snow", 3: "thunder", 4: "fog", 5: "heat", 6: "cold", 7: "marine",
             9: "snow", 10: "rain", 11: "flood", 12: "flood"}


def _info(alert: dict) -> dict:
    infos = alert["info"]
    return next((i for i in infos if (i.get("language") or "").lower().startswith("en")), infos[0])


def _is_weather(info: dict) -> bool:
    cat = info.get("category") or []
    cats = [cat] if isinstance(cat, str) else cat
    return "Met" in cats and not any(w in (info.get("event") or "").lower() for w in NON_WEATHER)


def _kind_of(info: dict) -> str:
    for p in info.get("parameter") or []:
        if p.get("valueName") == "awareness_type":
            try:
                kind = AWARENESS.get(int(p["value"].split(";")[0]))
            except (ValueError, KeyError, AttributeError):
                kind = None
            if kind:
                return kind
    return _kind(info.get("event") or "")


def _ring(text) -> list[tuple[float, float]]:
    """CAP polygon: space-separated 'lat,lon' pairs."""
    ring = [tuple(float(v) for v in pair.split(",")) for pair in text.split()]
    if len(ring) < 3 or any(len(pt) != 2 for pt in ring):
        raise ValueError("bad polygon")
    return ring


# Admin words that differ between Nominatim and a warning feed for the same area ("Landkreis X" vs "Kreis X").
# Longest first; keep the list small.
PREFIXES = ("kreis und stadt ", "kreisfreie stadt ", "landkreis ", "kreis ", "stadt ", "region ", "county ",
            "province of ", "département de ", "département ", "departement ")
SUFFIXES = (" county", " province")


def _norm(name: str) -> str:
    n = " ".join(name.casefold().split())
    for pre in PREFIXES:
        if n.startswith(pre):
            n = n[len(pre):]
            break
    for suf in SUFFIXES:
        if n.endswith(suf):
            n = n[:-len(suf)]
            break
    return n


def _covers(areas: list[dict], place: Place, names: set[str]) -> bool | None:
    """True/False when the areas can decide for this place, None when they cannot (no usable polygon or name).

    An area with a usable polygon is decided by the polygon alone; one without (or whose polygons all fail
    to parse) falls back to its name. In a feed mixing both, a polygon "no" yields False while a name
    match elsewhere still wins with True."""
    decided = None
    for a in areas:
        polygons = a.get("polygon")
        if isinstance(polygons, str):
            polygons = [polygons]
        usable = False
        for text in polygons or []:
            try:
                ring = _ring(text)
            except (ValueError, AttributeError):
                continue
            usable = True
            if point_in_polygon(place.lat, place.lon, ring):
                return True
            decided = False
        if not usable and _norm(a.get("areaDesc") or "") in names:
            return True
    return decided


def _alert(w: dict) -> tuple[Alert, list[dict]]:
    a = w["alert"]
    if a.get("msgType") == "Cancel" or a.get("status", "Actual") != "Actual":
        raise ValueError("not an active alert")
    info = _info(a)
    if not _is_weather(info):
        raise ValueError("not weather")
    severity = (info.get("severity") or "").lower()
    if severity not in ("extreme", "severe", "moderate", "minor"):
        severity = "minor"  # "Unknown"
    event = info["event"]
    headline = info.get("headline") or event
    return (Alert(_kind_of(info), severity, event, headline[:LIMIT], info.get("description") or headline,
                  _time(info.get("expires")), _time(a.get("sent")), "meteoalarm", f"meteoalarm:{a['identifier']}"),
            info["area"])


def _warnings(body) -> list:
    if not isinstance(body, dict) or not isinstance(body.get("warnings", []), list):
        raise ValueError("not a warning feed")
    return body.get("warnings", [])


def alerts_for(places: list[Place], http, now: datetime) -> list[list[Alert] | None]:
    feed = fetch_checked(http, URL.format(COUNTRIES[places[0].country_code]), _warnings)  # one country at a time
    warnings = []
    for w in feed:
        try:
            warnings.append(_alert(w))
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            continue  # one malformed warning must not make the whole country unavailable
    out: list[list[Alert] | None] = []
    for p in places:
        names = {_norm(n) for n in (p.region, p.locality, p.district) if n}
        hits, decided = [], False
        for alert, areas in warnings:
            try:
                covered = _covers(areas, p, names)
            except (TypeError, AttributeError):
                continue
            decided = decided or covered is not None
            if covered:
                hits.append(alert)
        # Name-only feeds can say "covered" but never "not covered": no match means the place is unknown to us.
        out.append(hits if hits or decided else None)
    return out
