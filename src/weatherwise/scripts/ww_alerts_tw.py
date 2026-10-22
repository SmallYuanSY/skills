"""Taiwan alerts from the NCDR Atom feed (CWA weather alerts only; one request per run, no CAP files)."""
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

from ww_cache import fetch_checked
from ww_errors import WwError
from ww_model import Alert, Place

FEED = "https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx"
TAIPEI = ZoneInfo("Asia/Taipei")
ATOM = "{http://www.w3.org/2005/Atom}"
CAP = "{urn:oasis:names:tc:emergency:cap:1.1}"
PUBLISHER = "中央氣象署"
KINDS = {"颱風": "typhoon", "降雨": "rain", "強風": "wind", "高溫": "heat", "低溫": "cold", "濃霧": "fog", "巨浪": "marine"}
RAIN_LEVELS = ["超大豪雨", "大豪雨", "豪雨", "大雨"]  # highest first
LIGHTS = ["紅色燈號", "橙色燈號", "黃色燈號"]
SEVERITY_WORDS = [
    ("extreme", ("紅色燈號", "超大豪雨")),
    ("severe", ("橙色燈號", "大豪雨", "豪雨")),
    ("moderate", ("黃色燈號", "大雨")),
]
LIMIT = 60


def parse_ncdr_time(s: str) -> datetime:
    """'2026/10/23 下午 08:00:00' (Taipei time, Chinese AM/PM) -> aware datetime."""
    m = re.fullmatch(r"\s*(\d+)/(\d+)/(\d+)\s+(上午|下午)\s*(\d+):(\d+):(\d+)\s*", s)
    if not m:
        raise ValueError(f"unrecognised NCDR time: {s!r}")
    y, mo, d, half, h, mi, sec = m.groups()
    hour = int(h) % 12 + (12 if half == "下午" else 0)
    return datetime(int(y), int(mo), int(d), hour, int(mi), int(sec), tzinfo=TAIPEI)


def _norm(s: str) -> str:
    return s.replace("台", "臺")  # same length, so indices carry over to the original text


def _severity(kind: str, text: str) -> str:
    if kind == "typhoon":
        return "severe"  # words elsewhere in the long text must not escalate it
    found = set()
    for level, words in SEVERITY_WORDS:
        if any(w in text for w in words):
            found.add(level)
    for level in ("extreme", "severe", "moderate"):
        if level in found:
            return level
    return "minor"


def _title(kind: str, title: str, text: str) -> str:
    if kind == "rain":
        return next((w for w in RAIN_LEVELS if w in text), title)
    if kind == "wind":
        light = next((w for w in LIGHTS if w in text), None)
        return f"強風 {light}" if light else title
    if kind == "typhoon":
        m = re.search(r"(輕度|中度|強烈)颱風 ([^\s（]+)（國際命名", text)
        return f"颱風警報 {m.group(1)}颱風 {m.group(2)}" if m else "颱風警報"
    return title


def _scope(text: str, region: str | None) -> str:
    """The clauses that name the place's county; the whole text when none does."""
    if region:
        norm = _norm(region)
        clauses = [c for c in re.split(r"[，。；;\n]", text) if norm in _norm(c)]
        if clauses:
            return "，".join(clauses)
    return text


def _segments(text: str) -> list[str]:
    return [s for s in re.split(r"[，。]", text) if s.strip()]


COUNTY = r"[\u4e00-\u9fff]{1,3}[縣市](?:\([^)]*\))?"
COUNTY_RUN = re.compile(rf"{COUNTY}(?:、{COUNTY})+(?:局部)?地區?")


def _strip_counties(seg: str) -> str:
    """The wind text lists every county before the hazard; the hazard is what matters."""
    return COUNTY_RUN.sub("", seg).strip(" 、")


def _summary(kind: str, text: str, region: str | None) -> str:
    if kind == "typhoon":
        # the feed prefixes the prose with machine-readable fields, so start at the named storm
        m = re.search(r"(?:輕度|中度|強烈)颱風 [^\s（]+（國際命名[^，。]*中心位置[^，。]*", text)
        if m:
            return m.group(0)[:LIMIT]
    elif region:
        norm = _norm(text)
        first = None
        for seg in _segments(norm):
            if region in seg:
                start = norm.index(seg)
                cleaned = _strip_counties(text[start:start + len(seg)])
                if len(cleaned) > 6:  # shorter is just what is left of a county list
                    return cleaned[:LIMIT]
                first = first or cleaned
        if first:
            return first[:LIMIT]
    return text.strip()[:LIMIT]


def _entries(root: ET.Element) -> list[dict]:
    """CWA weather entries, newest version of each title only, so a superseded
    version can't resurface for a place the newest one no longer lists."""
    newest: dict[str, dict] = {}
    for e in root.iter(ATOM + "entry"):
        title = (e.findtext(ATOM + "title") or "").strip()
        if (e.findtext(f"{ATOM}author/{ATOM}name") or "").strip() != PUBLISHER or title not in KINDS:
            continue
        if (e.findtext(CAP + "status") or "").strip() != "Actual":
            continue
        try:
            updated = datetime.fromisoformat((e.findtext(ATOM + "updated") or "").strip())
            raw = (e.findtext(CAP + "expires") or "").strip()
            expires = parse_ncdr_time(raw) if raw else None
        except ValueError:
            continue  # one malformed entry must not hide the rest
        if updated.tzinfo is None:
            continue
        item = {"title": title, "updated": updated, "expires": expires, "text": (e.findtext(ATOM + "summary") or "").strip()}
        if title not in newest or updated > newest[title]["updated"]:
            newest[title] = item
    return list(newest.values())


def _alert(item: dict, region: str | None) -> Alert:
    kind = KINDS[item["title"]]
    text = item["text"]
    scoped = _scope(text, region)
    return Alert(kind, _severity(kind, scoped), _title(kind, item["title"], text if kind == "typhoon" else scoped), _summary(kind, text, region), text,
                 item["expires"], item["updated"], "ncdr", "ncdr:" + item["title"])


def _root(body: str) -> ET.Element:
    root = ET.fromstring(body)
    if root.tag == "WarningMessage" or root.find(".//WarningMessage") is not None:
        raise WwError("service_error", "ncdr rate limited")
    return root


def alerts_for(places: list[Place], http, now: datetime) -> list[list[Alert] | None]:
    if not any(p.region for p in places):
        return [None] * len(places)
    entries = _entries(fetch_checked(http, FEED, _root, text=True))
    out: list[list[Alert] | None] = []
    for p in places:
        if not p.region:
            out.append(None)
            continue
        region = _norm(p.region)
        out.append([_alert(it, p.region) for it in entries
                    if it["title"] == "颱風" or region in _norm(it["text"])])
    return out
