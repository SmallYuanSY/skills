"""US alerts from the National Weather Service: one point query per place."""
from datetime import datetime

from ww_model import Alert, Place

URL = "https://api.weather.gov/alerts/active?point={:.4f},{:.4f}"
LIMIT = 60
NON_WEATHER = ("tsunami", "earthquake", "volcano")  # safety net behind the category check

# first matching word in the event name decides the kind; anything else is "other"
KINDS = [
    ("hurricane force wind", "wind"), ("hurricane", "typhoon"), ("tropical storm", "typhoon"), ("thunderstorm", "thunder"),
    ("tornado", "thunder"), ("flood", "flood"), ("rain", "rain"), ("snow", "snow"), ("winter", "snow"),
    ("blizzard", "snow"), ("ice storm", "snow"), ("heat", "heat"), ("cold", "cold"), ("freeze", "cold"), ("frost", "cold"),
    ("wind chill", "cold"), ("fog", "fog"), ("wind", "wind"), ("gale", "marine"), ("surf", "marine"),
    ("small craft", "marine"), ("marine", "marine"), ("storm surge", "marine"),
]


def _kind(event: str) -> str:
    e = event.lower()
    return next((k for word, k in KINDS if word in e), "other")


def _time(s) -> datetime | None:
    if not s:
        return None
    t = datetime.fromisoformat(s)
    if t.tzinfo is None:
        raise ValueError("naive time")
    return t


def _is_weather(props: dict) -> bool:
    category = props.get("category")
    if category and category != "Met":  # civil, law-enforcement, hazmat, evacuation ... alerts
        return False
    return not any(w in (props.get("event") or "").lower() for w in NON_WEATHER)


def _alert(props: dict) -> Alert:
    event = props.get("event") or "Weather alert"
    severity = (props.get("severity") or "").lower()
    if severity not in ("extreme", "severe", "moderate", "minor"):
        severity = "minor"  # "Unknown"
    headline = props.get("headline") or event
    return Alert(_kind(event), severity, event, headline[:LIMIT], props.get("description") or headline,
                 _time(props.get("expires") or props.get("ends")),
                 _time(props.get("sent") or props.get("effective")), "nws", f"nws:{props['id']}")


def alerts_for(places: list[Place], http, now: datetime) -> list[list[Alert] | None]:
    return [_place_alerts(http(URL.format(p.lat, p.lon))) for p in places]


def _place_alerts(data: dict) -> list[Alert]:
    out = []
    for f in data.get("features", []):
        try:
            props = f["properties"]
            if _is_weather(props):
                out.append(_alert(props))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue  # one malformed feature must not make the whole place unavailable
    return out
