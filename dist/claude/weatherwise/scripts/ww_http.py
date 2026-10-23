"""The only place that talks to the network."""
import json
import urllib.error
import urllib.request

from ww_errors import WwError

VERSION = "2.0.0"
REPO = "https://github.com/SmallYuanSY/skills"
USER_AGENT = f"weatherwise/{VERSION} (+{REPO})"
TIMEOUT = 15  # seconds
SLOW = {"https://www.gdacs.org": 30}  # GDACS geometry has taken ~14 s


class HttpError(Exception):
    def __init__(self, status: int, body: str = ""):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


def get(url: str, headers: dict | None = None, *, text: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        timeout = next((t for prefix, t in SLOW.items() if url.startswith(prefix)), TIMEOUT)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            status = getattr(r, "status", 200)
    except urllib.error.HTTPError as e:  # subclass of URLError, so it must come first
        try:
            detail = e.read().decode(errors="replace")[:300]
        except OSError:
            detail = ""
        raise HttpError(e.code, detail) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise WwError("network_error", str(e)) from None
    if status == 204:  # No Content (GDACS when there is no event): nothing, not a broken body
        return "" if text else None
    if text:
        return body.decode(errors="replace")
    try:
        return json.loads(body)
    except ValueError:  # e.g. a captive portal's HTML page
        raise WwError("service_error", "response was not JSON") from None
