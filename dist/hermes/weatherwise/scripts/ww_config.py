"""~/.config/weatherwise/config.json: read, validate, and write it safely."""
import json
import os
import re
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from ww_errors import WwError

LANG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")  # BCP 47, loosely
KEY_FILE_NAME = re.compile(r"^AuthKey_([A-Z0-9]+)\.p8$")  # Apple's download name
REQUIRED_WEATHERKIT = ("team_id", "key_id", "service_id", "key_path")


def config_dir() -> Path:
    return Path(os.environ.get("WEATHERWISE_CONFIG_DIR") or "~/.config/weatherwise").expanduser()


def load_config(d: Path) -> dict:
    path = d / "config.json"
    if not path.exists():
        return {}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # unreadable, not UTF-8, or not JSON
        raise WwError("config_invalid", str(path)) from None
    problem = _shape_problem(cfg)
    if problem:
        raise WwError("config_invalid", f"{path}: {problem}")
    return cfg


def _shape_problem(cfg) -> str | None:
    """Catch hand-edited values here, so nothing downstream crashes on them."""
    if not isinstance(cfg, dict):
        return "not a JSON object"
    if "lang" in cfg and not isinstance(cfg["lang"], str):
        return "lang must be a string"
    if "weatherkit" in cfg and not isinstance(cfg["weatherkit"], dict):
        return "weatherkit must be an object"
    d = cfg.get("default")
    if d is None:
        return None
    if not isinstance(d, dict):
        return "default must be an object"
    if not isinstance(d.get("name"), str) or not d["name"]:
        return "default.name is missing"
    for key, limit in (("lat", 90), ("lon", 180)):
        v = d.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not -limit <= v <= limit:
            return f"default.{key} must be a number between -{limit} and {limit}"
    if d.get("timezone") is not None:
        try:
            ZoneInfo(d["timezone"])
        except (KeyError, ValueError, TypeError):  # ZoneInfoNotFoundError is a KeyError
            return "default.timezone is not a valid time zone"
    return None


def save_config(d: Path, cfg: dict) -> None:
    """Write to a temp file, then rename, so a failure never leaves a half-written config."""
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, d / "config.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def resolve_lang(cli: str | None, cfg: dict) -> str:
    lang = cli or cfg.get("lang") or "zh-TW"
    if not LANG.match(lang):
        raise WwError("unsupported_lang", lang)
    return lang


def weatherkit_settings(cfg: dict) -> dict | None:
    wk = cfg.get("weatherkit")
    if not wk:
        return None
    missing = [k for k in REQUIRED_WEATHERKIT if not wk.get(k)]
    if missing:
        raise WwError("weatherkit_config_incomplete", ", ".join(missing))
    if not Path(wk["key_path"]).expanduser().is_file():
        raise WwError("weatherkit_key_missing", wk["key_path"])
    return wk


def mask(value: str) -> str:
    return "…" if len(value) <= 4 else f"{value[:2]}…{value[-2:]}"
