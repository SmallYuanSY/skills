"""The only place that talks to the network."""
import json
import urllib.error
import urllib.request

from ww_errors import WwError

VERSION = "1.0.0"
REPO = "https://github.com/SmallYuanSY/skills"
USER_AGENT = f"weatherwise/{VERSION} (+{REPO})"


class HttpError(Exception):
    def __init__(self, status: int, body: str = ""):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


def get_json(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:  # subclass of URLError, so it must come first
        raise HttpError(e.code, e.read().decode(errors="replace")[:300]) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise WwError("network_error", str(e)) from None
