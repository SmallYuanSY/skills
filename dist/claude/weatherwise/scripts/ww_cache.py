"""Request cache: one fetch per URL per run, plus a TTL'd copy on disk for slow-moving data."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

DAY = 86400
ALERT_TTL = 300
GDACS = "https://www.gdacs.org"
ALERT_FEEDS = (
    "https://alerts.ncdr.nat.gov.tw",
    "https://www.jma.go.jp/bosai/warning",
    "https://data.weather.gov.hk",
    "https://api.weather.gov",
    "https://api.weather.gc.ca",
    "https://feeds.meteoalarm.org",
)
ALERT_SOURCES = ALERT_FEEDS + (GDACS,)  # whose age the output reports as "as of"
OPEN_METEO = "https://api.open-meteo.com"
# First matching prefix wins; anything unlisted is only de-duplicated within a run.
TTLS = (
    *((p, ALERT_TTL) for p in ALERT_FEEDS),
    (GDACS, 900),
    (OPEN_METEO, 900),
    ("https://weatherkit.apple.com/api/v1/weather", 900),
    ("https://www.jma.go.jp/bosai/common/const/area.json", 30 * DAY),
    ("https://nominatim.openstreetmap.org", 30 * DAY),
)


def cache_dir() -> Path:
    override = os.environ.get("WEATHERWISE_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or "~/.cache"
    return Path(base).expanduser() / "weatherwise"


_default_dir = cache_dir  # Cached.__init__ shadows the name with its parameter


def ttl_for(url: str) -> int:
    if url.startswith(OPEN_METEO) and "timezone=auto" in url:
        return 30 * DAY  # a coordinate's timezone never changes
    for prefix, ttl in TTLS:
        if url.startswith(prefix):
            return ttl
    return 0


class Cached:
    """Wraps a fetcher with the same signature as ww_http.get. Failures are never cached,
    and any cache-file problem just means a normal fetch."""

    def __init__(self, http, now_ts: int, cache_dir: Path | None = None):
        self.http = http
        self.now_ts = now_ts
        self.dir = cache_dir if cache_dir is not None else _default_dir()
        self.memo: dict = {}
        self.disk_times: dict[str, int] = {}  # url -> when the disk copy we used was written

    def __call__(self, url: str, headers: dict | None = None, *, text: bool = False):
        key = (url, text)
        if key in self.memo:
            return self.memo[key]
        ttl = ttl_for(url)
        path = self.dir / hashlib.sha256(url.encode()).hexdigest()
        if ttl:
            hit = self._read(path, ttl, text)
            if hit is not None:
                self.memo[key] = hit[0]
                self.disk_times[url] = hit[1]
                return hit[0]
        body = self.http(url, headers, text=text)
        self.memo[key] = body
        if ttl:
            self._write(path, text, body)
        return body

    def is_fresh(self, url: str, text: bool = False) -> bool:
        """True when calling this URL would not make a request."""
        if (url, text) in self.memo:
            return True
        ttl = ttl_for(url)
        return bool(ttl) and self._read(self.dir / hashlib.sha256(url.encode()).hexdigest(), ttl, text) is not None

    def fetched_at(self, url: str) -> int | None:
        """When the data served for this URL was fetched, or None if it came live this run."""
        return self.disk_times.get(url)

    def _read(self, path: Path, ttl: int, text: bool):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            age = self.now_ts - entry["t"]
            if entry["text"] is text and 0 <= age < ttl:
                return entry["body"], entry["t"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def _write(self, path: Path, text: bool, body) -> None:
        tmp = None
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"t": self.now_ts, "text": text, "body": body}, f)
            os.replace(tmp, path)
        except (OSError, TypeError, ValueError):
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
