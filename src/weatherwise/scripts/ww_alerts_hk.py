"""Hong Kong alerts from the HKO open-data warning summary; one request serves every Hong Kong place."""
from datetime import datetime, timedelta, timezone

from ww_model import Alert, Place

URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum&lang=tc"
LIMIT = 60
HKT = timezone(timedelta(hours=8))

# warning-summary key -> kind; anything else is still listed as "other"
KINDS = {
    "WRAIN": "rain", "WTCSGNL": "typhoon", "WTS": "thunder", "WMSGNL": "wind",
    "WHOT": "heat", "WCOLD": "cold", "WFROST": "cold", "WFNTSA": "flood", "WTMW": "marine",
}
# signal 8 and above, red and black rainstorm
SEVERE_CODES = {"TC8NE", "TC8SE", "TC8NW", "TC8SW", "TC9", "TC10", "WRAINR", "WRAINB"}


def _time(s) -> datetime | None:
    if not s:
        return None
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=HKT)


def _alerts(data: dict) -> list[Alert]:
    out = []
    for key, w in data.items():
        if not isinstance(w, dict) or w.get("actionCode") == "CANCEL":
            continue
        code = w.get("code") or key
        title = w.get("name") or f"天氣警告 ({code})"
        out.append(Alert(KINDS.get(key, "other"), "severe" if code in SEVERE_CODES else "moderate",
                         title, title[:LIMIT], w.get("type") or w.get("contents") or title,
                         _time(w.get("expireTime")), _time(w.get("updateTime")), "hko", f"hko:{code}"))
    return out


def alerts_for(places: list[Place], http, now: datetime) -> list[list[Alert] | None]:
    if not places:
        return []
    data = http(URL)
    return [_alerts(data) for _ in places]
