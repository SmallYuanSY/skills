# weatherwise 與 skill 轉譯器：實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做出公開 repo 的第一個 skill `weatherwise`（Open-Meteo 預設、WeatherKit 選配、輸出給模型讀），以及把一份原始檔轉成 Hermes／Claude Code 版本的轉譯器。

**Architecture:** skill 的程式放在 `src/weatherwise/scripts/`，入口 `weatherwise.py` 是 uv inline script，其他模組放在同一資料夾，各管一件事：錯誤、HTTP、資料結構、輸出、地點、資料來源、設定檔、設定指令。所有網路呼叫都透過一個可注入的 `http(url, headers) -> JSON` 函式，測試時換成假的，不打網路。轉譯器 `tools/translate.py` 只用標準庫，把 `src/` 轉成 `dist/hermes/` 和 `dist/claude/`。

**Tech Stack:** Python ≥ 3.10、uv、pytest、PyJWT[crypto]（WeatherKit 簽章）、GitHub Actions。

**Spec:** `docs/specs/2026-10-07-weatherwise-and-translator-design.md`

## Global Constraints

- repo：`SmallYuanSY/skills`，本機 `~/Developer/skills`，MIT，Copyright (c) 2026 SmallYuan。
- 版本 `1.0.0`；User-Agent `weatherwise/1.0.0 (+https://github.com/SmallYuanSY/skills)`；`--version` 印出 `weatherwise 1.0.0 · by SmallYuan · https://github.com/SmallYuanSY/skills`。
- 設定目錄 `~/.config/weatherwise/`，可用環境變數 `WEATHERWISE_CONFIG_DIR` 覆寫（測試用）。設定檔和 `.p8` 的權限都是 `600`。
- 輸出給模型讀：英文 `key: value`，不用 emoji；錯誤是 `error: <code>` 加 `action: <下一步>`，結束碼 1。
- `lang` 預設 `zh-TW`，只影響 Nominatim 的 `accept-language` 和 WeatherKit 網址裡的語言。
- `--days` 預設 3，限制在 1 到 10。
- 不讀出、不印出 `.p8` 的內容；不在輸出或 SKILL.md 裡提到作者（frontmatter、LICENSE、`--version`、User-Agent 除外）；不回傳任何資料。
- repo 裡不能出現私人資訊。隱私 deny-list 只放在本機 `tests/private-terms.local.txt`（gitignore）。
- 測試全部不打網路。指令：`uv run pytest`。
- push 和建立 GitHub repo 都要先問過使用者。這份計畫只到本機 commit 和實測為止。

## Review Focus

1. **座標格式**：`24.15, 120.67`（有空白）要能解析；超出範圍（例如 `200,10`）要回 `place_not_found`，不能送去 API。→ Task 3 測試。
2. **Open-Meteo 回傳 null**：`precipitation_probability_max` 或 `uv_index` 是 `null` 時要輸出 `unknown`，不能當掉。→ Task 2、Task 4 測試。
3. **設定檔壞掉**：`config.json` 不是合法 JSON 時回 `config_invalid`，不能噴 traceback。→ Task 5 測試。
4. **時區不在本機時區**：`local_time` 和 WeatherKit 的每日日期要用地點的時區計算，不是執行機器的時區。UTC 23:30 在台北已經是隔天。→ Task 2、Task 4 測試。
5. **`--days` 超出範圍**：`--days 0` 或 `--days 20` 要限制成 1 或 10，不能讓 API 回錯。→ Task 6 測試。

---

## 檔案結構

```
skills/
├── pyproject.toml                      uv 專案設定：pytest、PyJWT 開發依賴、pythonpath
├── .gitignore
├── LICENSE
├── README.md
├── .github/workflows/test.yml
├── src/weatherwise/
│   ├── SKILL.md                        {{SKILL_DIR}} 佔位符
│   ├── references/weatherkit-setup.md
│   └── scripts/
│       ├── weatherwise.py              CLI 入口（uv inline script）：解析參數、分派、印輸出
│       ├── ww_errors.py                WwError 和每個錯誤代碼的 action
│       ├── ww_http.py                  get_json、HttpError、VERSION、USER_AGENT
│       ├── ww_model.py                 Place / Current / Day / Report，天氣狀況名稱
│       ├── ww_render.py                Report → 給模型讀的文字；錯誤 → 文字
│       ├── ww_places.py                地名／座標 → Place，時區查詢
│       ├── ww_sources.py               Open-Meteo、WeatherKit → Report
│       ├── ww_config.py                設定檔讀寫、lang、weatherkit 設定驗證、遮蔽
│       └── ww_setup.py                 config 子指令
├── tools/translate.py                  轉譯器
├── dist/{hermes,claude}/weatherwise/   轉譯器產生
└── tests/
    ├── conftest.py                     FakeHttp、fixture、測試用金鑰
    ├── test_model.py
    ├── test_render.py
    ├── test_places.py
    ├── test_sources.py
    ├── test_config.py
    ├── test_cli.py
    ├── test_setup.py
    ├── test_translate.py
    ├── test_privacy.py
    └── private-terms.example.txt
```

---

### Task 1: 專案骨架、錯誤、HTTP、資料結構

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `tests/conftest.py`
- Create: `src/weatherwise/scripts/ww_errors.py`, `ww_http.py`, `ww_model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Produces:
  - `ww_errors.ACTIONS: dict[str, str]`、`ww_errors.WwError(code: str, detail: str = "")`，屬性 `.code`、`.detail`
  - `ww_http.VERSION = "1.0.0"`、`ww_http.REPO`、`ww_http.USER_AGENT`、`ww_http.HttpError(status: int, body: str = "")`，屬性 `.status`
  - `ww_http.get_json(url: str, headers: dict | None = None) -> Any`：HTTP 錯誤丟 `HttpError`，連線失敗丟 `WwError("network_error")`
  - `ww_model.Place(name, lat, lon, timezone=None)`、`Current(condition, temperature, feels_like, humidity, wind_kmh, uv)`、`Day(date, condition, temp_min, temp_max, precip_chance)`、`Report(source, current, days, alerts, raw={})`
  - `ww_model.wmo_condition(code: int) -> str`、`ww_model.weatherkit_condition(code: str) -> str`
  - `conftest`：`FakeHttp`、`OPEN_METEO`、`WEATHERKIT`、`NOW`、`TAIPEI_DEFAULT`、`p8_key` fixture、`config_dir` fixture

- [ ] **Step 1: 建立專案設定檔**

`pyproject.toml`:

```toml
[project]
name = "smallyuan-skills"
version = "0.0.0"
requires-python = ">=3.10"
dependencies = []

[dependency-groups]
dev = ["pytest>=8", "pyjwt[crypto]>=2.8"]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src/weatherwise/scripts", "tools"]
```

`.gitignore`:

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.DS_Store
/tests/private-terms.local.txt
```

`LICENSE`：標準 MIT 全文，第一行 `MIT License`，版權行 `Copyright (c) 2026 SmallYuan`。

- [ ] **Step 2: 寫 `ww_errors.py`**

```python
"""Errors the model reads. Every code comes with the next step to take."""

ACTIONS = {
    "no_default_location": "ask the user where they are, then run: config set-default <place>",
    "place_not_found": "try another spelling, add --global for places outside Taiwan, or pass lat,lon",
    "network_error": "tell the user the weather could not be fetched right now",
    "service_error": "tell the user the weather service returned an error; try again later",
    "config_invalid": "ask the user to check or delete the config file, then set it up again with the config commands",
    "weatherkit_config_incomplete": "run: config weatherkit with the missing values, or config weatherkit --remove to use the free source",
    "weatherkit_key_missing": "run: config weatherkit again with --key-file <path to the .p8>, or config weatherkit --remove",
    "weatherkit_auth_failed": "tell the user WeatherKit rejected the key (wrong IDs, revoked key, or expired Apple Developer membership); nothing was saved",
    "invalid_key_file": "ask the user for the path to the AuthKey_<KeyID>.p8 file they downloaded from Apple",
    "unsupported_lang": "use a BCP 47 language tag such as zh-TW, en, or ja",
    "bad_arguments": "fix the command using the usage in SKILL.md",
}


class WwError(Exception):
    def __init__(self, code: str, detail: str = ""):
        if code not in ACTIONS:
            raise ValueError(f"unknown error code: {code}")
        super().__init__(code)
        self.code = code
        self.detail = detail
```

- [ ] **Step 3: 寫 `ww_http.py`**

```python
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
```

- [ ] **Step 4: 寫 `tests/conftest.py`**

```python
import sys

sys.dont_write_bytecode = True  # keep __pycache__ out of src/, which the translator copies

from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# 2026-10-07 12:41 UTC = 2026-10-07 20:41 Wed in Taipei
NOW = datetime(2026, 10, 7, 12, 41, tzinfo=timezone.utc)

TAIPEI_DEFAULT = {"name": "台北市", "lat": 25.033, "lon": 121.565, "timezone": "Asia/Taipei"}

OPEN_METEO = {
    "timezone": "Asia/Taipei",
    "current": {
        "time": "2026-10-07T20:30", "temperature_2m": 27.0, "apparent_temperature": 29.1,
        "relative_humidity_2m": 70, "wind_speed_10m": 12.3, "weather_code": 2, "uv_index": 6.0,
    },
    "daily": {
        "time": ["2026-10-07", "2026-10-08"],
        "weather_code": [3, 61],
        "temperature_2m_max": [25.8, 27.4],
        "temperature_2m_min": [21.9, 23.2],
        "precipitation_probability_max": [0, 80],
    },
}

WEATHERKIT = {
    "currentWeather": {
        "conditionCode": "PartlyCloudy", "temperature": 27.04, "temperatureApparent": 29.1,
        "humidity": 0.7, "windSpeed": 12.3, "uvIndex": 6,
    },
    "forecastDaily": {"days": [
        {"forecastStart": "2026-10-06T16:00:00Z", "conditionCode": "Cloudy",
         "temperatureMin": 21.9, "temperatureMax": 25.8, "precipitationChance": 0.0},
        {"forecastStart": "2026-10-07T16:00:00Z", "conditionCode": "Rain",
         "temperatureMin": 23.2, "temperatureMax": 27.4, "precipitationChance": 0.8},
    ]},
    "weatherAlerts": {"alerts": []},
}


class FakeHttp:
    """Routes a URL to the first response whose prefix matches. A response may be data,
    an exception to raise, or a callable taking the URL."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, url: str, headers: dict | None = None):
        self.calls.append((url, headers))
        for prefix, resp in self.routes.items():
            if url.startswith(prefix):
                if isinstance(resp, Exception):
                    raise resp
                return resp(url) if callable(resp) else resp
        raise AssertionError(f"unexpected request: {url}")


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    d = tmp_path / "config"
    monkeypatch.setenv("WEATHERWISE_CONFIG_DIR", str(d))
    return d


@pytest.fixture
def p8_key(tmp_path):
    """A real P-256 key in Apple's file naming, so JWT signing works offline."""
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    path = tmp_path / "downloads" / "AuthKey_ABC123DEF4.p8"
    path.parent.mkdir()
    path.write_bytes(pem)
    return path
```

- [ ] **Step 5: 寫會失敗的測試 `tests/test_model.py`**

```python
import pytest

from ww_errors import ACTIONS, WwError
from ww_model import WMO, weatherkit_condition, wmo_condition

# WeatherKit condition codes that WMO codes map onto
WEATHERKIT_CODES = [
    "Clear", "MostlyClear", "PartlyCloudy", "Cloudy", "Foggy", "Drizzle", "FreezingDrizzle",
    "Rain", "HeavyRain", "FreezingRain", "Snow", "HeavySnow", "Thunderstorms",
]


def test_weatherkit_condition_splits_camel_case():
    assert weatherkit_condition("PartlyCloudy") == "Partly Cloudy"
    assert weatherkit_condition("Rain") == "Rain"


def test_every_wmo_name_matches_a_weatherkit_name():
    names = {weatherkit_condition(c) for c in WEATHERKIT_CODES}
    assert set(WMO.values()) <= names


def test_unknown_wmo_code_is_labelled_not_dropped():
    assert wmo_condition(42) == "Unknown (WMO 42)"


def test_every_error_code_has_an_action():
    assert all(ACTIONS.values())
    with pytest.raises(ValueError):
        WwError("not_a_code")
```

- [ ] **Step 6: 確認測試失敗**

Run: `uv run pytest tests/test_model.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'ww_model'`

- [ ] **Step 7: 寫 `ww_model.py`**

```python
"""What every weather source is turned into before it is printed."""
import re
from dataclasses import dataclass, field


@dataclass
class Place:
    name: str
    lat: float
    lon: float
    timezone: str | None = None


@dataclass
class Current:
    condition: str
    temperature: float
    feels_like: float
    humidity: float  # percent, 0-100
    wind_kmh: float
    uv: float | None


@dataclass
class Day:
    date: str  # YYYY-MM-DD in the place's timezone
    condition: str
    temp_min: float
    temp_max: float
    precip_chance: float | None  # percent, 0-100


@dataclass
class Report:
    source: str  # "open-meteo" or "weatherkit"
    current: Current | None
    days: list[Day]
    alerts: list[str] | None  # None means this source has no alert data for the place
    raw: dict = field(default_factory=dict)


# WMO weather codes (Open-Meteo) -> the same names WeatherKit codes produce
WMO = {
    0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Cloudy",
    45: "Foggy", 48: "Foggy",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 56: "Freezing Drizzle", 57: "Freezing Drizzle",
    61: "Rain", 63: "Rain", 65: "Heavy Rain", 66: "Freezing Rain", 67: "Freezing Rain",
    71: "Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow",
    80: "Rain", 81: "Rain", 82: "Heavy Rain", 85: "Snow", 86: "Heavy Snow",
    95: "Thunderstorms", 96: "Thunderstorms", 99: "Thunderstorms",
}


def wmo_condition(code: int) -> str:
    return WMO.get(code, f"Unknown (WMO {code})")


def weatherkit_condition(code: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", code)
```

- [ ] **Step 8: 確認測試通過**

Run: `uv run pytest tests/test_model.py -v`
Expected: 4 passed

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .gitignore LICENSE tests/conftest.py tests/test_model.py src/weatherwise/scripts/ww_errors.py src/weatherwise/scripts/ww_http.py src/weatherwise/scripts/ww_model.py
git commit -m "feat: weatherwise scaffolding, errors, and data model"
```

---

### Task 2: 給模型讀的輸出

**Files:**
- Create: `src/weatherwise/scripts/ww_render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Place`、`Current`、`Day`、`Report`（Task 1）、`WwError`、`ACTIONS`
- Produces:
  - `ww_render.render_report(report: Report, place: Place, now: datetime, notice: str | None = None) -> str`。`now` 必須已經轉成地點的時區。
  - `ww_render.render_error(err: WwError) -> str`
  - `ww_render.ALERTS_UNSUPPORTED: str`

- [ ] **Step 1: 寫會失敗的測試 `tests/test_render.py`**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from conftest import NOW
from ww_errors import WwError
from ww_model import Current, Day, Place, Report
from ww_render import ALERTS_UNSUPPORTED, render_error, render_report

PLACE = Place("台北市", 25.033, 121.565, "Asia/Taipei")
LOCAL_NOW = NOW.astimezone(ZoneInfo("Asia/Taipei"))
CURRENT = Current("Partly Cloudy", 27.0, 29.1, 70, 12.3, 6.0)
DAYS = [Day("2026-10-07", "Cloudy", 21.9, 25.8, 0), Day("2026-10-08", "Rain", 23.2, 27.4, 80)]


def test_full_report_for_the_model():
    out = render_report(Report("open-meteo", CURRENT, DAYS, None), PLACE, LOCAL_NOW)
    assert out == "\n".join([
        "source: open-meteo",
        "location: 台北市 (25.033, 121.565) timezone=Asia/Taipei",
        "local_time: 2026-10-07T20:41 Wed",
        "current: Partly Cloudy, 27.0°C, feels 29.1°C, humidity 70%, wind 12 km/h, UV 6",
        "daily:",
        "  2026-10-07 Wed: Cloudy, 22–26°C, precipitation chance 0%",
        "  2026-10-08 Thu: Rain, 23–27°C, precipitation chance 80%",
        ALERTS_UNSUPPORTED,
    ])


def test_alerts_none_and_listed():
    none = render_report(Report("weatherkit", CURRENT, DAYS, []), PLACE, LOCAL_NOW)
    assert none.endswith("\nalerts: none")
    listed = render_report(Report("weatherkit", CURRENT, DAYS, ["Heavy Rain Advisory (CWA)"]), PLACE, LOCAL_NOW)
    assert listed.endswith("\nalerts:\n  - Heavy Rain Advisory (CWA)")


def test_unsupported_alerts_tell_the_model_not_to_say_none():
    assert "do not tell the user there are none" in ALERTS_UNSUPPORTED
    assert ALERTS_UNSUPPORTED.startswith("alerts: unsupported")


def test_notice_comes_first():
    out = render_report(Report("open-meteo", CURRENT, DAYS, None), PLACE, LOCAL_NOW, notice="weatherkit_auth_failed (HTTP 401)")
    assert out.splitlines()[0] == "notice: weatherkit_auth_failed (HTTP 401)"


def test_missing_values_say_unknown():
    current = Current("Clear", 20.0, 20.0, 50, 5, None)
    days = [Day("2026-10-07", "Clear", 18, 24, None)]
    out = render_report(Report("open-meteo", current, days, None), PLACE, LOCAL_NOW)
    assert "UV unknown" in out
    assert "precipitation chance unknown" in out


def test_local_time_uses_the_place_timezone():
    late_utc = datetime(2026, 10, 7, 23, 30, tzinfo=ZoneInfo("UTC"))
    out = render_report(Report("open-meteo", CURRENT, [], None), PLACE, late_utc.astimezone(ZoneInfo("Asia/Taipei")))
    assert "local_time: 2026-10-08T07:30 Thu" in out


def test_error_has_code_detail_and_action():
    assert render_error(WwError("place_not_found", "Atlantis")) == (
        "error: place_not_found (Atlantis)\n"
        "action: try another spelling, add --global for places outside Taiwan, or pass lat,lon"
    )
    assert render_error(WwError("no_default_location")).startswith("error: no_default_location\n")
```

- [ ] **Step 2: 確認測試失敗**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL，`No module named 'ww_render'`

- [ ] **Step 3: 寫 `ww_render.py`**

```python
"""Turns a Report into plain key: value lines for the model to read."""
from datetime import date, datetime

from ww_errors import ACTIONS, WwError
from ww_model import Place, Report

# Weekday names come from here, not strftime("%a"), which follows the machine's locale
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

ALERTS_UNSUPPORTED = (
    "alerts: unsupported (this source has no official alert data here; "
    "do not tell the user there are none)"
)


def _or_unknown(value: float | None, fmt: str, suffix: str = "") -> str:
    return "unknown" if value is None else f"{value:{fmt}}{suffix}"


def render_report(report: Report, place: Place, now: datetime, notice: str | None = None) -> str:
    lines = []
    if notice:
        lines.append(f"notice: {notice}")
    lines.append(f"source: {report.source}")
    lines.append(f"location: {place.name} ({place.lat:.3f}, {place.lon:.3f}) timezone={place.timezone}")
    lines.append(f"local_time: {now:%Y-%m-%dT%H:%M} {WEEKDAYS[now.weekday()]}")
    c = report.current
    if c:
        lines.append(
            f"current: {c.condition}, {c.temperature:.1f}°C, feels {c.feels_like:.1f}°C, "
            f"humidity {c.humidity:.0f}%, wind {c.wind_kmh:.0f} km/h, UV {_or_unknown(c.uv, '.0f')}"
        )
    if report.days:
        lines.append("daily:")
        for d in report.days:
            weekday = WEEKDAYS[date.fromisoformat(d.date).weekday()]
            lines.append(
                f"  {d.date} {weekday}: {d.condition}, {d.temp_min:.0f}–{d.temp_max:.0f}°C, "
                f"precipitation chance {_or_unknown(d.precip_chance, '.0f', '%')}"
            )
    if report.alerts is None:
        lines.append(ALERTS_UNSUPPORTED)
    elif not report.alerts:
        lines.append("alerts: none")
    else:
        lines.append("alerts:")
        lines += [f"  - {a}" for a in report.alerts]
    return "\n".join(lines)


def render_error(err: WwError) -> str:
    head = f"error: {err.code}" + (f" ({err.detail})" if err.detail else "")
    return f"{head}\naction: {ACTIONS[err.code]}"
```

- [ ] **Step 4: 確認測試通過**

Run: `uv run pytest tests/test_render.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/weatherwise/scripts/ww_render.py tests/test_render.py
git commit -m "feat: render weather and errors for the model"
```

---

### Task 3: 地點

**Files:**
- Create: `src/weatherwise/scripts/ww_places.py`
- Test: `tests/test_places.py`

**Interfaces:**
- Consumes: `Place`、`WwError`；`http(url, headers=None)`
- Produces:
  - `ww_places.resolve_place(query: str | None, cfg: dict, lang: str, global_search: bool, http) -> Place`（timezone 可能是 None）
  - `ww_places.geocode(query: str, lang: str, global_search: bool, http) -> Place`
  - `ww_places.with_timezone(place: Place, http) -> Place`（保證有 timezone）
  - `ww_places.NOMINATIM`、`ww_places.OPEN_METEO`（網址常數，測試用來當 FakeHttp 的前綴）

- [ ] **Step 1: 寫會失敗的測試 `tests/test_places.py`**

```python
import pytest

from conftest import TAIPEI_DEFAULT, FakeHttp
from ww_errors import WwError
from ww_model import Place
from ww_places import NOMINATIM, OPEN_METEO, resolve_place, with_timezone

TAICHUNG = [{"display_name": "臺中市, 40001, 臺灣", "lat": "24.1477", "lon": "120.6736"}]


def test_no_query_uses_the_default():
    place = resolve_place(None, {"default": TAIPEI_DEFAULT}, "zh-TW", False, FakeHttp({}))
    assert place == Place("台北市", 25.033, 121.565, "Asia/Taipei")


def test_no_query_and_no_default_asks_for_a_place():
    with pytest.raises(WwError) as e:
        resolve_place(None, {}, "zh-TW", False, FakeHttp({}))
    assert e.value.code == "no_default_location"


@pytest.mark.parametrize("query", ["24.15,120.67", " 24.15 , 120.67 "])
def test_coordinates_skip_geocoding(query):
    place = resolve_place(query, {}, "zh-TW", False, FakeHttp({}))
    assert (place.lat, place.lon, place.timezone) == (24.15, 120.67, None)


@pytest.mark.parametrize("query", ["200,10", "10,-181"])
def test_out_of_range_coordinates_are_rejected(query):
    with pytest.raises(WwError) as e:
        resolve_place(query, {}, "zh-TW", False, FakeHttp({}))
    assert e.value.code == "place_not_found"


def test_place_name_searches_taiwan_first_and_drops_postcodes():
    http = FakeHttp({NOMINATIM: TAICHUNG})
    place = resolve_place("台中", {}, "zh-TW", False, http)
    assert place == Place("臺中市, 臺灣", 24.1477, 120.6736)
    assert "countrycodes=tw" in http.calls[0][0]
    assert "accept-language=zh-TW" in http.calls[0][0]


def test_falls_back_to_a_global_search():
    http = FakeHttp({NOMINATIM: lambda url: [] if "countrycodes=tw" in url else TAICHUNG})
    resolve_place("台中", {}, "en", False, http)
    assert len(http.calls) == 2
    assert "countrycodes" not in http.calls[1][0]


def test_global_flag_skips_the_taiwan_search():
    http = FakeHttp({NOMINATIM: TAICHUNG})
    resolve_place("Tokyo", {}, "en", True, http)
    assert len(http.calls) == 1
    assert "countrycodes" not in http.calls[0][0]


def test_unknown_place():
    with pytest.raises(WwError) as e:
        resolve_place("Atlantis", {}, "en", False, FakeHttp({NOMINATIM: []}))
    assert (e.value.code, e.value.detail) == ("place_not_found", "Atlantis")


def test_timezone_is_looked_up_only_when_missing():
    http = FakeHttp({OPEN_METEO: {"timezone": "Asia/Tokyo"}})
    assert with_timezone(Place("x", 35.68, 139.69), http).timezone == "Asia/Tokyo"
    assert with_timezone(Place("y", 1, 2, "Asia/Taipei"), http).timezone == "Asia/Taipei"
    assert len(http.calls) == 1
```

- [ ] **Step 2: 確認測試失敗**

Run: `uv run pytest tests/test_places.py -v`
Expected: FAIL，`No module named 'ww_places'`

- [ ] **Step 3: 寫 `ww_places.py`**

```python
"""Turns what the user said ("台中", "Tokyo", "24.15,120.67", nothing) into a Place."""
import re
import urllib.parse
from dataclasses import replace

from ww_errors import WwError
from ww_model import Place

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
COORDS = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def resolve_place(query: str | None, cfg: dict, lang: str, global_search: bool, http) -> Place:
    if not query:
        d = cfg.get("default")
        if not d:
            raise WwError("no_default_location")
        return Place(d["name"], float(d["lat"]), float(d["lon"]), d.get("timezone"))
    m = COORDS.match(query)
    if m:
        lat, lon = float(m[1]), float(m[2])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise WwError("place_not_found", query.strip())
        return Place(f"{lat},{lon}", lat, lon)
    return geocode(query, lang, global_search, http)


def geocode(query: str, lang: str, global_search: bool, http) -> Place:
    base = {"q": query, "format": "json", "limit": 1, "accept-language": lang}
    # Taiwan first, then worldwide; --global goes straight to worldwide
    attempts = [base] if global_search else [{**base, "countrycodes": "tw"}, base]
    for params in attempts:
        res = http(f"{NOMINATIM}?{urllib.parse.urlencode(params)}")
        if res:
            r = res[0]
            parts = [p.strip() for p in r["display_name"].split(",")]
            name = ", ".join(p for p in parts if not p.isdigit())
            return Place(name, float(r["lat"]), float(r["lon"]))
    raise WwError("place_not_found", query)


def with_timezone(place: Place, http) -> Place:
    if place.timezone:
        return place
    q = urllib.parse.urlencode(
        {"latitude": place.lat, "longitude": place.lon, "timezone": "auto", "forecast_days": 1}
    )
    return replace(place, timezone=http(f"{OPEN_METEO}?{q}").get("timezone") or "UTC")
```

- [ ] **Step 4: 確認測試通過**

Run: `uv run pytest tests/test_places.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/weatherwise/scripts/ww_places.py tests/test_places.py
git commit -m "feat: resolve places from names, coordinates, or the default"
```

---

### Task 4: 資料來源

**Files:**
- Create: `src/weatherwise/scripts/ww_sources.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `Place`、`Current`、`Day`、`Report`、`wmo_condition`、`weatherkit_condition`、`HttpError`、`WwError`
- Produces:
  - `ww_sources.fetch_open_meteo(place: Place, days: int, http) -> Report`：HTTP 錯誤轉成 `WwError("service_error")`
  - `ww_sources.fetch_weatherkit(place: Place, days: int, lang: str, wk: dict, http, now_ts: int) -> Report`：**HTTP 錯誤原樣丟出 `HttpError`**（讓呼叫端決定要不要切換）；金鑰無效丟 `WwError("invalid_key_file")`
  - `ww_sources.parse_open_meteo(data: dict) -> Report`、`ww_sources.parse_weatherkit(data: dict, tz: str, days: int) -> Report`
  - `ww_sources.WEATHERKIT`（網址常數）

- [ ] **Step 1: 寫會失敗的測試 `tests/test_sources.py`**

```python
import jwt
import pytest

from conftest import OPEN_METEO, WEATHERKIT, FakeHttp
from ww_errors import WwError
from ww_http import HttpError
from ww_model import Current, Day, Place
from ww_sources import WEATHERKIT as WEATHERKIT_URL
from ww_sources import fetch_open_meteo, fetch_weatherkit, parse_open_meteo, parse_weatherkit

TAIPEI = Place("台北市", 25.033, 121.565, "Asia/Taipei")
EXPECTED_CURRENT = Current("Partly Cloudy", 27.0, 29.1, 70, 12.3, 6.0)
EXPECTED_DAYS = [Day("2026-10-07", "Cloudy", 21.9, 25.8, 0), Day("2026-10-08", "Rain", 23.2, 27.4, 80)]


def test_open_meteo_parses_current_and_daily():
    r = parse_open_meteo(OPEN_METEO)
    assert r.source == "open-meteo"
    assert r.current == EXPECTED_CURRENT
    assert r.days == EXPECTED_DAYS
    assert r.alerts is None


def test_open_meteo_nulls_become_none():
    data = {**OPEN_METEO, "current": {**OPEN_METEO["current"], "uv_index": None},
            "daily": {**OPEN_METEO["daily"], "precipitation_probability_max": [None, 80]}}
    r = parse_open_meteo(data)
    assert r.current.uv is None
    assert r.days[0].precip_chance is None


def test_open_meteo_request_uses_the_place_timezone_and_days():
    http = FakeHttp({"https://api.open-meteo.com/": OPEN_METEO})
    fetch_open_meteo(TAIPEI, 2, http)
    url = http.calls[0][0]
    assert "timezone=Asia%2FTaipei" in url and "forecast_days=2" in url


def test_open_meteo_http_error_is_a_service_error():
    with pytest.raises(WwError) as e:
        fetch_open_meteo(TAIPEI, 2, FakeHttp({"https://api.open-meteo.com/": HttpError(500)}))
    assert e.value.code == "service_error"


def test_weatherkit_matches_open_meteo_and_uses_local_dates():
    r = parse_weatherkit(WEATHERKIT, "Asia/Taipei", 10)
    assert r.source == "weatherkit"
    assert r.current.condition == "Partly Cloudy"
    assert round(r.current.humidity) == 70
    # 2026-10-06T16:00Z is already 2026-10-07 in Taipei
    assert [(d.date, d.condition, round(d.precip_chance)) for d in r.days] == [
        ("2026-10-07", "Cloudy", 0), ("2026-10-08", "Rain", 80)]
    assert r.alerts == []


def test_weatherkit_limits_days_and_lists_alerts():
    data = {**WEATHERKIT, "weatherAlerts": {"alerts": [{"description": "Heavy Rain Advisory", "source": "CWA"}]}}
    r = parse_weatherkit(data, "Asia/Taipei", 1)
    assert len(r.days) == 1
    assert r.alerts == ["Heavy Rain Advisory (CWA)"]


def test_weatherkit_without_alert_data_is_unsupported():
    data = {k: v for k, v in WEATHERKIT.items() if k != "weatherAlerts"}
    assert parse_weatherkit(data, "Asia/Taipei", 10).alerts is None


def test_weatherkit_request_is_signed(p8_key):
    wk = {"team_id": "TEAM123456", "key_id": "ABC123DEF4", "service_id": "dev.example.weather",
          "key_path": str(p8_key), "country_code": "TW"}
    http = FakeHttp({WEATHERKIT_URL: WEATHERKIT})
    fetch_weatherkit(TAIPEI, 3, "en", wk, http, 1_791_000_000)
    url, headers = http.calls[0]
    assert url.startswith(f"{WEATHERKIT_URL}/en/25.033/121.565?")
    token = headers["Authorization"].removeprefix("Bearer ")
    assert jwt.get_unverified_header(token)["kid"] == "ABC123DEF4"
    claims = jwt.decode(token, options={"verify_signature": False})
    assert (claims["iss"], claims["sub"]) == ("TEAM123456", "dev.example.weather")


def test_weatherkit_http_errors_are_left_to_the_caller(p8_key):
    wk = {"team_id": "T", "key_id": "K", "service_id": "S", "key_path": str(p8_key)}
    with pytest.raises(HttpError):
        fetch_weatherkit(TAIPEI, 3, "en", wk, FakeHttp({WEATHERKIT_URL: HttpError(401)}), 0)


def test_unreadable_key_is_an_invalid_key_file(tmp_path):
    bad = tmp_path / "AuthKey_X.p8"
    bad.write_text("not a key")
    wk = {"team_id": "T", "key_id": "K", "service_id": "S", "key_path": str(bad)}
    with pytest.raises(WwError) as e:
        fetch_weatherkit(TAIPEI, 3, "en", wk, FakeHttp({}), 0)
    assert e.value.code == "invalid_key_file"
```

- [ ] **Step 2: 確認測試失敗**

Run: `uv run pytest tests/test_sources.py -v`
Expected: FAIL，`No module named 'ww_sources'`

- [ ] **Step 3: 寫 `ww_sources.py`**

```python
"""Open-Meteo (free, default) and WeatherKit (optional) both become the same Report."""
import urllib.parse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ww_errors import WwError
from ww_http import HttpError
from ww_model import Current, Day, Place, Report, weatherkit_condition, wmo_condition

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
WEATHERKIT = "https://weatherkit.apple.com/api/v1/weather"


def fetch_open_meteo(place: Place, days: int, http) -> Report:
    q = urllib.parse.urlencode({
        "latitude": place.lat, "longitude": place.lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code,uv_index",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": place.timezone, "forecast_days": days,
    })
    try:
        return parse_open_meteo(http(f"{OPEN_METEO}?{q}"))
    except HttpError as e:
        raise WwError("service_error", f"open-meteo HTTP {e.status}") from None


def parse_open_meteo(data: dict) -> Report:
    c = data.get("current")
    current = Current(
        wmo_condition(c["weather_code"]), c["temperature_2m"], c["apparent_temperature"],
        c["relative_humidity_2m"], c["wind_speed_10m"], c.get("uv_index"),
    ) if c else None
    d = data.get("daily") or {}
    days = [
        Day(t, wmo_condition(code), lo, hi, chance)
        for t, code, hi, lo, chance in zip(
            d.get("time", []), d.get("weather_code", []), d.get("temperature_2m_max", []),
            d.get("temperature_2m_min", []), d.get("precipitation_probability_max", []),
        )
    ]
    return Report("open-meteo", current, days, None, data)


def make_token(wk: dict, now_ts: int) -> str:
    import jwt

    try:
        key = Path(wk["key_path"]).expanduser().read_text()
        return jwt.encode(
            {"iss": wk["team_id"], "iat": now_ts, "exp": now_ts + 3600, "sub": wk["service_id"]},
            key, algorithm="ES256",
            headers={"kid": wk["key_id"], "id": f"{wk['team_id']}.{wk['service_id']}"},
        )
    except (OSError, ValueError, jwt.PyJWTError) as e:
        # Name the problem without echoing anything read from the key file
        raise WwError("invalid_key_file", type(e).__name__) from None


def fetch_weatherkit(place: Place, days: int, lang: str, wk: dict, http, now_ts: int) -> Report:
    token = make_token(wk, now_ts)
    q = urllib.parse.urlencode({
        "dataSets": "currentWeather,forecastDaily,weatherAlerts",
        "timezone": place.timezone, "countryCode": wk.get("country_code", "TW"),
    })
    data = http(f"{WEATHERKIT}/{lang}/{place.lat}/{place.lon}?{q}", {"Authorization": f"Bearer {token}"})
    return parse_weatherkit(data, place.timezone, days)


def parse_weatherkit(data: dict, tz: str, days: int) -> Report:
    c = data.get("currentWeather")
    current = Current(
        weatherkit_condition(c["conditionCode"]), c["temperature"], c["temperatureApparent"],
        c["humidity"] * 100, c["windSpeed"], c.get("uvIndex"),
    ) if c else None
    zone = ZoneInfo(tz)
    out = []
    for d in (data.get("forecastDaily") or {}).get("days", [])[:days]:
        start = datetime.fromisoformat(d["forecastStart"].replace("Z", "+00:00")).astimezone(zone)
        chance = d.get("precipitationChance")
        out.append(Day(
            start.date().isoformat(), weatherkit_condition(d["conditionCode"]),
            d["temperatureMin"], d["temperatureMax"], None if chance is None else chance * 100,
        ))
    alerts = None
    if "weatherAlerts" in data:
        alerts = [
            f"{a.get('description', '')} ({a.get('source', '')})"
            for a in (data["weatherAlerts"] or {}).get("alerts", [])
        ]
    return Report("weatherkit", current, out, alerts, data)
```

- [ ] **Step 4: 確認測試通過**

Run: `uv run pytest tests/test_sources.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/weatherwise/scripts/ww_sources.py tests/test_sources.py
git commit -m "feat: Open-Meteo and WeatherKit sources"
```

---

### Task 5: 設定檔

**Files:**
- Create: `src/weatherwise/scripts/ww_config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `WwError`
- Produces:
  - `ww_config.config_dir() -> Path`（讀 `WEATHERWISE_CONFIG_DIR`，預設 `~/.config/weatherwise`）
  - `ww_config.load_config(d: Path) -> dict`（沒有檔案回 `{}`；JSON 壞掉丟 `config_invalid`）
  - `ww_config.save_config(d: Path, cfg: dict) -> None`（一次寫完、權限 600）
  - `ww_config.resolve_lang(cli: str | None, cfg: dict) -> str`
  - `ww_config.weatherkit_settings(cfg: dict) -> dict | None`
  - `ww_config.mask(value: str) -> str`
  - `ww_config.KEY_FILE_NAME`（`AuthKey_<KeyID>.p8` 的 regex）

- [ ] **Step 1: 寫會失敗的測試 `tests/test_config.py`**

```python
import json
import os
import stat

import pytest

import ww_config
from ww_config import KEY_FILE_NAME, load_config, mask, resolve_lang, save_config, weatherkit_settings
from ww_errors import WwError


def test_config_dir_follows_the_env(config_dir):
    assert ww_config.config_dir() == config_dir


def test_missing_file_is_an_empty_config(config_dir):
    assert load_config(config_dir) == {}


def test_broken_json_is_config_invalid(config_dir):
    config_dir.mkdir()
    (config_dir / "config.json").write_text("{not json")
    with pytest.raises(WwError) as e:
        load_config(config_dir)
    assert e.value.code == "config_invalid"


def test_save_round_trips_with_private_permissions(config_dir):
    save_config(config_dir, {"lang": "en"})
    assert load_config(config_dir) == {"lang": "en"}
    assert stat.S_IMODE(os.stat(config_dir / "config.json").st_mode) == 0o600


def test_failed_save_keeps_the_old_file(config_dir, monkeypatch):
    save_config(config_dir, {"lang": "en"})

    def boom(*_):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        save_config(config_dir, {"lang": "ja"})
    assert json.loads((config_dir / "config.json").read_text()) == {"lang": "en"}
    assert [p.name for p in config_dir.iterdir()] == ["config.json"]


def test_lang_priority_and_validation():
    assert resolve_lang(None, {}) == "zh-TW"
    assert resolve_lang(None, {"lang": "ja"}) == "ja"
    assert resolve_lang("en", {"lang": "ja"}) == "en"
    with pytest.raises(WwError) as e:
        resolve_lang("not a lang!", {})
    assert e.value.code == "unsupported_lang"


def test_weatherkit_settings(tmp_path):
    key = tmp_path / "AuthKey_K.p8"
    key.write_text("x")
    full = {"team_id": "T", "key_id": "K", "service_id": "S", "key_path": str(key)}
    assert weatherkit_settings({}) is None
    assert weatherkit_settings({"weatherkit": full}) == full
    with pytest.raises(WwError) as e:
        weatherkit_settings({"weatherkit": {"team_id": "T"}})
    assert (e.value.code, e.value.detail) == ("weatherkit_config_incomplete", "key_id, service_id, key_path")
    with pytest.raises(WwError) as e:
        weatherkit_settings({"weatherkit": {**full, "key_path": str(tmp_path / "gone.p8")}})
    assert e.value.code == "weatherkit_key_missing"


def test_mask_keeps_only_the_ends():
    assert mask("TEAMID1234") == "TE…34"
    assert mask("abc") == "…"


def test_key_file_name():
    assert KEY_FILE_NAME.match("AuthKey_ABC123DEF4.p8")[1] == "ABC123DEF4"
    assert KEY_FILE_NAME.match("mykey.p8") is None
```

- [ ] **Step 2: 確認測試失敗**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL，`No module named 'ww_config'`

- [ ] **Step 3: 寫 `ww_config.py`**

```python
"""~/.config/weatherwise/config.json: read, validate, and write it safely."""
import json
import os
import re
import tempfile
from pathlib import Path

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
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise WwError("config_invalid", str(path)) from None


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
```

- [ ] **Step 4: 確認測試通過**

Run: `uv run pytest tests/test_config.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/weatherwise/scripts/ww_config.py tests/test_config.py
git commit -m "feat: config file loading, validation, and atomic saves"
```

---

### Task 6: 查天氣的指令

**Files:**
- Create: `src/weatherwise/scripts/weatherwise.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1–5 的全部
- Produces:
  - `weatherwise.main(argv: list[str] | None = None, *, http=get_json, now: datetime | None = None) -> int`：印出結果，回傳結束碼（0 或 1）
  - `weatherwise.Parser`：參數錯誤時丟 `WwError("bad_arguments")`，不會直接結束程式
  - `weatherwise.run_config(argv, http, now) -> str`：Task 7 才實作；這個 task 先放一個會丟 `bad_arguments` 的版本
  - `weatherwise.VERSION_LINE`

- [ ] **Step 1: 寫會失敗的測試 `tests/test_cli.py`**

```python
import json
import shutil

from conftest import NOW, OPEN_METEO, TAIPEI_DEFAULT, WEATHERKIT, FakeHttp
from ww_config import save_config
from ww_http import HttpError
import weatherwise

OM = "https://api.open-meteo.com/"
WK = "https://weatherkit.apple.com/"


def run(argv, http, capsys):
    code = weatherwise.main(argv, http=http, now=NOW)
    return code, capsys.readouterr().out.strip()


def use_weatherkit(config_dir, p8_key):
    config_dir.mkdir(parents=True, exist_ok=True)
    key = config_dir / p8_key.name
    shutil.copy(p8_key, key)
    save_config(config_dir, {"default": TAIPEI_DEFAULT, "weatherkit": {
        "team_id": "TEAM123456", "key_id": "ABC123DEF4", "service_id": "dev.example.weather",
        "key_path": str(key)}})


def test_free_mode_with_default_place(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    code, out = run([], FakeHttp({OM: OPEN_METEO}), capsys)
    assert code == 0
    assert out.splitlines()[:3] == [
        "source: open-meteo",
        "location: 台北市 (25.033, 121.565) timezone=Asia/Taipei",
        "local_time: 2026-10-07T20:41 Wed",
    ]
    assert out.splitlines()[-1].startswith("alerts: unsupported")


def test_no_config_and_no_place_asks_where(config_dir, capsys):
    code, out = run([], FakeHttp({}), capsys)
    assert code == 1
    assert out.startswith("error: no_default_location\naction: ask the user where they are")


def test_weatherkit_mode(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run([], FakeHttp({WK: WEATHERKIT}), capsys)
    assert code == 0
    assert out.splitlines()[0] == "source: weatherkit"
    assert out.splitlines()[-1] == "alerts: none"


def test_both_sources_give_the_same_weather_lines(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    _, free = run(["--days", "2"], FakeHttp({OM: OPEN_METEO}), capsys)
    use_weatherkit(config_dir, p8_key)
    _, paid = run(["--days", "2"], FakeHttp({WK: WEATHERKIT}), capsys)
    assert free.splitlines()[1:-1] == paid.splitlines()[1:-1]


def test_auth_failure_falls_back_with_a_notice(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run([], FakeHttp({WK: HttpError(401), OM: OPEN_METEO}), capsys)
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("notice: weatherkit_auth_failed (HTTP 401), fell back to open-meteo;")
    assert "membership may have expired" in lines[0]
    assert lines[1] == "source: open-meteo"


def test_other_weatherkit_errors_do_not_fall_back(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run([], FakeHttp({WK: HttpError(500), OM: OPEN_METEO}), capsys)
    assert code == 1
    assert out.startswith("error: service_error")


def test_incomplete_weatherkit_config_is_an_error_not_a_fallback(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT, "weatherkit": {"team_id": "T"}})
    code, out = run([], FakeHttp({OM: OPEN_METEO}), capsys)
    assert code == 1
    assert out.startswith("error: weatherkit_config_incomplete")


def test_days_are_clamped(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    for given, sent in [("0", "forecast_days=1"), ("20", "forecast_days=10")]:
        http = FakeHttp({OM: OPEN_METEO})
        run(["--days", given], http, capsys)
        assert sent in http.calls[-1][0]


def test_json_wraps_the_raw_data(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    _, out = run(["--json"], FakeHttp({OM: OPEN_METEO}), capsys)
    data = json.loads(out)
    assert data["source"] == "open-meteo"
    assert data["data"]["daily"] == OPEN_METEO["daily"]
    assert "notice" not in data


def test_version(capsys):
    _, out = run(["--version"], FakeHttp({}), capsys)
    assert out == "weatherwise 1.0.0 · by SmallYuan · https://github.com/SmallYuanSY/skills"


def test_bad_arguments_are_reported_for_the_model(config_dir, capsys):
    code, out = run(["--days", "many"], FakeHttp({}), capsys)
    assert code == 1
    assert out.startswith("error: bad_arguments")


def test_lang_flag_reaches_the_geocoder(config_dir, capsys):
    http = FakeHttp({"https://nominatim.openstreetmap.org/": [{"display_name": "Tokyo, Japan", "lat": "35.68", "lon": "139.69"}],
                     OM: OPEN_METEO})
    run(["Tokyo", "--global", "--lang", "en"], http, capsys)
    assert "accept-language=en" in http.calls[0][0]
```

- [ ] **Step 2: 確認測試失敗**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL，`No module named 'weatherwise'`

- [ ] **Step 3: 寫 `weatherwise.py`**

```python
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
```

- [ ] **Step 4: 確認測試通過**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 12 passed

- [ ] **Step 5: 跑全部測試，再實際查一次**

Run: `uv run pytest`
Expected: 全部通過

Run: `WEATHERWISE_CONFIG_DIR=$(mktemp -d) uv run src/weatherwise/scripts/weatherwise.py 25.033,121.565`
Expected: 第一行 `source: open-meteo`、有 `local_time`、最後一行 `alerts: unsupported (...)`。這一步會打真的網路。

- [ ] **Step 6: Commit**

```bash
git add src/weatherwise/scripts/weatherwise.py tests/test_cli.py
git commit -m "feat: weatherwise command with WeatherKit fallback"
```

---

### Task 7: 設定指令

**Files:**
- Create: `src/weatherwise/scripts/ww_setup.py`
- Modify: `src/weatherwise/scripts/weatherwise.py`（把 `run_config` 換成真正的實作）
- Test: `tests/test_setup.py`

**Interfaces:**
- Consumes: `config_dir`、`load_config`、`save_config`、`resolve_lang`、`weatherkit_settings`、`mask`、`KEY_FILE_NAME`、`resolve_place`、`with_timezone`、`fetch_weatherkit`、`HttpError`、`WwError`、`Place`
- Produces:
  - `ww_setup.show(cfg: dict, d: Path) -> str`
  - `ww_setup.set_default(query: str, global_search: bool, cfg: dict, d: Path, lang: str, http) -> str`
  - `ww_setup.set_lang(lang: str, cfg: dict, d: Path) -> str`
  - `ww_setup.set_weatherkit(team_id, service_id, key_file, key_id, country_code, cfg, d, lang, http, now_ts) -> str`
  - `ww_setup.remove_weatherkit(cfg: dict, d: Path) -> str`

- [ ] **Step 1: 寫會失敗的測試 `tests/test_setup.py`**

```python
import os
import stat

from conftest import NOW, TAIPEI_DEFAULT, WEATHERKIT, FakeHttp
from ww_config import load_config, save_config
from ww_http import HttpError
import weatherwise

NOMINATIM = "https://nominatim.openstreetmap.org/"
OM = "https://api.open-meteo.com/"
WK = "https://weatherkit.apple.com/"
TAICHUNG = [{"display_name": "臺中市, 臺灣", "lat": "24.1477", "lon": "120.6736"}]


def run(argv, http, capsys):
    code = weatherwise.main(["config", *argv], http=http, now=NOW)
    return code, capsys.readouterr().out.strip()


def wk_args(p8_key, *extra):
    return ["weatherkit", "--team-id", "TEAM123456", "--service-id", "dev.example.weather",
            "--key-file", str(p8_key), *extra]


def test_show_with_nothing_set(config_dir, capsys):
    code, out = run(["show"], FakeHttp({}), capsys)
    assert code == 0
    assert "default: none" in out
    assert "lang: zh-TW" in out
    assert "source: open-meteo" in out


def test_set_default_saves_and_asks_to_confirm(config_dir, capsys):
    code, out = run(["set-default", "台中"], FakeHttp({NOMINATIM: TAICHUNG, OM: {"timezone": "Asia/Taipei"}}), capsys)
    assert code == 0
    assert out.splitlines()[0] == "saved: default = 臺中市, 臺灣 (24.148, 120.674) timezone=Asia/Taipei"
    assert out.splitlines()[1].startswith("action: confirm with the user")
    assert load_config(config_dir)["default"] == {
        "name": "臺中市, 臺灣", "lat": 24.1477, "lon": 120.6736, "timezone": "Asia/Taipei"}


def test_set_default_unknown_place_writes_nothing(config_dir, capsys):
    code, out = run(["set-default", "Atlantis"], FakeHttp({NOMINATIM: []}), capsys)
    assert code == 1
    assert out.startswith("error: place_not_found")
    assert not (config_dir / "config.json").exists()


def test_set_lang(config_dir, capsys):
    assert run(["set-lang", "en"], FakeHttp({}), capsys) == (0, "saved: lang = en")
    assert load_config(config_dir)["lang"] == "en"
    code, out = run(["set-lang", "bad lang"], FakeHttp({}), capsys)
    assert code == 1 and out.startswith("error: unsupported_lang")


def test_weatherkit_copies_the_key_and_tests_it(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    http = FakeHttp({WK: WEATHERKIT})
    code, out = run(wk_args(p8_key), http, capsys)
    assert code == 0
    assert out == "saved: weatherkit (test request succeeded)\nsource: weatherkit"
    copy = config_dir / "AuthKey_ABC123DEF4.p8"
    assert copy.read_bytes() == p8_key.read_bytes()
    assert stat.S_IMODE(os.stat(copy).st_mode) == 0o600
    wk = load_config(config_dir)["weatherkit"]
    assert wk == {"team_id": "TEAM123456", "key_id": "ABC123DEF4", "service_id": "dev.example.weather",
                  "key_path": str(copy), "country_code": "TW"}
    assert len(http.calls) == 1  # exactly one test request


def test_weatherkit_rejected_key_saves_nothing(config_dir, p8_key, capsys):
    code, out = run(wk_args(p8_key), FakeHttp({OM: {"timezone": "Asia/Taipei"}, WK: HttpError(403)}), capsys)
    assert code == 1
    assert out.startswith("error: weatherkit_auth_failed (HTTP 403)")
    assert not (config_dir / "config.json").exists()
    assert not (config_dir / "AuthKey_ABC123DEF4.p8").exists()


def test_weatherkit_needs_a_key_id_when_the_file_was_renamed(config_dir, p8_key, capsys):
    renamed = p8_key.with_name("mykey.p8")
    p8_key.rename(renamed)
    code, out = run(wk_args(renamed), FakeHttp({}), capsys)
    assert code == 1
    assert out.startswith("error: weatherkit_config_incomplete (key_id")


def test_weatherkit_missing_file(config_dir, tmp_path, capsys):
    code, out = run(["weatherkit", "--team-id", "T", "--service-id", "S", "--key-file", str(tmp_path / "nope.p8")],
                    FakeHttp({}), capsys)
    assert code == 1 and out.startswith("error: invalid_key_file")


def test_show_masks_ids_and_never_prints_the_key(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    run(wk_args(p8_key), FakeHttp({WK: WEATHERKIT}), capsys)
    _, out = run(["show"], FakeHttp({}), capsys)
    assert "source: weatherkit" in out
    assert "TE…56" in out and "TEAM123456" not in out
    assert "PRIVATE KEY" not in out


def test_remove_weatherkit(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    run(wk_args(p8_key), FakeHttp({WK: WEATHERKIT}), capsys)
    code, out = run(["weatherkit", "--remove"], FakeHttp({}), capsys)
    assert (code, out) == (0, "removed: weatherkit\nsource: open-meteo")
    assert "weatherkit" not in load_config(config_dir)
    assert not (config_dir / "AuthKey_ABC123DEF4.p8").exists()
    assert p8_key.exists()  # the user's own download is never touched
```

- [ ] **Step 2: 確認測試失敗**

Run: `uv run pytest tests/test_setup.py -v`
Expected: FAIL，輸出是 `error: bad_arguments (config commands are not available yet)`

- [ ] **Step 3: 寫 `ww_setup.py`**

```python
"""The config commands an agent runs on the user's behalf. Every write is validated first."""
import os
import shutil
from pathlib import Path

from ww_config import KEY_FILE_NAME, mask, resolve_lang, save_config, weatherkit_settings
from ww_errors import WwError
from ww_http import HttpError
from ww_model import Place
from ww_places import resolve_place, with_timezone
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
    cfg["default"] = {"name": place.name, "lat": place.lat, "lon": place.lon, "timezone": place.timezone}
    save_config(d, cfg)
    return (
        f"saved: default = {place.name} ({place.lat:.3f}, {place.lon:.3f}) timezone={place.timezone}\n"
        "action: confirm with the user that this is the right place"
    )


def set_lang(lang: str, cfg: dict, d: Path) -> str:
    cfg["lang"] = resolve_lang(lang, {})
    save_config(d, cfg)
    return f"saved: lang = {cfg['lang']}"


def set_weatherkit(team_id, service_id, key_file, key_id, country_code, cfg, d, lang, http, now_ts) -> str:
    src = Path(key_file).expanduser()
    if not src.is_file():
        raise WwError("invalid_key_file", str(src))
    m = KEY_FILE_NAME.match(src.name)
    key_id = key_id or (m[1] if m else None)
    missing = [n for n, v in (("team_id", team_id), ("key_id", key_id), ("service_id", service_id)) if not v]
    if missing:
        hint = " (file is not named AuthKey_<KeyID>.p8; pass --key-id)" if "key_id" in missing else ""
        raise WwError("weatherkit_config_incomplete", ", ".join(missing) + hint)

    wk = {"team_id": team_id, "key_id": key_id, "service_id": service_id,
          "key_path": str(src), "country_code": country_code}
    df = cfg.get("default")
    place = Place(df["name"], df["lat"], df["lon"], df.get("timezone")) if df else TEST_PLACE
    place = with_timezone(place, http)
    try:  # one real request before anything is written
        fetch_weatherkit(place, 1, lang, wk, http, now_ts)
    except HttpError as e:
        if e.status in (401, 403):
            raise WwError("weatherkit_auth_failed", f"HTTP {e.status}") from None
        raise WwError("service_error", f"weatherkit HTTP {e.status}") from None

    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"AuthKey_{key_id}.p8"
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    os.chmod(dest, 0o600)
    cfg["weatherkit"] = {**wk, "key_path": str(dest)}
    save_config(d, cfg)
    return "saved: weatherkit (test request succeeded)\nsource: weatherkit"


def remove_weatherkit(cfg: dict, d: Path) -> str:
    wk = cfg.pop("weatherkit", None) or {}
    key = Path(wk.get("key_path", "")).expanduser()
    if wk.get("key_path") and key.parent.resolve() == d.resolve():  # only our own copy
        key.unlink(missing_ok=True)
    save_config(d, cfg)
    return "removed: weatherkit\nsource: open-meteo"
```

- [ ] **Step 4: 把 `weatherwise.py` 的 `run_config` 換成真正的實作**

在 import 區加上：

```python
from ww_setup import remove_weatherkit, set_default, set_lang, set_weatherkit, show  # noqa: E402
```

把 Task 6 的 `run_config` 整個換成：

```python
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
    wk.add_argument("--country-code", default="TW")
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
    return set_weatherkit(a.team_id, a.service_id, a.key_file, a.key_id, a.country_code,
                          cfg, d, resolve_lang(None, cfg), http, now_ts)
```

並把 docstring 的第二行用法保持不變（已經列出 config 子指令）。

- [ ] **Step 5: 確認測試通過**

Run: `uv run pytest tests/test_setup.py -v`
Expected: 10 passed

Run: `uv run pytest`
Expected: 全部通過

- [ ] **Step 6: Commit**

```bash
git add src/weatherwise/scripts/ww_setup.py src/weatherwise/scripts/weatherwise.py tests/test_setup.py
git commit -m "feat: config commands for agents to set weatherwise up"
```

---

### Task 8: SKILL.md、WeatherKit 教學、轉譯器

**Files:**
- Create: `src/weatherwise/SKILL.md`、`src/weatherwise/references/weatherkit-setup.md`、`tools/translate.py`
- Create（產生）: `dist/hermes/weatherwise/**`、`dist/claude/weatherwise/**`
- Test: `tests/test_translate.py`

**Interfaces:**
- Produces:
  - `translate.TARGETS: dict[str, str]`、`translate.PLACEHOLDER = "{{SKILL_DIR}}"`
  - `translate.build(src: Path, out: Path) -> None`：發生錯誤時不動到 `out`
  - `translate.check(src: Path, out: Path) -> list[str]`：回傳不同步的相對路徑
  - `translate.TranslateError`
  - `translate.main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: 寫會失敗的測試 `tests/test_translate.py`**

```python
import pytest

import translate
from translate import PLACEHOLDER, TranslateError, build, check

ROOT = translate.ROOT


@pytest.fixture
def src(tmp_path):
    s = tmp_path / "src" / "demo"
    (s / "scripts").mkdir(parents=True)
    (s / "SKILL.md").write_text(f"run {PLACEHOLDER}/scripts/x.py\n")
    (s / "scripts" / "x.py").write_text(f"print('{PLACEHOLDER}')\n")
    (s / "scripts" / "__pycache__").mkdir()
    (s / "scripts" / "__pycache__" / "x.cpython-314.pyc").write_bytes(b"\0")
    return tmp_path / "src"


def test_each_target_gets_its_own_skill_dir(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    assert (out / "hermes/demo/SKILL.md").read_text() == "run ${HERMES_SKILL_DIR}/scripts/x.py\n"
    assert (out / "claude/demo/SKILL.md").read_text() == "run ${CLAUDE_SKILL_DIR}/scripts/x.py\n"


def test_only_markdown_is_rewritten_and_caches_are_skipped(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    assert (out / "claude/demo/scripts/x.py").read_text() == f"print('{PLACEHOLDER}')\n"
    assert not (out / "claude/demo/scripts/__pycache__").exists()


def test_rebuild_removes_deleted_files(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    (src / "demo/scripts/x.py").unlink()
    build(src, out)
    assert not (out / "hermes/demo/scripts/x.py").exists()


def test_unknown_placeholder_fails_without_touching_dist(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    (src / "demo/SKILL.md").write_text("{{SKILL_DIRR}}\n")
    with pytest.raises(TranslateError, match="SKILL_DIRR"):
        build(src, out)
    assert "HERMES_SKILL_DIR" in (out / "hermes/demo/SKILL.md").read_text()


def test_check_reports_drift(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    assert check(src, out) == []
    (src / "demo/SKILL.md").write_text("changed\n")
    assert check(src, out) == ["claude/demo/SKILL.md", "hermes/demo/SKILL.md"]


def test_repo_dist_is_up_to_date():
    assert check(ROOT / "src", ROOT / "dist") == []
```

- [ ] **Step 2: 確認測試失敗**

Run: `uv run pytest tests/test_translate.py -v`
Expected: FAIL，`No module named 'translate'`

- [ ] **Step 3: 寫 `tools/translate.py`**

```python
#!/usr/bin/env python3
"""Skill translator: one source skill in src/, one installable copy per agent in dist/.

  uv run tools/translate.py          rebuild dist/ from src/
  uv run tools/translate.py --check  exit 1 if dist/ is out of date
"""
import argparse
import filecmp
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "{{SKILL_DIR}}"
LEFTOVER = re.compile(r"\{\{[A-Z_]+\}\}")
# Add a row here to support another agent
TARGETS = {
    "hermes": "${HERMES_SKILL_DIR}",
    "claude": "${CLAUDE_SKILL_DIR}",
}


class TranslateError(Exception):
    pass


def _skip(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix == ".pyc" or path.name == ".DS_Store"


def _render(src: Path, out: Path) -> None:
    for target, skill_dir in TARGETS.items():
        for f in sorted(src.rglob("*")):
            rel = f.relative_to(src)
            if f.is_dir() or _skip(rel):
                continue
            dest = out / target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if f.suffix == ".md":
                text = f.read_text(encoding="utf-8").replace(PLACEHOLDER, skill_dir)
                if m := LEFTOVER.search(text):
                    raise TranslateError(f"{rel}: unknown placeholder {m.group(0)}")
                dest.write_text(text, encoding="utf-8")
            else:
                shutil.copy2(f, dest)


def build(src: Path, out: Path) -> None:
    """Render everything into a temp dir first, so a mistake never leaves dist/ half-written."""
    with tempfile.TemporaryDirectory() as tmp:
        _render(src, Path(tmp))
        for target in TARGETS:
            shutil.rmtree(out / target, ignore_errors=True)
            built = Path(tmp) / target
            if built.exists():
                shutil.copytree(built, out / target)


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not _skip(p)} if root.exists() else set()


def check(src: Path, out: Path) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        _render(src, fresh)
        problems = []
        for target in TARGETS:
            a, b = _files(fresh / target), _files(out / target)
            for rel in sorted(a | b):
                pa, pb = fresh / target / rel, out / target / rel
                if rel not in a or rel not in b or not filecmp.cmp(pa, pb, shallow=False):
                    problems.append(f"{target}/{rel}")
        return sorted(problems)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build per-agent copies of the skills in src/.")
    p.add_argument("--check", action="store_true", help="exit 1 if dist/ is out of date")
    a = p.parse_args(argv)
    src, out = ROOT / "src", ROOT / "dist"
    try:
        if a.check:
            problems = check(src, out)
            for rel in problems:
                print(f"out of date: dist/{rel}")
            if problems:
                print("run: uv run tools/translate.py")
                return 1
            print("dist/ is up to date")
            return 0
        build(src, out)
        print(f"built dist/ for: {', '.join(TARGETS)}")
        return 0
    except TranslateError as e:
        print(f"error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 寫 `src/weatherwise/SKILL.md`**

````markdown
---
name: weatherwise
description: Current weather, multi-day forecast, and rain chance for the user's location or any place, plus official alerts when WeatherKit is set up. Use when the user asks about weather, temperature, rain, an umbrella, typhoons, or what to wear. 天氣、氣溫、會不會下雨、要不要帶傘、颱風、明天／這週天氣、出門前看天氣。
version: 1.0.0
author: SmallYuan
license: MIT
homepage: https://github.com/SmallYuanSY/skills
platforms: [macos, linux]
metadata:
  hermes:
    tags: [weather, 天氣, forecast, rain, typhoon, WeatherKit, Open-Meteo]
prerequisites:
  commands: [uv]
---

# weatherwise

Run the command, then answer from its output. The output is written for you, not for the user: read it and answer in the user's own language.

## Commands

```bash
uv run {{SKILL_DIR}}/scripts/weatherwise.py                 # default location
uv run {{SKILL_DIR}}/scripts/weatherwise.py 板橋             # a place in Taiwan (searched first)
uv run {{SKILL_DIR}}/scripts/weatherwise.py Tokyo --global  # a place outside Taiwan
uv run {{SKILL_DIR}}/scripts/weatherwise.py 24.15,120.67    # coordinates
uv run {{SKILL_DIR}}/scripts/weatherwise.py --days 7        # forecast days, 1-10 (default 3)
```

## Reading the output

- `local_time` is the current time at that place. Use it to work out "today", "tomorrow", and weekdays.
- Check that `location` is the place the user meant. If not, retry with a fuller name, `--global`, or coordinates.
- `alerts: none`: there is alert data and no alerts are active.
- `alerts: unsupported`: there is no alert data. Never tell the user there are no alerts. If they ask about typhoons or heavy rain, or it looks like typhoon season, tell them to check their local weather agency.
- `alerts:` followed by items: always mention every one.
- `notice:` always pass it on to the user.
- `error:` do what the `action:` line says.
- Answer with the numbers: conditions, temperature, and rain chance. Don't mention the data source.

## Settings

Change settings only with these commands. Never edit the config file by hand.

```bash
uv run {{SKILL_DIR}}/scripts/weatherwise.py config show
uv run {{SKILL_DIR}}/scripts/weatherwise.py config set-default <place> [--global]
uv run {{SKILL_DIR}}/scripts/weatherwise.py config set-lang <lang>
uv run {{SKILL_DIR}}/scripts/weatherwise.py config weatherkit --team-id <id> --service-id <id> --key-file <path to .p8>
uv run {{SKILL_DIR}}/scripts/weatherwise.py config weatherkit --remove
```

- After `set-default`, tell the user the place that was saved and ask them to confirm it.
- `lang` only sets the language of place names and alert text (a BCP 47 tag such as `zh-TW`, `en`, `ja`). It does not change the language you answer in.
- WeatherKit is optional and needs a paid Apple Developer membership. If the user wants it, walk them through `{{SKILL_DIR}}/references/weatherkit-setup.md` one step at a time. Only the user can do the steps on Apple's website. The Key ID is read from the key's file name.
- If the user would rather not paste their IDs into the chat, give them the full command to run in their own terminal (in Claude Code, they can type it after `!`).
- Never open, print, or paste the contents of a `.p8` key file. Only ever handle its path.
````

- [ ] **Step 5: 寫 `src/weatherwise/references/weatherkit-setup.md`**

````markdown
# Setting up Apple WeatherKit (optional)

weatherwise works without this. WeatherKit adds Apple Weather data and official weather alerts. It needs a paid Apple Developer Program membership (US$99/year), which includes 500,000 WeatherKit calls a month.

Guide the user one step at a time. Steps 1–4 happen on Apple's website and only the user can do them.

## 1. Join the Apple Developer Program

https://developer.apple.com/programs/ → Enroll. Approval can take a day or two.

## 2. Register a Services ID

Certificates, Identifiers & Profiles → Identifiers → **+** → **Services IDs**. Use a reverse-domain name such as `com.example.weatherwise`. This is the **Service ID**.

## 3. Create a key with WeatherKit enabled

Certificates, Identifiers & Profiles → Keys → **+** → give it a name → tick **WeatherKit** → Continue → Register → **Download**.

The file is named `AuthKey_<KeyID>.p8`. It can only be downloaded once, so the user should keep it somewhere safe. The Key ID is in the file name; there's no need to look it up.

## 4. Find the Team ID

Top right of the developer website, or Membership details. It's 10 characters.

## 5. Save the settings

```bash
uv run {{SKILL_DIR}}/scripts/weatherwise.py config weatherkit --team-id <TEAM_ID> --service-id <SERVICE_ID> --key-file <path to AuthKey_XXXX.p8>
```

This makes one real request first and only saves if it works. It copies the key into `~/.config/weatherwise/` with permissions `600`, so the downloaded file can be moved or deleted afterwards.

The IDs are identifiers, not secrets (they appear in every WeatherKit request), but they will stay in the chat history. A user who prefers not to share them can run this command in their own terminal.

## 6. Check

```bash
uv run {{SKILL_DIR}}/scripts/weatherwise.py config show
```

It should say `source: weatherkit`.

## Troubleshooting

- `weatherkit_auth_failed (HTTP 401)`: a wrong Team ID, Service ID, or Key ID, or the key was revoked.
- `weatherkit_auth_failed (HTTP 403)`: the key doesn't have WeatherKit enabled.
- The `.p8` key never expires, but WeatherKit stops working if the Apple Developer membership lapses, and works again after renewal. Meanwhile weatherwise switches to the free source on its own and says so in a `notice:` line.
- To stop using WeatherKit: `uv run {{SKILL_DIR}}/scripts/weatherwise.py config weatherkit --remove`
````

- [ ] **Step 6: 產生 dist，確認測試通過**

Run: `uv run tools/translate.py`
Expected: `built dist/ for: hermes, claude`

Run: `grep -rn "SKILL_DIR" dist/*/weatherwise/SKILL.md | head -2`
Expected: hermes 版是 `${HERMES_SKILL_DIR}`，claude 版是 `${CLAUDE_SKILL_DIR}`

Run: `uv run pytest`
Expected: 全部通過（包含 `test_repo_dist_is_up_to_date`）

- [ ] **Step 7: Commit**

```bash
git add src/weatherwise/SKILL.md src/weatherwise/references tools/translate.py tests/test_translate.py dist
git commit -m "feat: weatherwise SKILL.md, WeatherKit guide, and the skill translator"
```

---

### Task 9: 隱私檢查、README、CI

**Files:**
- Create: `tests/test_privacy.py`、`tests/private-terms.example.txt`、`README.md`、`.github/workflows/test.yml`
- Create（本機、不進 git）: `tests/private-terms.local.txt`

- [ ] **Step 1: 寫 `tests/private-terms.example.txt`**

```
# One private term per line (case-insensitive). Copy to private-terms.local.txt,
# which is gitignored, and fill in the real terms: home area, family names,
# device or entity IDs, anything that must never be published.
# Lines starting with # are ignored.
example-private-term
```

- [ ] **Step 2: 建立本機 deny-list**

把 `~/Developer/smallyuan.dev/tests/dist/private-terms.local.txt` 複製成 `tests/private-terms.local.txt`，再加上舊的 `macos-weather` SKILL.md 裡 agent 對使用者的稱呼。**不要把這些詞寫進任何會被 commit 的檔案，也不要在對話或 commit 訊息裡打出來。**

Run: `git check-ignore tests/private-terms.local.txt`
Expected: 印出路徑（代表有被忽略）

- [ ] **Step 3: 寫 `tests/test_privacy.py`**

```python
"""Nothing on the local deny-list may appear in any file that could be published."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / "tests" / "private-terms.local.txt"
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache"}
SKIP_FILES = {LOCAL.name, "private-terms.example.txt"}


def terms() -> list[str]:
    lines = LOCAL.read_text(encoding="utf-8").splitlines()
    return [t.strip().lower() for t in lines if t.strip() and not t.startswith("#")]


def publishable_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not SKIP_DIRS & set(p.relative_to(ROOT).parts) and p.name not in SKIP_FILES:
            yield p


@pytest.mark.skipif(not LOCAL.exists(), reason="no local deny-list (e.g. in CI)")
def test_no_private_terms_anywhere():
    banned = terms()
    assert banned, "the deny-list is empty"
    hits = []
    for p in publishable_files():
        try:
            text = p.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError:
            continue
        hits += [f"{p.relative_to(ROOT)} (term #{i + 1})" for i, t in enumerate(banned) if t in text]
    assert not hits, f"private terms found in: {hits}"
```

失敗訊息只顯示「第幾個詞」，不印出詞本身，這樣測試失敗時私人資訊也不會出現在終端機或 CI 紀錄裡。

- [ ] **Step 4: 確認隱私測試會抓到東西**

暫時在 `docs/` 建一個檔案，內容是 deny-list 的第一個詞（用 `head -1 tests/private-terms.local.txt > docs/leak-check.txt` 產生，不要手打），然後：

Run: `uv run pytest tests/test_privacy.py -v`
Expected: FAIL，訊息包含 `docs/leak-check.txt (term #1)`

Run: `rm docs/leak-check.txt && uv run pytest tests/test_privacy.py -v`
Expected: PASS

- [ ] **Step 5: 寫 `README.md`**

````markdown
# skills

Agent skills by [SmallYuan](https://smallyuan.dev), ready to drop into [Hermes](https://github.com/NousResearch/hermes-agent) or [Claude Code](https://claude.com/claude-code).

| Skill | What it does |
|---|---|
| [weatherwise](src/weatherwise/SKILL.md) | Weather, forecast, and rain chance for any place. Free by default (Open-Meteo); Apple WeatherKit optional for official alerts. |

## Install

Each skill comes pre-built for each agent in `dist/`. Copy the folder for your agent:

```bash
git clone https://github.com/SmallYuanSY/skills.git

# Hermes
cp -R skills/dist/hermes/weatherwise ~/.hermes/skills/

# Claude Code
cp -R skills/dist/claude/weatherwise ~/.claude/skills/
```

weatherwise needs [uv](https://docs.astral.sh/uv/). Its Python dependencies install themselves on first run.

## Setup

Just ask your agent, e.g. "set my default location to Taipei". It runs the right `config` command for you. For Apple WeatherKit, ask it to walk you through [the setup guide](src/weatherwise/references/weatherkit-setup.md).

The command's output is written for the agent to read (plain English `key: value` lines). Your agent answers in your own language.

## Development

Edit skills only in `src/`. `dist/` is generated:

```bash
uv run tools/translate.py   # rebuild dist/ from src/
uv run pytest               # tests (no network)
```

The translator replaces `{{SKILL_DIR}}` in Markdown files with each agent's skill-folder variable (`${HERMES_SKILL_DIR}`, `${CLAUDE_SKILL_DIR}`). To support another agent, add a row to `TARGETS` in `tools/translate.py`.

## License

[MIT](LICENSE) © 2026 SmallYuan
````

- [ ] **Step 6: 寫 `.github/workflows/test.yml`**

```yaml
name: test
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv run pytest
      - run: uv run tools/translate.py --check
```

CI 沒有本機的 deny-list，所以隱私測試會被跳過；其他測試照跑。

- [ ] **Step 7: 全部重跑**

Run: `uv run tools/translate.py --check && uv run pytest -v`
Expected: `dist/ is up to date`，全部通過，隱私測試是 PASS（不是 SKIPPED）

- [ ] **Step 8: Commit**

```bash
git add tests/test_privacy.py tests/private-terms.example.txt README.md .github
git status --short   # 確認 private-terms.local.txt 沒有出現
git commit -m "chore: privacy check, README, and CI"
```

---

### Task 10: 實測（手動，不 push）

**Files:** 不改 repo（發現問題時回到對應的 task 修正，並補上測試）

- [ ] **Step 1: 免費模式實測**

```bash
export WEATHERWISE_CONFIG_DIR=$(mktemp -d)
S=~/Developer/skills/src/weatherwise/scripts/weatherwise.py
uv run $S                                   # 預期 error: no_default_location
uv run $S config set-default 台北            # 預期 saved: default = ...
uv run $S                                   # 預期 source: open-meteo、alerts: unsupported
uv run $S Tokyo --global --lang en          # 預期 location 是英文的 Tokyo、timezone=Asia/Tokyo
uv run $S --version
```

- [ ] **Step 2: WeatherKit 實測**

用使用者現有的金鑰（`~/.config/weatherkit/`）。**只讀取 `config.json` 裡的 ID 欄位，不讀、不印 `.p8` 的內容。**

```bash
uv run $S config weatherkit --team-id <team_id> --service-id <service_id> --key-file <key_path>
uv run $S config show                       # 預期 source: weatherkit，ID 被遮蔽
uv run $S                                   # 預期 source: weatherkit、alerts: none 或有內容
uv run $S config weatherkit --remove
unset WEATHERWISE_CONFIG_DIR
```

- [ ] **Step 3: 安裝到這台的 Hermes，讓飛予實際使用**

先跟使用者確認，再執行：

```bash
cp -R ~/Developer/skills/dist/hermes/weatherwise ~/.hermes/skills/
```

暫停 `macos-weather`（具體做法依 Hermes 的 skill 停用方式，執行前先查清楚並跟使用者確認）。

請使用者用真實對話測試：「明天要帶傘嗎」「預設地點改成台中」「東京這週天氣」「颱風要來了嗎」。確認：日期對得上 `local_time`、不會把 `alerts: unsupported` 說成沒有警報、`set-default` 之後有跟使用者確認地點。

發現答錯 → 修改輸出格式或 SKILL.md → 補測試 → `uv run tools/translate.py` → 重新複製到 Hermes → 再測。

- [ ] **Step 4: 回報**

整理實測結果給使用者，詢問是否要建立 GitHub repo 並 push。這份計畫到此結束。
