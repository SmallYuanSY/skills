"""US alerts from the National Weather Service: one point query per place."""
from datetime import datetime

from ww_model import Alert, Place

URL = "https://api.weather.gov/alerts/active?point={:.4f},{:.4f}"
LIMIT = 60

# first matching word in the event name decides the kind; anything else is "other"
KINDS = [
    ("hurricane", "typhoon"), ("tropical storm", "typhoon"), ("thunderstorm", "thunder"),
    ("tornado", "thunder"), ("flood", "flood"), ("rain", "rain"), ("snow", "snow"), ("winter", "snow"),
    ("blizzard", "snow"), ("ice storm", "snow"), ("heat", "heat"), ("freeze", "cold"), ("frost", "cold"),
    ("wind chill", "cold"), ("fog", "fog"), ("wind", "wind"), ("gale", "marine"), ("surf", "marine"),
    ("small craft", "marine"), ("marine", "marine"), ("storm surge", "marine"),
]


def _kind(event: str) -> str:
    e = event.lower()
    return next((k for word, k in KINDS if word in e), "other")


def _time(s) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


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
    return [[_alert(f["properties"]) for f in http(URL.format(p.lat, p.lon)).get("features", [])]
            for p in places]
