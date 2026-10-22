"""The config commands an agent runs on the user's behalf. Every write is validated first."""
import os
from pathlib import Path

from ww_config import KEY_FILE_NAME, ensure_private_dir, mask, resolve_lang, save_config, weatherkit_settings
from ww_errors import WwError
from ww_http import HttpError
from ww_model import Place
from ww_places import resolve_place, reverse, with_timezone
from ww_sources import fetch_weatherkit

# Where the WeatherKit test request asks for weather when no default place is set
TEST_PLACE = Place("Taipei", 25.033, 121.565, "Asia/Taipei")


def show(cfg: dict, d: Path) -> str:
    lines = [f"config: {d / 'config.json'}", f"lang: {resolve_lang(None, cfg)}"]
    df = cfg.get("default")
    lines.append(
        f"default: {df['name']} ({df['lat']:.3f}, {df['lon']:.3f}) timezone={df.get('timezone')}"
        if df else "default: none"
    )
    try:
        wk = weatherkit_settings(cfg)
    except WwError as e:
        lines.append(f"source: weatherkit misconfigured ({e.code}: {e.detail})")
        return "\n".join(lines)
    if not wk:
        lines.append("source: open-meteo")
        return "\n".join(lines)
    lines.append("source: weatherkit")
    lines.append(
        f"weatherkit: team_id={mask(wk['team_id'])} key_id={mask(wk['key_id'])} "
        f"service_id={mask(wk['service_id'])} key_path={wk['key_path']}"
    )
    return "\n".join(lines)


def set_default(query: str, global_search: bool, cfg: dict, d: Path, lang: str, http) -> str:
    place = with_timezone(resolve_place(query, cfg, lang, global_search, http), http)
    cfg["default"] = {"name": place.name, "lat": place.lat, "lon": place.lon, "timezone": place.timezone,
                      "country_code": place.country_code, "region": place.region, "locality": place.locality}
    save_config(d, cfg)
    return (
        f"saved: default = {place.name} ({place.lat:.3f}, {place.lon:.3f}) timezone={place.timezone}\n"
        "action: confirm with the user that this is the right place"
    )


def ensure_default_complete(cfg: dict, d: Path, lang: str, http) -> None:
    """Defaults saved before country codes existed get one reverse lookup, written back for good."""
    df = cfg.get("default")
    if not df or df.get("country_code"):
        return
    try:
        found = reverse(df["lat"], df["lon"], lang, http)
    except WwError:
        return  # try again next run; the weather itself does not need it
    if not found.country_code:
        return
    df.update(country_code=found.country_code, region=found.region, locality=found.locality)
    save_config(d, cfg)


def set_lang(lang: str, cfg: dict, d: Path) -> str:
    cfg["lang"] = resolve_lang(lang, {})
    save_config(d, cfg)
    return f"saved: lang = {cfg['lang']}"


def set_weatherkit(team_id, service_id, key_file, key_id, cfg, d, lang, http, now_ts) -> str:
    src = Path(key_file).expanduser()
    if not src.is_file():
        raise WwError("invalid_key_file", str(src))
    m = KEY_FILE_NAME.match(src.name)
    key_id = key_id or (m[1] if m else None)
    saved = cfg.get("weatherkit") or {}  # a new key keeps the IDs that already worked
    kept = [n for n, v in (("team_id", team_id), ("service_id", service_id)) if not v and saved.get(n)]
    team_id = team_id or saved.get("team_id")
    service_id = service_id or saved.get("service_id")
    missing = [n for n, v in (("team_id", team_id), ("key_id", key_id), ("service_id", service_id)) if not v]
    if missing:
        hint = " (file is not named AuthKey_<KeyID>.p8; pass --key-id)" if "key_id" in missing else ""
        raise WwError("weatherkit_config_incomplete", ", ".join(missing) + hint)

    wk = {"team_id": team_id, "key_id": key_id, "service_id": service_id,
          "key_path": str(src)}
    df = cfg.get("default")
    place = Place(df["name"], df["lat"], df["lon"], df.get("timezone"), df.get("country_code")) if df else TEST_PLACE
    place = with_timezone(place, http)
    try:  # one real request before anything is written
        fetch_weatherkit(place, 1, lang, wk, http, now_ts)
    except HttpError as e:
        if e.status in (401, 403):
            used = ", ".join(f"{n}={mask(wk[n])} {'from saved config' if n in kept else 'as given'}"
                             for n in ("team_id", "service_id"))
            raise WwError("weatherkit_auth_failed", f"HTTP {e.status}; {used}, key_id={key_id}") from None
        raise WwError("service_error", f"weatherkit HTTP {e.status}") from None

    ensure_private_dir(d)
    dest = d / f"AuthKey_{key_id}.p8"
    if src.resolve() != dest.resolve():
        # Create the key as 0600 from the start, so it is never world-readable
        # for a window between the copy and a later chmod.
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(src.read_bytes())
    os.chmod(dest, 0o600)
    old_copy = Path(saved.get("key_path", "")).expanduser()
    if saved.get("key_path") and old_copy.parent.resolve() == d.resolve() and old_copy.resolve() != dest.resolve():
        old_copy.unlink(missing_ok=True)  # only our own copy of the replaced key
    cfg["weatherkit"] = {**wk, "key_path": str(dest)}
    save_config(d, cfg)
    note = f"; kept the saved {' and '.join(kept)}" if kept else ""
    return f"saved: weatherkit (test request succeeded{note})\nsource: weatherkit"


def remove_weatherkit(cfg: dict, d: Path) -> str:
    wk = cfg.pop("weatherkit", None) or {}
    key = Path(wk.get("key_path", "")).expanduser()
    if wk.get("key_path") and key.parent.resolve() == d.resolve():  # only our own copy
        key.unlink(missing_ok=True)
    save_config(d, cfg)
    return "removed: weatherkit\nsource: open-meteo"
