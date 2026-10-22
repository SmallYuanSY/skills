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


# JIS prefecture code = the first two digits of a class20 code. Matching by code, not by the office
# name, because Hokkaido and Okinawa offices are named after subregions (石狩・空知・後志地方).
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県",
    "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]
JIS = {**{n: f"{i:02d}" for i, n in enumerate(PREFECTURES, 1)},
       **{n[:-1]: f"{i:02d}" for i, n in enumerate(PREFECTURES, 1)}}  # "東京" as well as "東京都"


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


def _match(area: dict, place: Place) -> tuple[list[str], str] | None:
    """(class20 codes, office code) for the place's municipality, or None when absent or ambiguous.

    Only the place's own prefecture is searched: 北区 is in Tokyo, Osaka (as 大阪市) and Kobe. A ward of a
    designated city may be listed as the city (大阪市), as city+ward (神戸市北区) or as parts of the city
    (横浜市北部/南部, all returned since we cannot tell which part a ward is in)."""
    pref = JIS.get((place.region or "").strip())
    if not pref or not place.locality:
        return None
    names = {code: v["name"] for code, v in area["class20s"].items() if code[:2] == pref}
    loc = place.locality
    city = place.district if place.district and place.district != loc else None
    whole = [c for c in (city, loc if loc.endswith("市") else None) if c]  # names a part of a city starts with
    tries = [lambda n: n == loc]
    if city:
        tries += [lambda n: n == city + loc, lambda n: n == city]
    tries += [lambda n: _strip(n) == _strip(loc)]
    for same in tries:
        found = [code for code, n in names.items() if same(n)]
        if len(found) == 1:
            office = _office_of(area, found[0])
            return ([found[0]], office) if office else None
    for w in whole:
        found = [code for code, n in names.items() if n.startswith(w)]
        offices = {_office_of(area, code) for code in found}
        if found and len(offices) == 1 and None not in offices:
            return found, offices.pop()
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
    out, seen = [], set()
    for w in entries:
        if w.get("status") in INACTIVE or not w.get("code") or w["code"] in seen:
            continue
        seen.add(w["code"])  # a city in several parts lists the same warning per part
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
        codes, office = m
        # the file lists only areas that have entries, so a missing class20 means no warnings
        entries = [w for t in reports[office]["areaTypes"] for a in t["areas"] if a["code"] in codes
                   for w in a["warnings"]]
        out.append(_alerts(codes[0], entries, reports[office]))
    return out
