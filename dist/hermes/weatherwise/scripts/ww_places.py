"""Turns what the user said ("台中", "Tokyo", "24.15,120.67", nothing) into a Place."""
import re
import time
import urllib.parse
from dataclasses import replace

from ww_alerts_jp import PREFECTURES
from ww_errors import WwError
from ww_http import HttpError
from ww_model import Place

NOMINATIM_HOST = "https://nominatim.openstreetmap.org"
NOMINATIM = f"{NOMINATIM_HOST}/search"
NOMINATIM_REVERSE = f"{NOMINATIM_HOST}/reverse"
PAUSE = 1.1  # seconds between live Nominatim requests
SMALL_PLACES = {"village", "hamlet", "suburb", "neighbourhood", "quarter", "isolated_dwelling"}
CJK = re.compile(r"[\u3400-\u9fff]")
ADMIN_SUFFIXES = ("區", "鄉", "鎮", "市", "縣")
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
SAR = {"CN-HK": "hk", "CN-MO": "mo"}
JP_CODE = re.compile(r"JP-(\d\d)")
COORDS = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class Paced:
    """The one place Nominatim requests are paced (one per second): it waits right before a request that
    will really hit the network, and only when an earlier one in this run already did. A cached lookup
    (the wrapped fetcher's is_fresh) never waits."""

    def __init__(self, http):
        self.http = http
        self.live = False

    def __call__(self, url: str, headers: dict | None = None, *, text: bool = False):
        is_fresh = getattr(self.http, "is_fresh", None)
        if url.startswith(NOMINATIM_HOST) and not (is_fresh and is_fresh(url, text)):
            if self.live:
                time.sleep(PAUSE)
            self.live = True
        return self.http(url, headers, text=text)

    def evict(self, url: str, text: bool = False):
        evict = getattr(self.http, "evict", None)
        return evict(url, text) if evict else None


def paced(http) -> Paced:
    """Every entry point that may ask Nominatim wraps its fetcher once; an already paced one is kept."""
    return http if isinstance(http, Paced) else Paced(http)


def _get(http, url: str, service: str):
    try:
        return http(url)
    except HttpError as e:  # e.g. Nominatim rate-limiting with 429
        raise WwError("service_error", f"{service} HTTP {e.status}") from None


def resolve_place(query: str | None, cfg: dict, lang: str, global_search: bool, http) -> Place:
    http = paced(http)
    if not query:
        d = cfg.get("default")
        if not d:
            raise WwError("no_default_location")
        # A default without a country is completed by ensure_default_complete, not here (one reverse per run)
        return Place(d["name"], float(d["lat"]), float(d["lon"]), d.get("timezone"),
                     d.get("country_code"), d.get("region"), d.get("locality"), d.get("district") or None)
    m = COORDS.match(query)
    if m:
        lat, lon = float(m[1]), float(m[2])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise WwError("place_not_found", query.strip())
        return _with_address(Place(f"{lat},{lon}", lat, lon), lang, http)
    return geocode(query, lang, global_search, http)


def localize(place: Place, http) -> Place:
    """Alert feeds match region/locality/district by name, in the local language (MeteoAlarm "Berlin",
    JMA 千代田区), so places outside Taiwan get those three fields from a reverse lookup without
    accept-language. The name stays in the user's language. A failed lookup keeps what we have."""
    if not place.country_code or place.country_code == "tw":
        return place
    return local_names(place, http) or place


def local_names(place: Place, http) -> Place | None:
    """localize's lookup: the place with local region/locality/district, or None when it failed."""
    http = paced(http)
    try:
        local = reverse(place.lat, place.lon, None, http)
    except WwError:
        return None
    if local.country_code != place.country_code:
        return None
    return replace(place, region=local.region, locality=local.locality, district=local.district)


def _with_address(place: Place, lang: str, http) -> Place:
    """Country and region are a bonus for coordinates; without them only alerts are unavailable."""
    try:
        found = reverse(place.lat, place.lon, lang, http)
    except WwError:
        return place
    return localize(replace(place, country_code=found.country_code, region=found.region,
                            locality=found.locality, district=found.district), http)


def _is_district(r: dict, query: str) -> bool:
    name = r.get("name") or ""
    return r.get("class") == "boundary" and r.get("type") == "administrative" and name.startswith(query)


def _pick(results: list[dict], query: str, prefer_district: bool = True) -> dict:
    # A same-named village often ranks first ("坪林" in 苗栗 before 新北市坪林區), so prefer the district.
    # Only in the Taiwan search: worldwide, Nominatim's importance order is right ("Berlin" is not Berlin, NH)
    if not prefer_district:
        return results[0]
    return next((r for r in results if _is_district(r, query)), results[0])


def _search(params: dict, http) -> list[dict]:
    return _get(http, f"{NOMINATIM}?{urllib.parse.urlencode(params)}", "nominatim")


def _district_by_suffix(query: str, base: dict, first: dict, http) -> dict | None:
    """Nominatim may not list the district at all for a bare name; ask for 坪林區, 坪林鄉, ... instead.

    Only for Taiwan-style (CJK) names; a failed retry just means keeping the first result."""
    if first.get("type") not in SMALL_PLACES or query.endswith(ADMIN_SUFFIXES) or not CJK.search(query):
        return None
    for suffix in ("區", "鄉", "鎮"):
        try:
            results = _search({**base, "q": query + suffix}, http)
        except WwError:
            return None
        for r in results:
            if _is_district(r, query):
                return r
    return None


def geocode(query: str, lang: str, global_search: bool, http) -> Place:
    http = paced(http)
    base = {"q": query, "format": "json", "addressdetails": 1, "limit": 5, "accept-language": lang}
    # Taiwan first, then worldwide; --global goes straight to worldwide
    attempts = [base] if global_search else [{**base, "countrycodes": "tw"}, base]
    for params in attempts:
        res = _search(params, http)
        if res:
            taiwan = "countrycodes" in params
            r = _pick(res, query, taiwan)
            if taiwan and not _is_district(r, query):
                r = _district_by_suffix(query, params, res[0], http) or r
            parts = [p.strip() for p in r["display_name"].split(",")]
            name = ", ".join(p for p in parts if not p.isdigit())
            return localize(Place(name, float(r["lat"]), float(r["lon"]), **_address_fields(r)), http)
    raise WwError("place_not_found", query)


def reverse(lat: float, lon: float, lang: str | None, http) -> Place:
    """lang None asks without accept-language, which makes Nominatim answer in the place's own language."""
    http = paced(http)
    q = urllib.parse.urlencode({"format": "json", "addressdetails": 1, "zoom": 14, "lat": lat, "lon": lon,
                                **({"accept-language": lang} if lang else {})})
    r = _get(http, f"{NOMINATIM_REVERSE}?{q}", "nominatim")
    return Place(f"{lat},{lon}", lat, lon, **_address_fields(r if isinstance(r, dict) else {}))


def _address_fields(r: dict) -> dict:
    """country_code, region and locality from a Nominatim result.

    Observed 2026-10: Taiwan puts the 直轄市 in `city`, other towns' county in `county`, and the
    district/township in `suburb`/`town`. Japan puts a ward or city in `city` and only sometimes a
    prefecture in `state`/`province`, so there `city` is the municipality and the prefecture may have
    to come from display_name ("千代田区, 東京, 102-0000, 日本"). The US puts the state in `state`.
    """
    addr = r.get("address") or {}
    cc = addr.get("country_code")
    if cc == "cn":  # Nominatim files Hong Kong and Macau under China, with the SAR as ISO3166-2-lvl3
        cc = SAR.get(addr.get("ISO3166-2-lvl3"), cc)
    keys = ("city", "county", "state", "province") if cc == "tw" else ("state", "province", "county")
    region = _japan_by_code(addr) if cc == "jp" else None
    region = region or next((addr[k] for k in keys if addr.get(k)), None)
    if not region and cc == "jp":
        region = _japan_prefecture(r, addr)
    if not region and cc != "tw":
        region = addr.get("city")
    locality = next((addr[k] for k in ("suburb", "town", "city_district", "village", "municipality", "city")
                     if addr.get(k) and addr[k] != region), None)
    # County-level area (German Kreis) for matching county-based warning feeds; Taiwan's county is the region
    district = None if cc == "tw" else (addr.get("county") or addr.get("city"))
    return {"country_code": cc, "region": region, "locality": locality, "district": district}


def _japan_by_code(addr: dict) -> str | None:
    """JP-27 -> 大阪府. The code is language-independent: a town in a 郡 may have no prefecture in the
    address (the 郡 would become the region) or have it in simplified characters (鹿儿岛县)."""
    m = JP_CODE.fullmatch(addr.get("ISO3166-2-lvl4") or "")
    return PREFECTURES[int(m[1]) - 1] if m and 1 <= int(m[1]) <= len(PREFECTURES) else None


def _japan_prefecture(r: dict, addr: dict) -> str | None:
    parts = [p.strip() for p in (r.get("display_name") or "").split(",")]
    if addr.get("city") in parts:
        nxt = parts[parts.index(addr["city"]) + 1:]
        return next((p for p in nxt if p != addr.get("country") and not p[:1].isdigit()), None)
    return None


def with_timezone(place: Place, http) -> Place:
    if place.timezone:
        return place
    q = urllib.parse.urlencode(
        {"latitude": place.lat, "longitude": place.lon, "timezone": "auto", "forecast_days": 1}
    )
    return replace(place, timezone=_get(http, f"{OPEN_METEO}?{q}", "open-meteo").get("timezone") or "UTC")
