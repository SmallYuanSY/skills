"""Turns what the user said ("台中", "Tokyo", "24.15,120.67", nothing) into a Place."""
import re
import time
import urllib.parse
from dataclasses import replace

from ww_errors import WwError
from ww_http import HttpError
from ww_model import Place

NOMINATIM = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
PAUSE = 1.1  # seconds between Nominatim requests of one lookup
SMALL_PLACES = {"village", "hamlet", "suburb", "neighbourhood", "quarter", "isolated_dwelling"}
CJK = re.compile(r"[\u3400-\u9fff]")
ADMIN_SUFFIXES = ("區", "鄉", "鎮", "市", "縣")
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
COORDS = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def _get(http, url: str, service: str):
    try:
        return http(url)
    except HttpError as e:  # e.g. Nominatim rate-limiting with 429
        raise WwError("service_error", f"{service} HTTP {e.status}") from None


def resolve_place(query: str | None, cfg: dict, lang: str, global_search: bool, http) -> Place:
    if not query:
        d = cfg.get("default")
        if not d:
            raise WwError("no_default_location")
        # A default without a country is completed by ensure_default_complete, not here (one reverse per run)
        return Place(d["name"], float(d["lat"]), float(d["lon"]), d.get("timezone"),
                     d.get("country_code"), d.get("region"), d.get("locality"), d.get("district"))
    m = COORDS.match(query)
    if m:
        lat, lon = float(m[1]), float(m[2])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise WwError("place_not_found", query.strip())
        return _with_address(Place(f"{lat},{lon}", lat, lon), lang, http)
    return geocode(query, lang, global_search, http)


def _with_address(place: Place, lang: str, http) -> Place:
    """Country and region are a bonus for coordinates; without them only alerts are unavailable."""
    try:
        found = reverse(place.lat, place.lon, lang, http)
    except WwError:
        return place
    return replace(place, country_code=found.country_code, region=found.region, locality=found.locality,
                   district=found.district)


def _is_district(r: dict, query: str) -> bool:
    name = r.get("name") or ""
    return r.get("class") == "boundary" and r.get("type") == "administrative" and name.startswith(query)


def _pick(results: list[dict], query: str) -> dict:
    # A same-named village often ranks first ("坪林" in 苗栗 before 新北市坪林區), so prefer the district
    return next((r for r in results if _is_district(r, query)), results[0])


def _search(params: dict, http) -> list[dict]:
    return _get(http, f"{NOMINATIM}?{urllib.parse.urlencode(params)}", "nominatim")


def _district_by_suffix(query: str, base: dict, first: dict, http) -> dict | None:
    """Nominatim may not list the district at all for a bare name; ask for 坪林區, 坪林鄉, ... instead.

    Only for Taiwan-style (CJK) names; a failed retry just means keeping the first result."""
    if first.get("type") not in SMALL_PLACES or query.endswith(ADMIN_SUFFIXES) or not CJK.search(query):
        return None
    for suffix in ("區", "鄉", "鎮"):
        time.sleep(PAUSE)  # Nominatim allows one request per second
        try:
            results = _search({**base, "q": query + suffix}, http)
        except WwError:
            return None
        for r in results:
            if _is_district(r, query):
                return r
    return None


def geocode(query: str, lang: str, global_search: bool, http) -> Place:
    base = {"q": query, "format": "json", "addressdetails": 1, "limit": 5, "accept-language": lang}
    # Taiwan first, then worldwide; --global goes straight to worldwide
    attempts = [base] if global_search else [{**base, "countrycodes": "tw"}, base]
    for i, params in enumerate(attempts):
        if i:
            time.sleep(PAUSE)
        res = _search(params, http)
        if res:
            r = _pick(res, query)
            if not global_search and not _is_district(r, query):
                r = _district_by_suffix(query, params, res[0], http) or r
            parts = [p.strip() for p in r["display_name"].split(",")]
            name = ", ".join(p for p in parts if not p.isdigit())
            return Place(name, float(r["lat"]), float(r["lon"]), **_address_fields(r))
    raise WwError("place_not_found", query)


def reverse(lat: float, lon: float, lang: str, http) -> Place:
    q = urllib.parse.urlencode({"format": "json", "addressdetails": 1, "zoom": 14, "lat": lat, "lon": lon,
                                "accept-language": lang})
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
    keys = ("city", "county", "state", "province") if cc == "tw" else ("state", "province", "county")
    region = next((addr[k] for k in keys if addr.get(k)), None)
    if not region and cc == "jp":
        region = _japan_prefecture(r, addr)
    if not region and cc != "tw":
        region = addr.get("city")
    locality = next((addr[k] for k in ("suburb", "town", "city_district", "village", "municipality", "city")
                     if addr.get(k) and addr[k] != region), None)
    # County-level area (German Kreis) for matching county-based warning feeds; Taiwan's county is the region
    district = None if cc == "tw" else (addr.get("county") or addr.get("city"))
    return {"country_code": cc, "region": region, "locality": locality, "district": district}


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
