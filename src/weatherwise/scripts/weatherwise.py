#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyjwt[crypto]>=2.8"]
# ///
# weatherwise · Copyright (c) 2026 SmallYuan · MIT License · https://github.com/SmallYuanSY/skills
"""Weather for an agent to read: Open-Meteo by default, Apple WeatherKit when configured.

  weatherwise [place] [--global] [--days N] [--lang TAG] [--json] [--version]
  weatherwise config show | set-default | set-lang | weatherkit
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ww_config import config_dir, load_config, resolve_lang, weatherkit_settings  # noqa: E402
from ww_errors import WwError  # noqa: E402
from ww_http import REPO, VERSION, HttpError, get_json  # noqa: E402
from ww_places import resolve_place, with_timezone  # noqa: E402
from ww_render import render_error, render_report  # noqa: E402
from ww_sources import fetch_open_meteo, fetch_weatherkit  # noqa: E402

VERSION_LINE = f"weatherwise {VERSION} · by SmallYuan · {REPO}"
AUTH_FALLBACK = (
    "weatherkit_auth_failed (HTTP {status}), fell back to open-meteo; tell the user their "
    "WeatherKit key may be revoked or their Apple Developer membership may have expired"
)


class Parser(argparse.ArgumentParser):
    """Report argument mistakes in the model-facing error format instead of exiting."""

    def error(self, message):
        raise WwError("bad_arguments", message)


def run_weather(argv: list[str], http, now: datetime | None) -> str:
    p = Parser(prog="weatherwise")
    p.add_argument("place", nargs="?")
    p.add_argument("--global", dest="global_search", action="store_true")
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--lang")
    p.add_argument("--json", action="store_true")
    p.add_argument("--version", action="store_true")
    a = p.parse_args(argv)
    if a.version:
        return VERSION_LINE

    cfg = load_config(config_dir())
    lang = resolve_lang(a.lang, cfg)
    wk = weatherkit_settings(cfg)  # config mistakes stop here, before any request
    place = with_timezone(resolve_place(a.place, cfg, lang, a.global_search, http), http)
    days = min(max(a.days, 1), 10)
    local_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(place.timezone))

    notice = None
    if wk:
        try:
            report = fetch_weatherkit(place, days, lang, wk, http, int(local_now.timestamp()))
        except HttpError as e:
            if e.status not in (401, 403):
                raise WwError("service_error", f"weatherkit HTTP {e.status}") from None
            notice = AUTH_FALLBACK.format(status=e.status)
            report = fetch_open_meteo(place, days, http)
    else:
        report = fetch_open_meteo(place, days, http)

    if a.json:
        out = {"source": report.source, **({"notice": notice} if notice else {}), "data": report.raw}
        return json.dumps(out, ensure_ascii=False, indent=2)
    return render_report(report, place, local_now, notice)


def run_config(argv: list[str], http, now: datetime | None) -> str:
    raise WwError("bad_arguments", "config commands are not available yet")


def main(argv: list[str] | None = None, *, http=get_json, now: datetime | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["config"]:
            out = run_config(argv[1:], http, now)
        else:
            out = run_weather(argv, http, now)
    except WwError as e:
        print(render_error(e))
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
