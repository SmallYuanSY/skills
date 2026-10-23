#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyjwt[crypto]>=2.8"]
# ///
# weatherwise · Copyright (c) 2026 SmallYuan · MIT License · https://github.com/SmallYuanSY/skills
"""Weather for an agent to read: Open-Meteo by default, Apple WeatherKit when configured.

  weatherwise [place ...] [--global] [--days N] [--lang TAG] [--json] [--detail] [--version]
  weatherwise config show | set-default | set-lang | weatherkit
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ww_alerts import collect  # noqa: E402
from ww_cache import ALERT_SOURCES, Cached  # noqa: E402
from ww_config import config_dir, load_config, resolve_lang, weatherkit_settings  # noqa: E402
from ww_errors import WwError  # noqa: E402
from ww_http import REPO, VERSION, HttpError, get  # noqa: E402
from ww_places import Paced, resolve_place, with_timezone  # noqa: E402
from ww_render import render, render_error, render_json  # noqa: E402
from ww_sources import fetch_open_meteo_many, fetch_weatherkit  # noqa: E402
from ww_setup import ensure_default_complete, remove_weatherkit, set_default, set_lang, set_weatherkit, show  # noqa: E402

MAX_PLACES = 5
VERSION_LINE = f"weatherwise {VERSION} · by SmallYuan · {REPO}"
AUTH_FALLBACK = (
    "weatherkit_auth_failed (HTTP {status}), fell back to open-meteo; tell the user their "
    "WeatherKit key may be revoked or their Apple Developer membership may have expired"
)


class Parser(argparse.ArgumentParser):
    """Report argument mistakes in the model-facing error format instead of exiting."""

    def error(self, message):
        raise WwError("bad_arguments", message)


def _forecasts(places: list, days: int, lang: str, wk, http, now_ts: int):
    """One Report or WwError per place. Open-Meteo is a single request; WeatherKit is one per place."""
    out: list = [None] * len(places)
    notice = None
    fallback = list(range(len(places)))
    if wk:
        fallback = []
        revoked = False
        for i, place in enumerate(places):
            if revoked:  # the key was rejected once; asking again for every place would just repeat it
                fallback.append(i)
                continue
            try:
                out[i] = fetch_weatherkit(place, days, lang, wk, http, now_ts)
            except HttpError as e:
                if e.status in (401, 403):
                    notice = AUTH_FALLBACK.format(status=e.status)
                    revoked = True
                    fallback.append(i)
                else:
                    out[i] = WwError("service_error", f"weatherkit HTTP {e.status}")
            except WwError as e:
                if e.code == "invalid_key_file":
                    raise  # the same key signs every place, so this is not a per-place failure
                out[i] = e
    if fallback:
        try:
            for i, report in zip(fallback, fetch_open_meteo_many([places[i] for i in fallback], days, http)):
                out[i] = report
        except WwError as e:
            for i in fallback:
                out[i] = e
    return out, notice


def _alerts_as_of(cached: Cached, now: datetime) -> datetime:
    """Alert data older than this run (served from the disk cache) is reported with its own age."""
    times = [t for url, _ in cached.memo
             if url.startswith(ALERT_SOURCES) and (t := cached.fetched_at(url)) is not None]
    return datetime.fromtimestamp(min(times), timezone.utc) if times else now


def run_weather(argv: list[str], http, now: datetime | None) -> str:
    p = Parser(prog="weatherwise")
    p.add_argument("places", nargs="*")
    p.add_argument("--global", dest="global_search", action="store_true")
    p.add_argument("--days", type=int)
    p.add_argument("--lang")
    p.add_argument("--json", action="store_true")
    p.add_argument("--detail", action="store_true")
    p.add_argument("--version", action="store_true")
    a = p.parse_intermixed_args(argv)
    if a.version:
        return VERSION_LINE
    if len(a.places) > MAX_PLACES:
        raise WwError("too_many_places", str(len(a.places)))

    now = now or datetime.now(timezone.utc)
    cached = Cached(http, int(now.timestamp()))
    http = Paced(cached)
    cfg = load_config(config_dir())
    lang = resolve_lang(a.lang, cfg)
    wk = weatherkit_settings(cfg)  # config mistakes stop here, before any request
    if not a.places:
        ensure_default_complete(cfg, config_dir(), lang, http)
    queries = a.places or [None]
    days = min(max(a.days if a.days is not None else (3 if len(queries) == 1 else 1), 1), 10)

    resolved: list = []  # (Place | None, WwError | None) per query
    for q in queries:
        try:
            resolved.append((with_timezone(resolve_place(q, cfg, lang, a.global_search, http), http), None))
        except WwError as e:
            if len(queries) == 1:
                raise
            resolved.append((None, e))

    ok = [i for i, (place, _) in enumerate(resolved) if place is not None]
    reports: list = [e for _, e in resolved]
    if ok:
        got, notice = _forecasts([resolved[i][0] for i in ok], days, lang, wk, http, int(now.timestamp()))
        for i, r in zip(ok, got):
            reports[i] = r
    else:
        notice = None
    errors = [r for r in reports if isinstance(r, WwError)]
    if len(errors) == len(reports):
        raise errors[0]

    places = [resolved[i][0] for i in ok]
    per_place, cyclones, cyclone_error = collect(places, http, now)
    alerts: list = [None] * len(resolved)
    for i, pa in zip(ok, per_place):
        alerts[i] = pa
    cyclones = [(c, [ok[j] for j in idx]) for c, idx in cyclones]  # back to positions in the request
    entries = [(resolved[i][0], reports[i], alerts[i]) for i in range(len(resolved))]

    as_of = _alerts_as_of(cached, now)
    if a.json:
        return json.dumps(render_json(entries, cyclones, notice, a.places or [None], cyclone_error, as_of),
                          ensure_ascii=False, indent=2)
    return render(entries, cyclones, now, as_of, days, notice, a.detail, cyclone_error)


def run_config(argv: list[str], http, now: datetime | None) -> str:
    p = Parser(prog="weatherwise config")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    sd = sub.add_parser("set-default")
    sd.add_argument("place")
    sd.add_argument("--global", dest="global_search", action="store_true")
    sl = sub.add_parser("set-lang")
    sl.add_argument("lang")
    wk = sub.add_parser("weatherkit")
    wk.add_argument("--team-id")
    wk.add_argument("--service-id")
    wk.add_argument("--key-file")
    wk.add_argument("--key-id")
    wk.add_argument("--remove", action="store_true")
    a = p.parse_args(argv)

    d = config_dir()
    cfg = load_config(d)
    if a.cmd == "show":
        return show(cfg, d)
    if a.cmd == "set-default":
        return set_default(a.place, a.global_search, cfg, d, resolve_lang(None, cfg), http)
    if a.cmd == "set-lang":
        return set_lang(a.lang, cfg, d)
    if a.remove:
        return remove_weatherkit(cfg, d)
    if not a.key_file:
        raise WwError("invalid_key_file", "--key-file is required")
    now_ts = int((now or datetime.now(timezone.utc)).timestamp())
    return set_weatherkit(a.team_id, a.service_id, a.key_file, a.key_id,
                          cfg, d, resolve_lang(None, cfg), http, now_ts)


def main(argv: list[str] | None = None, *, http=get, now: datetime | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["config"]:
            out = run_config(argv[1:], http, now)
        else:
            out = run_weather(argv, http, now)
    except WwError as e:
        print(render_error(e))
        return 1
    except Exception as e:  # never show the model a traceback, or an exception message that might hold file contents
        print(render_error(WwError("internal_error", type(e).__name__)))
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
