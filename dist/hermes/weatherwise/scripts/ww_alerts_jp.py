"""Japan alerts from JMA bosai: municipality -> class20 code -> forecast office -> that office's warning file."""
from datetime import datetime

from ww_model import Alert, Place

AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"
WARNING_URL = "https://www.jma.go.jp/bosai/warning/data/warning/{}.json"
LIMIT = 60
SUFFIXES = "市区町村"
INACTIVE = {"解除", "発表警報・注意報はなし"}

# JMA warning code -> (name, kind, severity). Special warning = extreme, warning = severe, advisory = moderate.
CODES = {
    "32": ("暴風雪特別警報", "wind", "extreme"),
    "33": ("大雨特別警報", "rain", "extreme"),
    "35": ("暴風特別警報", "wind", "extreme"),
    "36": ("大雪特別警報", "snow", "extreme"),
    "37": ("波浪特別警報", "marine", "extreme"),
    "38": ("高潮特別警報", "storm_surge", "extreme"),
    "02": ("暴風雪警報", "wind", "severe"),
    "03": ("大雨警報", "rain", "severe"),
    "04": ("洪水警報", "flood", "severe"),
    "05": ("暴風警報", "wind", "severe"),
    "06": ("大雪警報", "snow", "severe"),
    "07": ("波浪警報", "marine", "severe"),
    "08": ("高潮警報", "storm_surge", "severe"),
    "10": ("大雨注意報", "rain", "moderate"),
    "12": ("大雪注意報", "snow", "moderate"),
    "13": ("風雪注意報", "wind", "moderate"),
    "14": ("雷注意報", "thunder", "moderate"),
    "15": ("強風注意報", "wind", "moderate"),
    "16": ("波浪注意報", "marine", "moderate"),
    "18": ("洪水注意報", "flood", "moderate"),
    "17": ("融雪注意報", "snowmelt", "moderate"),
    "19": ("高潮注意報", "storm_surge", "moderate"),
    "20": ("濃霧注意報", "fog", "moderate"),
    "21": ("乾燥注意報", "dry", "moderate"),
    "22": ("なだれ注意報", "avalanche", "moderate"),
    "23": ("低温注意報", "cold", "moderate"),
    "24": ("霜注意報", "frost", "moderate"),
    "25": ("着氷注意報", "icing", "moderate"),
    "26": ("着雪注意報", "snow_accretion", "moderate"),
    "27": ("その他の注意報", "other", "moderate"),
}


def _strip(name: str) -> str:
    return name[:-1] if name and name[-1] in SUFFIXES and len(name) > 1 else name


def _office_of(area: dict, code: str) -> str | None:
    """Follow parent links (class20 -> class15 -> class10 -> office) up to an office code."""
    cur = code
    for table in ("class20s", "class15s", "class10s"):
        cur = area[table][cur]["parent"]
        if cur in area["offices"]:
            return cur
    return None


def _match(area: dict, place: Place) -> tuple[str, str] | None:
    """(class20 code, office code) for the place's municipality, or None when absent or ambiguous."""
    if not place.locality:
        return None
    names = area["class20s"]
    for same in (lambda n: n == place.locality, lambda n: _strip(n) == _strip(place.locality)):
        found = []
        for code, v in names.items():
            if same(v["name"]):
                office = _office_of(area, code)
                if office:
                    found.append((code, office))
        if len(found) > 1 and place.region:  # e.g. 中央区 exists in several prefectures
            found = [f for f in found if place.region in area["offices"][f[1]]["name"]]
        if len(found) == 1:
            return found[0]
    return None


def _lookup(code: str) -> tuple[str, str, str]:
    """Known codes by table; an unknown future code is still listed rather than dropped."""
    if code in CODES:
        return CODES[code]
    n = int(code) if code.isdigit() else 10
    return (f"気象注意報 (code {code})", "other", "extreme" if n >= 30 else "severe" if n < 10 else "moderate")


def _alerts(code: str, entries: list[dict], report: dict) -> list[Alert]:
    updated = datetime.fromisoformat(report["reportDatetime"])
    headline = report.get("headlineText") or ""
    out = []
    for w in entries:
        if w.get("status") in INACTIVE or not w.get("code"):
            continue
        title, kind, severity = _lookup(w["code"])
        out.append(Alert(kind, severity, title, headline[:LIMIT], headline, None, updated, "jma",
                         f"jma:{code}:{w['code']}"))
    return out


def alerts_for(places: list[Place], http, now: datetime) -> list[list[Alert] | None]:
    area = http(AREA_URL)
    matches = [_match(area, p) for p in places]
    reports: dict[str, dict] = {}
    for m in matches:
        if m and m[1] not in reports:
            reports[m[1]] = http(WARNING_URL.format(m[1]))
    out: list[list[Alert] | None] = []
    for m in matches:
        if m is None:
            out.append(None)
            continue
        code, office = m
        # the file lists only areas that have entries, so a missing class20 means no warnings
        entries = next((a["warnings"] for t in reports[office]["areaTypes"] for a in t["areas"]
                        if a["code"] == code), [])
        out.append(_alerts(code, entries, reports[office]))
    return out
