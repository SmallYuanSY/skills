"""Hong Kong alerts from the HKO open-data warning summary; one request serves every Hong Kong place."""
import re
from datetime import datetime, timedelta, timezone

from ww_cache import fetch_checked
from ww_model import Alert, Place

URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum&lang=tc"
LIMIT = 60
HKT = timezone(timedelta(hours=8))
WARNING_KEY = re.compile(r"W[A-Z0-9]+")  # every warning-summary key: WRAIN, WTCSGNL, WFIRE, ...

# warning-summary key -> kind; anything else is still listed as "other"
KINDS = {
    "WRAIN": "rain", "WTCSGNL": "typhoon", "WTCPRE8": "typhoon", "WTS": "thunder", "WMSGNL": "wind",
    "WHOT": "heat", "WCOLD": "cold", "WFROST": "cold", "WFNTSA": "flood",
}
# weather only (spec section 3): landslip and tsunami warnings are not listed
SKIP = {"WL", "WTMW"}
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
        if not isinstance(w, dict) or key in SKIP or w.get("actionCode") == "CANCEL" or w.get("code") == "CANCEL":
            continue
        code = w.get("code") or key
        # per the API doc, WTCSGNL's name is generic and "type" holds the specific signal
        title = (w.get("type") if key == "WTCSGNL" else None) or w.get("name") or f"天氣警告 ({code})"
        out.append(Alert(KINDS.get(key, "other"), "severe" if code in SEVERE_CODES else "moderate",
                         title, title[:LIMIT], " ".join(x for x in (w.get("name"), w.get("type")) if x) or title,
                         _time(w.get("expireTime")), _time(w.get("updateTime")), "hko", f"hko:{code}"))
    return out


def _summary(body) -> dict:
    """{} is the real "no warnings"; anything else must look like warning entries ("WRAIN": {...}),
    so an error object served with HTTP 200 is rejected rather than read as none."""
    if not isinstance(body, dict) or not all(
            isinstance(k, str) and WARNING_KEY.fullmatch(k) and isinstance(v, dict) for k, v in body.items()):
        raise ValueError("not a warning summary")
    return body


def alerts_for(places: list[Place], http, now: datetime) -> list[list[Alert] | None]:
    if not places:
        return []
    data = fetch_checked(http, URL, _summary)
    return [_alerts(data) for _ in places]
