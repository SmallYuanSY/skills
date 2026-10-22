import pytest

from conftest import FakeHttp
from ww_cache import Cached, cache_dir, ttl_for
from ww_errors import WwError
from ww_http import HttpError

ALERTS = "https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx"


def test_same_url_in_one_run_is_fetched_once(tmp_path):
    http = FakeHttp({"https://api.weather.gov/": {"features": []}})
    c = Cached(http, now_ts=1000, cache_dir=tmp_path)
    c("https://api.weather.gov/alerts/active?point=1,2")
    c("https://api.weather.gov/alerts/active?point=1,2")
    assert len(http.calls) == 1


def test_disk_cache_is_used_within_ttl_and_refreshed_after(tmp_path):
    http = FakeHttp({ALERTS: "<feed/>"})
    Cached(http, 1000, tmp_path)(ALERTS, text=True)
    assert Cached(http, 1000 + 299, tmp_path)(ALERTS, text=True) == "<feed/>"
    assert len(http.calls) == 1
    Cached(http, 1000 + 301, tmp_path)(ALERTS, text=True)
    assert len(http.calls) == 2


def test_errors_are_not_cached(tmp_path):
    outcomes = [HttpError(500), {"features": []}]

    def flaky(url):
        o = outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o

    http = FakeHttp({"https://api.weather.gov/": flaky})
    with pytest.raises(HttpError):
        Cached(http, 1000, tmp_path)("https://api.weather.gov/x")
    c = Cached(http, 1000, tmp_path)
    with pytest.raises(WwError):
        Cached(FakeHttp({"https://api.weather.gov/": WwError("network_error", "x")}), 1000, tmp_path)("https://api.weather.gov/x")
    assert c("https://api.weather.gov/x") == {"features": []}
    assert len(http.calls) == 2


def test_broken_cache_file_is_ignored(tmp_path):
    http = FakeHttp({ALERTS: "<feed/>"})
    Cached(http, 1000, tmp_path)(ALERTS, text=True)
    for f in tmp_path.iterdir():
        f.write_text("not json{{")
    assert Cached(http, 1001, tmp_path)(ALERTS, text=True) == "<feed/>"
    assert len(http.calls) == 2


def test_unwritable_cache_dir_is_ignored(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    http = FakeHttp({ALERTS: "<feed/>"})
    assert Cached(http, 1000, blocker / "sub")(ALERTS, text=True) == "<feed/>"


def test_unknown_url_is_not_written_to_disk(tmp_path):
    http = FakeHttp({"https://example.com/": {"a": 1}})
    c = Cached(http, 1000, tmp_path)
    c("https://example.com/x")
    c("https://example.com/x")
    assert len(http.calls) == 1
    assert list(tmp_path.iterdir()) == []


def test_text_and_json_responses_do_not_mix_on_disk(tmp_path):
    url = "https://api.weather.gov/x"
    http = FakeHttp({url: lambda u: "<t/>" if len(http.calls) == 1 else {"k": 1}})
    assert Cached(http, 1000, tmp_path)(url, text=True) == "<t/>"
    assert Cached(http, 1001, tmp_path)(url) == {"k": 1}


@pytest.mark.parametrize("url,ttl", [
    (ALERTS, 300),
    ("https://www.jma.go.jp/bosai/warning/data/warning/130000.json", 300),
    ("https://data.weather.gov.hk/weatherAPI/opendata/weather.php", 300),
    ("https://api.weather.gc.ca/collections/x", 300),
    ("https://feeds.meteoalarm.org/feeds/x", 300),
    ("https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP", 900),
    ("https://api.open-meteo.com/v1/forecast?x=1", 900),
    ("https://weatherkit.apple.com/api/v1/weather/en/1/2", 900),
    ("https://www.jma.go.jp/bosai/common/const/area.json", 30 * 86400),
    ("https://nominatim.openstreetmap.org/search?q=x", 30 * 86400),
    ("https://example.com/", 0),
])
def test_ttl_for(url, ttl):
    assert ttl_for(url) == ttl


def test_cache_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("WEATHERWISE_CACHE_DIR", str(tmp_path / "c"))
    assert cache_dir() == tmp_path / "c"
    monkeypatch.delenv("WEATHERWISE_CACHE_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "x"))
    assert cache_dir() == tmp_path / "x" / "weatherwise"
