# routine-keeper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做出 `routine-keeper`：一支零依賴的 Python CLI（SQLite）讓 agent 記錄與查詢家事、保健品，外加手寫的 Hermes 版（分類結構）與 Claude Code 版（單一 skill），以及打包兩個 release zip 的工具與 workflow。

**Architecture:** `src/routine-keeper/scripts/` 是唯一一份程式：`routine.py` 只做 argparse 與分派，`routine_core/` 依職責拆成 errors / dates / schedule（純函式排程引擎）/ status（某天狀態，純函式）/ db / storage / items / logs / notes 與四個指令模組。`hermes/`、`claude/` 是兩套手寫的 skill 文件。`tools/package.py` 把 scripts 複製進兩套並打包。

**Tech Stack:** Python ≥ 3.10 標準函式庫（sqlite3、zoneinfo、argparse、json），pytest（已在 repo 的 dev group），GitHub Actions。

**Spec:** `docs/specs/2026-10-14-routine-keeper-design.md`

## Global Constraints

- Python `>=3.10`，執行期零依賴，只用標準函式庫；指令寫成 `python3 .../routine.py`，不用 `uv`。
- 輸出固定英文 `key: value` 行，寫給 agent 讀；不做 i18n。
- 錯誤一律 `error: <code>` + `action: <next step>`，永不輸出 traceback。
- exit code：0 成功；1 指令／參數錯（含 internal_error）；2 業務錯誤；3 資料位置錯誤。
- 不用 overdue、late、failed 這類帶壓力的詞描述使用者（`done_late` 是場次狀態代碼，不出現在給使用者看的句子裡；文字輸出用「N days late」描述完成相對預定日的偏差，這是事實陳述）。
- 每個 Hermes 子 skill 的 `description` ≤ 60 字元，`name` 與資料夾同名。
- 設定檔 `config.json` 與預設資料 `data/` 放在 skill 根目錄（`routine.py` 往上一層）；兩者不進 git、不進 release zip。
- 日界線預設 `05:00`；時區預設系統時區。
- 防預填：`--at` 晚於現在、或 `--for` 晚於今天（依日界線）一律拒絕。
- 不做 `import`。
- repo 不得含私人資訊（`tests/test_privacy.py` 會掃）。範例一律用 Vitamin D、Magnesium、Laundry、Litter box、Bed sheets 這類通用名稱。
- 現有 weatherwise、`tools/translate.py`、`dist/` 行為不變。

## Review Focus

1. **中文名稱與多餘空白**：使用者或 agent 打「魚油  EX」（兩個空白）或大小寫不同的英文名，應該找得到同一個項目 → Task 7 `test_names_ignore_case_and_extra_spaces`。
2. **資料夾壞掉或 DB 不是 SQLite**：應回 `error: data_unavailable`、exit 3、沒有 traceback → Task 6 `test_corrupt_database_is_data_unavailable`、Task 7 `test_unexpected_exception_never_shows_traceback`。
3. **事後改時區**：已存在紀錄的歸屬日不能被改寫 → Task 9 `test_changing_timezone_keeps_past_days`。
4. **剛好在日界線時間記錄（05:00 整）**：算當天，不算前一天 → Task 2 `test_exactly_at_boundary_counts_for_that_day`。
5. **週期項目好幾週都沒做**：`time` 輸出要短，不能列出一長串錯過 → Task 9 `test_many_missed_days_are_summarised`。

---

## File Structure

```
src/routine-keeper/
├── scripts/
│   ├── routine.py                  CLI 入口：argparse、--json、錯誤輸出、分派
│   └── routine_core/
│       ├── __init__.py             VERSION
│       ├── errors.py               錯誤代碼、exit code、action 文字
│       ├── dates.py                日界線、日期與時間解析、時區
│       ├── schedule.py             排程規則解析／描述、weekly 場次配對（純函式）
│       ├── status.py               某項目在某天的狀態（純函式）
│       ├── db.py                   schema、meta 設定
│       ├── storage.py              skill 根目錄、config.json、開 DB、data move
│       ├── items.py                項目與別名
│       ├── logs.py                 完成紀錄、skip、紀錄修改
│       ├── notes.py                提醒
│       ├── context.py              Ctx（連線、時間、時區、日界線）與 Result
│       ├── cmd_items.py            item add|edit|pause|resume|list
│       ├── cmd_logs.py             done、skip、log …、note …
│       ├── cmd_time.py             time
│       └── cmd_admin.py            config …、data …、export
├── hermes/
│   ├── DESCRIPTION.md
│   ├── routine-log/SKILL.md
│   ├── routine-setup/SKILL.md
│   └── routine-history/SKILL.md
└── claude/
    ├── SKILL.md
    └── references/{setup.md, history.md}
tools/package.py                    組裝並打包兩個 zip
tools/translate.py                  （修改）只處理根目錄有 SKILL.md 的 skill
.github/workflows/release-routine-keeper.yml
tests/rk_helpers.py                 共用的 NOW、root fixture、run()
tests/test_routine_errors.py
tests/test_routine_dates.py
tests/test_routine_schedule.py
tests/test_routine_status.py
tests/test_routine_storage.py
tests/test_routine_items.py
tests/test_routine_logs.py
tests/test_routine_time.py
tests/test_routine_data.py
tests/test_routine_skills.py
tests/test_package.py
```

測試日期基準：**2026-10-14 是星期三**。附近日期：Wed 10-07、Sat 10-10、Sun 10-11、Mon 10-12、Tue 10-13、Wed 10-14、Thu 10-15、Fri 10-16、Sat 10-17。

---

### Task 1: 骨架、錯誤代碼、translate 只處理單一 skill

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Modify: `tools/translate.py:33-46`
- Modify: `tests/test_translate.py`
- Create: `src/routine-keeper/scripts/routine_core/__init__.py`
- Create: `src/routine-keeper/scripts/routine_core/errors.py`
- Create: `tests/test_routine_errors.py`

**Interfaces:**
- Produces: `routine_core.VERSION: str`；`errors.USAGE/BUSINESS/STORAGE: int`；`errors.ACTIONS: dict[str, tuple[int, str]]`；`class RkError(Exception)`（屬性 `code`, `detail`, `exit_code`）；`render_error(err) -> str`；`error_data(err) -> dict`。

- [ ] **Step 1: 設定 pytest 路徑與 gitignore**

`pyproject.toml` 的 `pythonpath` 改成：

```toml
pythonpath = ["src/weatherwise/scripts", "src/routine-keeper/scripts", "tools"]
```

`.gitignore` 末尾加上：

```
/src/routine-keeper/**/config.json
/src/routine-keeper/**/data/
/build/
```

- [ ] **Step 2: 寫 translate 的失敗測試**

在 `tests/test_translate.py` 末尾加：

```python
def test_folders_without_a_root_skill_md_are_left_alone(src, tmp_path):
    other = src / "bundle"
    (other / "hermes" / "part").mkdir(parents=True)
    (other / "hermes" / "part" / "SKILL.md").write_text("{{NOT_OURS}}\n")
    out = tmp_path / "dist"
    build(src, out)
    assert not (out / "hermes" / "bundle").exists()
    assert check(src, out) == []
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `uv run pytest tests/test_translate.py::test_folders_without_a_root_skill_md_are_left_alone -v`
Expected: FAIL，`TranslateError: ... unknown placeholder {{NOT_OURS}}`

- [ ] **Step 4: 修改 translate.py 的 `_render`**

把 `tools/translate.py` 的 `_render` 換成：

```python
def _skill_dirs(src: Path) -> list[Path]:
    """Only folders with a SKILL.md at their root are translated; others (e.g. hand-written
    per-agent skills such as routine-keeper) are packaged by tools/package.py instead."""
    return [d for d in sorted(src.iterdir()) if d.is_dir() and (d / "SKILL.md").is_file()]


def _render(src: Path, out: Path) -> None:
    for target, skill_dir in TARGETS.items():
        for skill in _skill_dirs(src):
            for f in sorted(skill.rglob("*")):
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
```

- [ ] **Step 5: 跑 translate 全部測試**

Run: `uv run pytest tests/test_translate.py -v`
Expected: 全部 PASS（包含 `test_repo_dist_is_up_to_date`）

- [ ] **Step 6: 寫 errors 的失敗測試**

`tests/test_routine_errors.py`：

```python
import pytest

from routine_core import VERSION
from routine_core.errors import ACTIONS, BUSINESS, STORAGE, USAGE, RkError, error_data, render_error


def test_version_is_semver():
    assert VERSION.count(".") == 2


def test_every_code_has_an_exit_code_and_an_action():
    for code, (exit_code, action) in ACTIONS.items():
        assert exit_code in (USAGE, BUSINESS, STORAGE), code
        assert action and not action.endswith("."), code


def test_unknown_code_is_a_programming_error():
    with pytest.raises(ValueError):
        RkError("no_such_code")


def test_render_error_has_code_detail_and_action():
    err = RkError("unknown_item", 'no item named "Vit"; existing: Vitamin D')
    assert err.exit_code == BUSINESS
    assert render_error(err) == (
        'error: unknown_item (no item named "Vit"; existing: Vitamin D)\n'
        f"action: {ACTIONS['unknown_item'][1]}"
    )


def test_error_data_for_json():
    err = RkError("data_unavailable", "/x")
    assert error_data(err) == {"error": "data_unavailable", "detail": "/x", "action": ACTIONS["data_unavailable"][1]}
```

- [ ] **Step 7: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_errors.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'routine_core'`

- [ ] **Step 8: 實作**

`src/routine-keeper/scripts/routine_core/__init__.py`：

```python
# routine-keeper · Copyright (c) 2026 SmallYuan · MIT License · https://github.com/SmallYuanSY/skills
"""Chores and supplements for an agent to log and check."""
VERSION = "1.0.0"
REPO = "https://github.com/SmallYuanSY/skills"
```

`src/routine-keeper/scripts/routine_core/errors.py`：

```python
"""Errors the agent reads. Every code comes with an exit code and the next step to take."""

USAGE, BUSINESS, STORAGE = 1, 2, 3

ACTIONS: dict[str, tuple[int, str]] = {
    "bad_arguments": (USAGE, "fix the command using the usage in SKILL.md"),
    "bad_date": (USAGE, "use YYYY-MM-DD, today, or yesterday"),
    "bad_time": (USAGE, 'use "YYYY-MM-DD HH:MM" in the configured timezone'),
    "bad_schedule": (USAGE, "use daily, none, interval:N (1-365), or weekly: plus days such as weekly:wed,sat"),
    "bad_window": (USAGE, "use --window -E,+L with whole days from 0 to 6, e.g. -1,+2"),
    "bad_setting": (USAGE, "day-boundary takes HH:MM; timezone takes an IANA name such as Asia/Taipei or America/New_York"),
    "internal_error": (USAGE, "tell the user routine-keeper hit an unexpected problem and nothing was saved; if it keeps happening, report it at https://github.com/SmallYuanSY/skills/issues"),
    "unknown_item": (BUSINESS, "retry with an exact name from the list above; if none fits, ask the user, then add the item or an alias (see routine-setup)"),
    "unknown_alias": (BUSINESS, "check the item's aliases with: item list"),
    "name_taken": (BUSINESS, "pick another name, or edit the item that already uses it"),
    "item_paused": (BUSINESS, "the item is paused; ask the user whether to resume it with: item resume <name>"),
    "future_time": (BUSINESS, "only log what the user says already happened; never log ahead of time"),
    "already_logged": (BUSINESS, "tell the user it is already logged for that day; add --force only if they confirm it really happened twice"),
    "skip_not_applicable": (BUSINESS, "skip only works for daily and weekly items"),
    "not_scheduled": (BUSINESS, "skip a day the item is scheduled on; check with: time <date>"),
    "unknown_log": (BUSINESS, "find the id with: log list"),
    "unknown_note": (BUSINESS, "find the id with: note list"),
    "target_exists": (BUSINESS, "ask the user whether to switch to the data already there (--use-existing) or replace it (--overwrite)"),
    "data_unavailable": (STORAGE, "nothing was saved; tell the user the data folder cannot be used and show them the path from: data where"),
    "data_version_newer": (STORAGE, "this data was written by a newer routine-keeper; ask the user to update the skill"),
    "move_verify_failed": (STORAGE, "nothing changed and the data stays where it was; tell the user the move failed"),
}


class RkError(Exception):
    def __init__(self, code: str, detail: str = ""):
        if code not in ACTIONS:
            raise ValueError(f"unknown error code: {code}")
        super().__init__(code)
        self.code = code
        self.detail = detail

    @property
    def exit_code(self) -> int:
        return ACTIONS[self.code][0]


def render_error(err: RkError) -> str:
    head = f"error: {err.code}" + (f" ({err.detail})" if err.detail else "")
    return f"{head}\naction: {ACTIONS[err.code][1]}"


def error_data(err: RkError) -> dict:
    return {"error": err.code, "detail": err.detail, "action": ACTIONS[err.code][1]}
```

- [ ] **Step 9: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_errors.py tests/test_translate.py -v`
Expected: 全部 PASS

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml .gitignore tools/translate.py tests/test_translate.py src/routine-keeper tests/test_routine_errors.py
git commit -m "feat: routine-keeper scaffolding and error codes; translate only skills with a root SKILL.md"
```

---

### Task 2: 日期、日界線、時區

**Files:**
- Create: `src/routine-keeper/scripts/routine_core/dates.py`
- Create: `tests/test_routine_dates.py`

**Interfaces:**
- Consumes: `RkError`（Task 1）
- Produces:
  - `WEEKDAYS: tuple[str, ...]`（`"mon"`…`"sun"`，index = `date.weekday()`）
  - `parse_boundary(text: str) -> datetime.time`（錯誤 `bad_setting`）
  - `zone(name: str) -> ZoneInfo`（錯誤 `bad_setting`）
  - `system_timezone() -> str`
  - `day_of(at: datetime, boundary: time) -> date`（`at` 必須是已換到設定時區的 aware datetime）
  - `parse_day(text: str, today: date) -> date`（`today`、`yesterday`、`YYYY-MM-DD`；錯誤 `bad_date`）
  - `parse_at(text: str, tz: ZoneInfo) -> datetime`（`YYYY-MM-DD HH:MM`；錯誤 `bad_time`）
  - `short_day(d: date) -> str` → `"Wed 2026-10-14"`
  - `long_day(d: date) -> str` → `"2026-10-14 (Wed)"`
  - `plural(n: int, word: str) -> str` → `"1 day"`、`"2 days"`
  - `ago(d: date, q: date) -> str` → `"today"`、`"1 day ago"`、`"3 days ago"`、`"in 2 days"`

- [ ] **Step 1: 寫失敗測試**

`tests/test_routine_dates.py`：

```python
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from routine_core.dates import (
    ago, day_of, long_day, parse_at, parse_boundary, parse_day, plural, short_day, system_timezone, zone)
from routine_core.errors import RkError

TPE = ZoneInfo("Asia/Taipei")
FIVE = time(5, 0)


def local(text):
    return datetime.fromisoformat(text).replace(tzinfo=TPE)


def test_before_the_boundary_counts_for_the_previous_day():
    assert day_of(local("2026-10-02 03:10"), FIVE) == date(2026, 10, 1)


def test_exactly_at_boundary_counts_for_that_day():
    assert day_of(local("2026-10-02 05:00"), FIVE) == date(2026, 10, 2)


def test_midnight_boundary_means_calendar_days():
    assert day_of(local("2026-10-02 00:00"), time(0, 0)) == date(2026, 10, 2)


def test_parse_boundary():
    assert parse_boundary("5:00") == FIVE
    assert parse_boundary(" 04:30 ") == time(4, 30)
    for bad in ("24:00", "5", "05:60", "five"):
        with pytest.raises(RkError) as e:
            parse_boundary(bad)
        assert e.value.code == "bad_setting"


def test_zone():
    assert zone("Asia/Taipei") == TPE
    for bad in ("Mars/Base", "", "../etc"):
        with pytest.raises(RkError) as e:
            zone(bad)
        assert e.value.code == "bad_setting"


def test_system_timezone_is_a_real_zone(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris")
    assert system_timezone() == "Europe/Paris"
    monkeypatch.setenv("TZ", "Not/AZone")
    assert ZoneInfo(system_timezone())


def test_parse_day():
    today = date(2026, 10, 14)
    assert parse_day("today", today) == today
    assert parse_day("Yesterday", today) == date(2026, 10, 13)
    assert parse_day("2026-10-01", today) == date(2026, 10, 1)
    for bad in ("2026-13-01", "10/13", "tomorrow", "2026-1-1"):
        with pytest.raises(RkError) as e:
            parse_day(bad, today)
        assert e.value.code == "bad_date"


def test_parse_at():
    assert parse_at("2026-10-02 03:10", TPE) == local("2026-10-02 03:10")
    assert parse_at("2026-10-02T3:10", TPE) == local("2026-10-02 03:10")
    for bad in ("2026-10-02", "2026-10-02 25:00", "now"):
        with pytest.raises(RkError) as e:
            parse_at(bad, TPE)
        assert e.value.code == "bad_time"


def test_formatting():
    d = date(2026, 10, 14)
    assert short_day(d) == "Wed 2026-10-14"
    assert long_day(d) == "2026-10-14 (Wed)"
    assert plural(1, "day") == "1 day" and plural(0, "day") == "0 days"
    assert ago(d, d) == "today"
    assert ago(date(2026, 10, 13), d) == "1 day ago"
    assert ago(date(2026, 10, 7), d) == "7 days ago"
    assert ago(date(2026, 10, 16), d) == "in 2 days"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_dates.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'routine_core.dates'`

- [ ] **Step 3: 實作 `dates.py`**

```python
"""Days, the day boundary, and time zones. A record's day is its local time minus the boundary."""
import os
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import RkError

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_AT = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})$")
_HM = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_boundary(text: str) -> time:
    m = _HM.match(text.strip())
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        raise RkError("bad_setting", f"day-boundary {text!r}")
    return time(int(m[1]), int(m[2]))


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise RkError("bad_setting", f"timezone {name!r}") from None


def _localtime_name() -> str:
    target = os.path.realpath("/etc/localtime")
    marker = "zoneinfo/"
    return target.split(marker, 1)[1] if marker in target else ""


def system_timezone() -> str:
    for cand in (os.environ.get("TZ", "").lstrip(":"), _localtime_name()):
        if cand:
            try:
                ZoneInfo(cand)
                return cand
            except (ZoneInfoNotFoundError, ValueError):
                continue
    return "UTC"


def day_of(at: datetime, boundary: time) -> date:
    d = at.date()
    return d - timedelta(days=1) if at.time() < boundary else d


def parse_day(text: str, today: date) -> date:
    t = text.strip().lower()
    if t == "today":
        return today
    if t == "yesterday":
        return today - timedelta(days=1)
    if _DAY.match(t):
        try:
            return date.fromisoformat(t)
        except ValueError:
            pass
    raise RkError("bad_date", text)


def parse_at(text: str, tz: ZoneInfo) -> datetime:
    m = _AT.match(text.strip())
    if m:
        try:
            d = date.fromisoformat(m[1])
            return datetime(d.year, d.month, d.day, int(m[2]), int(m[3]), tzinfo=tz)
        except ValueError:
            pass
    raise RkError("bad_time", text)


def short_day(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()].capitalize()} {d.isoformat()}"


def long_day(d: date) -> str:
    return f"{d.isoformat()} ({WEEKDAYS[d.weekday()].capitalize()})"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def ago(d: date, q: date) -> str:
    n = (q - d).days
    if n == 0:
        return "today"
    return f"{plural(n, 'day')} ago" if n > 0 else f"in {plural(-n, 'day')}"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_dates.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/routine-keeper/scripts/routine_core/dates.py tests/test_routine_dates.py
git commit -m "feat: routine-keeper days, day boundary, and time zones"
```

---

### Task 3: 排程規則的解析與描述

**Files:**
- Create: `src/routine-keeper/scripts/routine_core/schedule.py`
- Create: `tests/test_routine_schedule.py`

**Interfaces:**
- Consumes: `WEEKDAYS`, `plural`（Task 2）；`RkError`
- Produces:
  - `@dataclass(frozen=True) Schedule(kind: str, n: int = 0, days: tuple[int, ...] = ())`，`kind ∈ {"daily","none","interval","weekly"}`
  - `parse_schedule(text: str) -> Schedule`（錯誤 `bad_schedule`）
  - `format_schedule(s: Schedule) -> str`（標準形式，例如 `weekly:wed,sat`）
  - `parse_window(text: str) -> tuple[int, int]`（`"-1,+2"` → `(1, 2)`；錯誤 `bad_window`）
  - `describe(s: Schedule, early: int, late: int) -> str`

- [ ] **Step 1: 寫失敗測試**

`tests/test_routine_schedule.py`：

```python
import pytest

from routine_core.errors import RkError
from routine_core.schedule import Schedule, describe, format_schedule, parse_schedule, parse_window


@pytest.mark.parametrize("text,expected", [
    ("daily", Schedule("daily")),
    ("NONE", Schedule("none")),
    ("interval:14", Schedule("interval", n=14)),
    ("weekly:sat,wed", Schedule("weekly", days=(2, 5))),
    ("weekly: Wed, Sat, wed", Schedule("weekly", days=(2, 5))),
])
def test_parse_schedule(text, expected):
    assert parse_schedule(text) == expected


@pytest.mark.parametrize("text", ["", "weekly", "weekly:", "weekly:wednesday", "interval:0", "interval:366", "interval:x", "monthly:1"])
def test_bad_schedule(text):
    with pytest.raises(RkError) as e:
        parse_schedule(text)
    assert e.value.code == "bad_schedule"


def test_format_schedule_round_trips():
    for text in ("daily", "none", "interval:14", "weekly:wed,sat"):
        assert format_schedule(parse_schedule(text)) == text


def test_parse_window():
    assert parse_window("-1,+2") == (1, 2)
    assert parse_window("-0,3") == (0, 3)
    assert parse_window(" -2, +0 ") == (2, 0)
    for bad in ("1,2", "-7,+0", "-1", "+1,-2", "-1,+x"):
        with pytest.raises(RkError) as e:
            parse_window(bad)
        assert e.value.code == "bad_window"


def test_describe():
    assert describe(Schedule("daily"), 1, 2) == "every day"
    assert describe(Schedule("none"), 1, 2) == "no schedule, log only"
    assert describe(Schedule("interval", n=1), 1, 2) == "every 1 day after the last time it was done"
    assert describe(Schedule("interval", n=14), 1, 2) == "every 14 days after the last time it was done"
    assert describe(Schedule("weekly", days=(2, 5)), 1, 2) == "every Wed and Sat, can be done 1 day early or 2 days late"
    assert describe(Schedule("weekly", days=(0, 2, 4)), 0, 0) == "every Mon, Wed and Fri, only on the day"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_schedule.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'routine_core.schedule'`

- [ ] **Step 3: 實作 `schedule.py`（本 task 只寫解析與描述）**

```python
"""Schedule rules, and how completions settle weekly scheduled days. Pure: no database, no clock."""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from .dates import WEEKDAYS, plural
from .errors import RkError

_WINDOW = re.compile(r"^-(\d),\+?(\d)$")


@dataclass(frozen=True)
class Schedule:
    kind: str                    # "daily" | "none" | "interval" | "weekly"
    n: int = 0                   # interval: days between
    days: tuple[int, ...] = ()   # weekly: 0=Mon .. 6=Sun, sorted, unique


def parse_schedule(text: str) -> Schedule:
    t = text.strip().lower().replace(" ", "")
    if t in ("daily", "none"):
        return Schedule(t)
    if t.startswith("interval:"):
        n = t[len("interval:"):]
        if n.isdigit() and 1 <= int(n) <= 365:
            return Schedule("interval", n=int(n))
    if t.startswith("weekly:"):
        parts = [p for p in t[len("weekly:"):].split(",") if p]
        if parts and all(p in WEEKDAYS for p in parts):
            return Schedule("weekly", days=tuple(sorted({WEEKDAYS.index(p) for p in parts})))
    raise RkError("bad_schedule", text)


def format_schedule(s: Schedule) -> str:
    if s.kind == "interval":
        return f"interval:{s.n}"
    if s.kind == "weekly":
        return "weekly:" + ",".join(WEEKDAYS[d] for d in s.days)
    return s.kind


def parse_window(text: str) -> tuple[int, int]:
    m = _WINDOW.match(text.strip().replace(" ", ""))
    if not m or int(m[1]) > 6 or int(m[2]) > 6:
        raise RkError("bad_window", text)
    return int(m[1]), int(m[2])


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def describe(s: Schedule, early: int, late: int) -> str:
    if s.kind == "daily":
        return "every day"
    if s.kind == "none":
        return "no schedule, log only"
    if s.kind == "interval":
        return f"every {plural(s.n, 'day')} after the last time it was done"
    days = _join([WEEKDAYS[d].capitalize() for d in s.days])
    if early == 0 and late == 0:
        return f"every {days}, only on the day"
    return f"every {days}, can be done {plural(early, 'day')} early or {plural(late, 'day')} late"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_schedule.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/routine-keeper/scripts/routine_core/schedule.py tests/test_routine_schedule.py
git commit -m "feat: routine-keeper schedule rules and plain descriptions"
```

---

### Task 4: weekly 場次配對引擎

**Files:**
- Modify: `src/routine-keeper/scripts/routine_core/schedule.py`（檔尾新增）
- Modify: `tests/test_routine_schedule.py`（檔尾新增）

**Interfaces:**
- Produces:
  - `@dataclass Occurrence(day: date, status: str, by: date | None = None)`；`status ∈ {"due","makeup","missed","done","done_early","done_late","merged","skipped"}`
  - `@dataclass Settlement(day: date, claimed: date | None, offset: int, merged: list[date])`，property `extra: bool`
  - `evaluate_weekly(days: tuple[int, ...], early: int, late: int, completions: list[date], skips: set[date], start: date, until: date) -> tuple[list[Occurrence], list[Settlement]]`
    - 場次範圍：`start` 到 `until + early`，星期在 `days` 裡的日子。
    - 呼叫端只傳 `<= until` 的完成日。
    - 配對規則（spec「排程規則 › weekly」）：每次完成依時間順序，抵掉「窗口包含它、尚未被抵、未被 skip」的最早場次；所有「尚未被抵、未 skip、窗口結束早於這次完成」的場次標 `merged`；都沒有就是 `extra`。
    - 未被抵的場次相對 `until`：`day >= until` → `due`（範圍只到 `until + early`，所以都在提前窗口內）；`day + late >= until` → `makeup`；否則 `missed`。「下一個場次」不在這裡算，由 Task 5 的 `day_status` 處理。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_routine_schedule.py` 檔尾加：

```python
from datetime import date

from routine_core.schedule import evaluate_weekly

WED_SAT = (2, 5)


def d(text):
    return date.fromisoformat(text)


def statuses(occ):
    return {o.day.isoformat(): o.status for o in occ}


def run_week(completions, until, skips=(), days=WED_SAT, early=1, late=2, start="2026-10-07"):
    return evaluate_weekly(days, early, late, [d(c) for c in completions], {d(s) for s in skips}, d(start), d(until))


# The spec's example table (weekly:wed,sat, window -1,+2), starting after a normal Wed 10-07.

def test_done_the_day_before_counts_early():
    occ, sets = run_week(["2026-10-07", "2026-10-10", "2026-10-13"], "2026-10-13")
    assert statuses(occ)["2026-10-14"] == "done_early"
    assert sets[-1].claimed == d("2026-10-14") and sets[-1].offset == -1


def test_saturday_made_up_on_monday():
    occ, sets = run_week(["2026-10-07", "2026-10-12"], "2026-10-12")
    assert statuses(occ)["2026-10-10"] == "done_late"
    assert sets[-1].claimed == d("2026-10-10") and sets[-1].offset == 2
    # Wednesday is still open: on Tue 10-13 it is due
    assert statuses(run_week(["2026-10-07", "2026-10-12"], "2026-10-13")[0])["2026-10-14"] == "due"


def test_saturday_missed_then_done_tuesday_merges_it():
    occ, sets = run_week(["2026-10-07", "2026-10-13"], "2026-10-13")
    s = statuses(occ)
    assert s["2026-10-10"] == "merged"
    assert s["2026-10-14"] == "done_early"
    assert sets[-1].merged == [d("2026-10-10")]


def test_saturday_missed_then_done_wednesday():
    occ, sets = run_week(["2026-10-07", "2026-10-14"], "2026-10-14")
    s = statuses(occ)
    assert s["2026-10-10"] == "merged"
    assert s["2026-10-14"] == "done"
    assert sets[-1].offset == 0 and sets[-1].merged == [d("2026-10-10")]


def test_skipped_saturday_is_not_merged():
    occ, _ = run_week(["2026-10-07", "2026-10-14"], "2026-10-14", skips=["2026-10-10"])
    s = statuses(occ)
    assert s["2026-10-10"] == "skipped"
    assert s["2026-10-14"] == "done"


# Pending states relative to `until`

def test_pending_states():
    s = statuses(run_week(["2026-10-07"], "2026-10-11")[0])
    assert s["2026-10-10"] == "makeup"
    s = statuses(run_week(["2026-10-07"], "2026-10-13")[0])
    assert s["2026-10-10"] == "missed" and s["2026-10-14"] == "due"
    s = statuses(run_week(["2026-10-07"], "2026-10-08")[0])
    assert "2026-10-10" not in s   # beyond the early window; day_status works out "next" itself
    s = statuses(run_week(["2026-10-07"], "2026-10-09")[0])
    assert s["2026-10-10"] == "due"


def test_many_missed_then_one_completion_settles_all():
    occ, sets = run_week(["2026-10-07", "2026-10-28"], "2026-10-28")
    s = statuses(occ)
    assert [k for k, v in s.items() if v == "merged"] == [
        "2026-10-10", "2026-10-14", "2026-10-17", "2026-10-21", "2026-10-24"]
    assert s["2026-10-28"] == "done"
    assert not [v for v in s.values() if v == "missed"]


def test_completion_outside_every_window_with_nothing_missed_is_extra():
    # weekly:mon only, window -1,+2 covers Sun..Wed; Thu 10-08 is outside, Mon 10-05 was done.
    occ, sets = run_week(["2026-10-05", "2026-10-08"], "2026-10-08", days=(0,), start="2026-10-05")
    assert sets[-1].extra
    assert statuses(occ) == {"2026-10-05": "done"}


def test_completion_outside_every_window_still_merges_earlier_misses():
    # Mon 10-05 never done; Thu 10-08 merges it and does not claim next Mon.
    occ, sets = run_week(["2026-10-08"], "2026-10-08", days=(0,), start="2026-10-05")
    assert sets[-1].merged == [d("2026-10-05")] and sets[-1].claimed is None
    assert not sets[-1].extra


def test_overlapping_windows_prefer_the_earlier_day():
    # weekly:fri,sat, window -1,+2: a Saturday completion makes up Friday; Saturday stays due.
    occ, sets = run_week(["2026-10-17"], "2026-10-17", days=(4, 5), start="2026-10-16")
    s = statuses(occ)
    assert s["2026-10-16"] == "done_late"
    assert s["2026-10-17"] == "due"


def test_two_completions_in_one_window_claim_two_days():
    occ, sets = run_week(["2026-10-16", "2026-10-17"], "2026-10-17", days=(4, 5), start="2026-10-16")
    s = statuses(occ)
    assert s["2026-10-16"] == "done" and s["2026-10-17"] == "done"


def test_crossing_a_year():
    occ, _ = run_week(["2026-12-30", "2027-01-02"], "2027-01-02", start="2026-12-30")
    s = statuses(occ)
    assert s["2026-12-30"] == "done" and s["2027-01-02"] == "done"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_schedule.py -v`
Expected: 新測試 FAIL，`ImportError: cannot import name 'evaluate_weekly'`

- [ ] **Step 3: 在 `schedule.py` 檔尾實作**

```python
@dataclass
class Occurrence:
    day: date
    status: str               # due|makeup|missed|done|done_early|done_late|merged|skipped
    by: date | None = None    # the completion day that settled it


@dataclass
class Settlement:
    day: date                  # the completion
    claimed: date | None       # the scheduled day it counted for
    offset: int                # completion minus claimed day, in days
    merged: list[date] = field(default_factory=list)

    @property
    def extra(self) -> bool:
        return self.claimed is None and not self.merged


def evaluate_weekly(days, early, late, completions, skips, start, until):
    """Settle each scheduled day in [start, until + early] against the completions (all <= until).

    A completion claims the earliest open day whose window holds it, so making up comes before
    doing early. It also settles every open day whose window ended before it as "merged": doing
    it once clears what was missed, nothing piles up. Skipped days are never claimed or merged.
    """
    before, after = timedelta(days=early), timedelta(days=late)
    occ_days = []
    d = start
    while d <= until + before:
        if d.weekday() in days:
            occ_days.append(d)
        d += timedelta(days=1)
    state: dict[date, tuple[str, date | None]] = {o: ("skipped", None) for o in occ_days if o in skips}
    settlements = []
    for c in sorted(completions):
        open_days = [o for o in occ_days if o not in state]
        holding = [o for o in open_days if o - before <= c <= o + after]
        claimed = min(holding) if holding else None
        offset = (c - claimed).days if claimed else 0
        if claimed:
            state[claimed] = ("done" if offset == 0 else "done_early" if offset < 0 else "done_late", c)
        merged = [o for o in open_days if o != claimed and o + after < c]
        for o in merged:
            state[o] = ("merged", c)
        settlements.append(Settlement(c, claimed, offset, merged))
    result = []
    for o in occ_days:
        if o in state:
            status, by = state[o]
        elif o >= until:   # only days up to until + early are listed, so this is inside the early window
            status, by = "due", None
        elif o + after >= until:
            status, by = "makeup", None
        else:
            status, by = "missed", None
        result.append(Occurrence(o, status, by))
    return result, settlements
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_schedule.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/routine-keeper/scripts/routine_core/schedule.py tests/test_routine_schedule.py
git commit -m "feat: weekly schedule settlement with make-up, early, merge, and skip"
```

---

### Task 5: 某項目在某天的狀態

**Files:**
- Create: `src/routine-keeper/scripts/routine_core/status.py`
- Create: `tests/test_routine_status.py`

**Interfaces:**
- Consumes: `Schedule`, `Settlement`, `evaluate_weekly`（Task 3–4）
- Produces:
  - `@dataclass DayStatus(state: str, ref: date | None = None, last_done: date | None = None, missed: list[date] = [], settlement: Settlement | None = None)`
    - `state ∈ {"done","not_done","skipped","idle","never_done","upcoming","due","makeup","missed"}`
  - `day_status(sch: Schedule, early: int, late: int, start: date, done_days: list[date], skips: set[date], q: date) -> DayStatus`
    - `done_days` 可以有重複、可以含 `> q` 的日子（會被忽略）。
    - weekly 只把 `>= start - early` 的完成拿去配對；`last_done` 用全部完成。
    - interval：`q` 當天有完成 → `done`，`ref = q + n`；沒有完成過 → `never_done`；否則 `ref = 上次 + n`，`q < ref` → `upcoming`，否則 `due`。
    - weekly：當天有完成 → `done`（附該天最後一筆 settlement）；否則依序：第一個 `due`/`makeup` 場次 → 該狀態；有 `missed` → `missed`（ref = 最後一個）；當天場次被 skip → `skipped`；否則 `upcoming`（ref = `q + early` 之後的第一個場次）。

- [ ] **Step 1: 寫失敗測試**

`tests/test_routine_status.py`：

```python
from datetime import date

from routine_core.schedule import Schedule
from routine_core.status import day_status

WED_SAT = Schedule("weekly", days=(2, 5))
START = date(2026, 10, 1)


def d(text):
    return date.fromisoformat(text)


def ds(sch, done, q, skips=(), early=1, late=2, start=START):
    return day_status(sch, early, late, start, [d(x) for x in done], {d(s) for s in skips}, d(q))


def test_daily():
    sch = Schedule("daily")
    assert ds(sch, ["2026-10-14"], "2026-10-14").state == "done"
    st = ds(sch, ["2026-10-12"], "2026-10-14")
    assert st.state == "not_done" and st.last_done == d("2026-10-12")
    assert ds(sch, [], "2026-10-14", skips=["2026-10-14"]).state == "skipped"


def test_none():
    sch = Schedule("none")
    assert ds(sch, ["2026-10-14", "2026-10-14"], "2026-10-14").state == "done"
    st = ds(sch, ["2026-10-07"], "2026-10-14")
    assert st.state == "idle" and st.last_done == d("2026-10-07")
    assert ds(sch, [], "2026-10-14").last_done is None


def test_interval():
    sch = Schedule("interval", n=14)
    assert ds(sch, [], "2026-10-14").state == "never_done"
    st = ds(sch, ["2026-09-19"], "2026-10-14")
    assert (st.state, st.ref, st.last_done) == ("due", d("2026-10-03"), d("2026-09-19"))
    st = ds(sch, ["2026-10-10"], "2026-10-14")
    assert (st.state, st.ref) == ("upcoming", d("2026-10-24"))
    st = ds(sch, ["2026-09-19", "2026-10-14"], "2026-10-14")
    assert (st.state, st.ref) == ("done", d("2026-10-28"))


def test_interval_ignores_completions_after_the_day():
    st = ds(Schedule("interval", n=14), ["2026-09-19", "2026-10-20"], "2026-10-14")
    assert st.last_done == d("2026-09-19")


def test_weekly_due_today():
    st = ds(WED_SAT, ["2026-10-10"], "2026-10-14")
    assert (st.state, st.ref, st.last_done) == ("due", d("2026-10-14"), d("2026-10-10"))


def test_weekly_due_in_the_early_window():
    st = ds(WED_SAT, ["2026-10-10"], "2026-10-13")
    assert (st.state, st.ref) == ("due", d("2026-10-14"))


def test_weekly_upcoming():
    st = ds(WED_SAT, ["2026-10-10"], "2026-10-12")
    assert (st.state, st.ref) == ("upcoming", d("2026-10-14"))


def test_weekly_makeup():
    st = ds(WED_SAT, ["2026-10-07"], "2026-10-11")
    assert (st.state, st.ref) == ("makeup", d("2026-10-10"))


def test_weekly_missed_saturday_while_wednesday_is_due():
    st = ds(WED_SAT, ["2026-10-07"], "2026-10-13")
    assert (st.state, st.ref, st.missed) == ("due", d("2026-10-14"), [d("2026-10-10")])


def test_weekly_done_reports_its_settlement():
    st = ds(WED_SAT, ["2026-10-07", "2026-10-13"], "2026-10-13")
    assert st.state == "done"
    assert st.settlement.claimed == d("2026-10-14") and st.settlement.merged == [d("2026-10-10")]


def test_weekly_after_doing_it_early_the_next_day_is_the_one_after():
    st = ds(WED_SAT, ["2026-10-07", "2026-10-13"], "2026-10-14")
    assert (st.state, st.ref, st.missed) == ("upcoming", d("2026-10-17"), [])


def test_weekly_skipped_today():
    st = ds(WED_SAT, ["2026-10-10"], "2026-10-14", skips=["2026-10-14"])
    assert (st.state, st.ref) == ("skipped", d("2026-10-14"))


def test_weekly_only_missed():
    # weekly:mon only, nothing pending on Thu 10-08 after missing Mon 10-05
    st = ds(Schedule("weekly", days=(0,)), [], "2026-10-08", start=d("2026-10-05"))
    assert (st.state, st.ref) == ("missed", d("2026-10-05"))


def test_weekly_ignores_completions_long_before_start():
    st = ds(WED_SAT, ["2026-09-01"], "2026-10-14", start=d("2026-10-14"))
    assert (st.state, st.ref, st.last_done) == ("due", d("2026-10-14"), d("2026-09-01"))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_status.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'routine_core.status'`

- [ ] **Step 3: 實作 `status.py`**

```python
"""Where an item stands on a given day. Pure: no database, no clock."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from .schedule import Schedule, Settlement, evaluate_weekly


@dataclass
class DayStatus:
    state: str                    # done|not_done|skipped|idle|never_done|upcoming|due|makeup|missed
    ref: date | None = None       # the scheduled day (weekly) or due date (interval) the state is about
    last_done: date | None = None
    missed: list[date] = field(default_factory=list)
    settlement: Settlement | None = None


def _next_weekly(after: date, days: tuple[int, ...]) -> date:
    d = after + timedelta(days=1)
    while d.weekday() not in days:
        d += timedelta(days=1)
    return d


def day_status(sch: Schedule, early: int, late: int, start: date, done_days: list[date],
               skips: set[date], q: date) -> DayStatus:
    done = sorted(x for x in done_days if x <= q)
    last = done[-1] if done else None
    done_today = q in done
    if sch.kind == "daily":
        return DayStatus("done" if done_today else "skipped" if q in skips else "not_done", last_done=last)
    if sch.kind == "none":
        return DayStatus("done" if done_today else "idle", last_done=last)
    if sch.kind == "interval":
        if done_today:
            return DayStatus("done", ref=q + timedelta(days=sch.n), last_done=q)
        if last is None:
            return DayStatus("never_done")
        due = last + timedelta(days=sch.n)
        return DayStatus("upcoming" if q < due else "due", ref=due, last_done=last)
    counted = [x for x in done if x >= start - timedelta(days=early)]
    occ, settlements = evaluate_weekly(sch.days, early, late, counted, skips, start, q)
    missed = [o.day for o in occ if o.status == "missed"]
    if done_today:
        mine = [s for s in settlements if s.day == q]
        return DayStatus("done", last_done=q, missed=missed, settlement=mine[-1] if mine else None)
    pending = [o for o in occ if o.status in ("due", "makeup")]
    if pending:
        return DayStatus(pending[0].status, ref=pending[0].day, last_done=last, missed=missed)
    if missed:
        return DayStatus("missed", ref=missed[-1], last_done=last, missed=missed)
    if any(o.day == q and o.status == "skipped" for o in occ):
        return DayStatus("skipped", ref=q, last_done=last)
    # every scheduled day up to q + early is settled, so the next one comes after that
    return DayStatus("upcoming", ref=_next_weekly(q + timedelta(days=early), sch.days), last_done=last)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_status.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/routine-keeper/scripts/routine_core/status.py tests/test_routine_status.py
git commit -m "feat: routine-keeper day status for daily, none, interval, and weekly items"
```

---

### Task 6: 資料庫與存放位置

**Files:**
- Create: `src/routine-keeper/scripts/routine_core/db.py`
- Create: `src/routine-keeper/scripts/routine_core/storage.py`
- Create: `tests/test_routine_storage.py`

**Interfaces:**
- Consumes: `RkError`
- Produces:
  - `db.SCHEMA_VERSION = 1`、`db.TABLES: tuple[str, ...]`
  - `db.connect(path) -> sqlite3.Connection`（`row_factory = sqlite3.Row`，foreign keys on）
  - `db.init(conn, default_tz: str) -> None`（建表、寫入預設 meta；版本較新 → `data_version_newer`）
  - `db.get_meta(conn, key) -> str | None`、`db.set_meta(conn, key, value) -> None`
  - `storage.SKILL_ROOT: Path`（`routine_core/` 往上兩層）
  - `storage.CONFIG_NAME = "config.json"`、`storage.DB_NAME = "routine.db"`
  - `storage.load_config(root) -> dict`、`storage.save_config(root, cfg) -> None`（原子寫入）
  - `storage.data_dir(root) -> Path`
  - `storage.open_db(root, default_tz) -> sqlite3.Connection`（錯誤 → `data_unavailable`）

- [ ] **Step 1: 寫失敗測試**

`tests/test_routine_storage.py`：

```python
import json
import sqlite3

import pytest

from routine_core import db, storage
from routine_core.errors import RkError


def test_skill_root_is_two_levels_above_the_package():
    assert (storage.SKILL_ROOT / "scripts" / "routine_core" / "storage.py").is_file()


def test_default_data_dir_is_inside_the_skill(tmp_path):
    assert storage.data_dir(tmp_path) == tmp_path / "data"


def test_config_points_somewhere_else(tmp_path):
    storage.save_config(tmp_path, {"data_dir": str(tmp_path / "elsewhere")})
    assert storage.data_dir(tmp_path) == tmp_path / "elsewhere"
    assert json.loads((tmp_path / "config.json").read_text())["data_dir"].endswith("elsewhere")


def test_save_config_leaves_no_temp_files(tmp_path):
    storage.save_config(tmp_path, {"data_dir": "x"})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]


def test_broken_config_is_data_unavailable(tmp_path):
    (tmp_path / "config.json").write_text("{not json")
    with pytest.raises(RkError) as e:
        storage.data_dir(tmp_path)
    assert e.value.code == "data_unavailable"


def test_open_db_creates_schema_and_defaults(tmp_path):
    conn = storage.open_db(tmp_path, "Asia/Taipei")
    assert (tmp_path / "data" / "routine.db").is_file()
    assert db.get_meta(conn, "timezone") == "Asia/Taipei"
    assert db.get_meta(conn, "day_boundary") == "05:00"
    assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
    for table in db.TABLES:
        conn.execute(f"SELECT COUNT(*) FROM {table}")


def test_open_db_keeps_existing_settings(tmp_path):
    conn = storage.open_db(tmp_path, "Asia/Taipei")
    db.set_meta(conn, "timezone", "Europe/Paris")
    conn.commit()
    conn.close()
    assert db.get_meta(storage.open_db(tmp_path, "Asia/Taipei"), "timezone") == "Europe/Paris"


def test_newer_data_is_refused(tmp_path):
    conn = storage.open_db(tmp_path, "UTC")
    db.set_meta(conn, "schema_version", str(db.SCHEMA_VERSION + 1))
    conn.commit()
    conn.close()
    with pytest.raises(RkError) as e:
        storage.open_db(tmp_path, "UTC")
    assert e.value.code == "data_version_newer"


def test_corrupt_database_is_data_unavailable(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "routine.db").write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(RkError) as e:
        storage.open_db(tmp_path, "UTC")
    assert e.value.code == "data_unavailable"


def test_unwritable_data_dir_is_data_unavailable(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    storage.save_config(tmp_path, {"data_dir": str(blocker / "sub")})
    with pytest.raises(RkError) as e:
        storage.open_db(tmp_path, "UTC")
    assert e.value.code == "data_unavailable"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_storage.py -v`
Expected: FAIL，`ImportError: cannot import name 'db'`

- [ ] **Step 3: 實作 `db.py`**

```python
"""SQLite schema, and the settings stored with the data (meta)."""
import sqlite3

from .errors import RkError

SCHEMA_VERSION = 1
DEFAULT_BOUNDARY = "05:00"
TABLES = ("items", "aliases", "logs", "skips", "log_edits", "notes", "meta")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('chore', 'dose')),
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    schedule TEXT NOT NULL,
    window_early INTEGER NOT NULL,
    window_late INTEGER NOT NULL,
    slot TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    start_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aliases (
    key TEXT PRIMARY KEY,
    alias TEXT NOT NULL,
    item_id INTEGER NOT NULL REFERENCES items(id)
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    at TEXT NOT NULL,
    for_date TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS logs_item_day ON logs(item_id, for_date);
CREATE TABLE IF NOT EXISTS skips (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    for_date TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS log_edits (
    id INTEGER PRIMARY KEY,
    log_id INTEGER NOT NULL REFERENCES logs(id),
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    edited_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by_log INTEGER REFERENCES logs(id)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))


def init(conn, default_tz: str) -> None:
    conn.executescript(_SCHEMA)
    version = get_meta(conn, "schema_version")
    if version is not None and int(version) > SCHEMA_VERSION:
        raise RkError("data_version_newer", f"data v{version}, skill v{SCHEMA_VERSION}")
    for key, value in (("schema_version", str(SCHEMA_VERSION)), ("day_boundary", DEFAULT_BOUNDARY),
                       ("timezone", default_tz)):
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)", (key, value))
    conn.commit()
```

- [ ] **Step 4: 實作 `storage.py`（本 task 不含 data move）**

```python
"""Where the skill lives, its config.json, and where the data is."""
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from . import db
from .errors import RkError

SKILL_ROOT = Path(__file__).resolve().parents[2]   # routine_core/ -> scripts/ -> the skill folder
CONFIG_NAME = "config.json"
DB_NAME = "routine.db"


def load_config(root: Path) -> dict:
    path = Path(root) / CONFIG_NAME
    if not path.exists():
        return {}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RkError("data_unavailable", f"{path} is not valid JSON") from None
    if not isinstance(cfg, dict):
        raise RkError("data_unavailable", f"{path} is not a JSON object")
    return cfg


def save_config(root: Path, cfg: dict) -> None:
    """Write to a temp file, then rename: a crash never leaves a half-written config."""
    root = Path(root)
    fd, tmp = tempfile.mkstemp(dir=root, prefix=".config-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, root / CONFIG_NAME)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def data_dir(root: Path) -> Path:
    raw = load_config(root).get("data_dir")
    return Path(raw).expanduser() if raw else Path(root) / "data"


def open_db(root: Path, default_tz: str) -> sqlite3.Connection:
    d = data_dir(root)
    try:
        d.mkdir(parents=True, exist_ok=True)
        conn = db.connect(d / DB_NAME)
        db.init(conn, default_tz)
    except RkError:
        raise
    except (OSError, sqlite3.Error) as e:
        raise RkError("data_unavailable", f"{d}: {type(e).__name__}") from None
    return conn
```

- [ ] **Step 5: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_storage.py -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add src/routine-keeper/scripts/routine_core/db.py src/routine-keeper/scripts/routine_core/storage.py tests/test_routine_storage.py
git commit -m "feat: routine-keeper database schema, config file, and data location"
```

---

### Task 7: 項目管理、CLI 入口、config

**Files:**
- Create: `src/routine-keeper/scripts/routine_core/items.py`
- Create: `src/routine-keeper/scripts/routine_core/context.py`
- Create: `src/routine-keeper/scripts/routine_core/cmd_items.py`
- Create: `src/routine-keeper/scripts/routine_core/cmd_admin.py`（本 task 只有 config）
- Create: `src/routine-keeper/scripts/routine.py`
- Create: `tests/rk_helpers.py`
- Create: `tests/test_routine_items.py`

**Interfaces:**
- Consumes: Task 1–6 全部
- Produces:
  - `items.find_item(conn, ref) -> sqlite3.Row`（不分大小寫、壓縮空白，比對 name 與 alias；找不到 → `unknown_item`，detail 列出 active 項目名稱）
  - `items.add_item(conn, *, kind, name, schedule, window, slot, aliases, today, now) -> int`
  - `items.edit_item(conn, ref, *, name=None, schedule=None, window=None, slot=None, add_aliases=(), remove_aliases=(), today, now) -> sqlite3.Row`（schedule 或 window 改變時 `start_date` 重設為 today）
  - `items.set_active(conn, ref, active: bool, now) -> sqlite3.Row`
  - `items.list_items(conn, kind=None, include_paused=False) -> list[sqlite3.Row]`
  - `items.aliases_of(conn, item_id) -> list[str]`
  - `items.describe_item(item, aliases) -> str`
  - `items.item_data(item, aliases) -> dict`
  - `context.Ctx(conn, root, now, tz, boundary)`，property `today`，classmethod `build(conn, root, now)`
  - `context.Result(lines: list[str], data: dict)`
  - `routine.main(argv=None, *, now=None, root=None, default_tz=None) -> int`
  - `routine.build_parser() -> argparse.ArgumentParser`
  - `tests/rk_helpers.py`：`NOW`（2026-10-14 16:20 台北）、`at_tpe(text) -> datetime`（UTC aware）、fixture `root`、`run(root, capsys, *argv, now=NOW) -> (code, out)`

- [ ] **Step 1: 寫共用測試工具**

`tests/rk_helpers.py`：

```python
"""Shared bits for the routine-keeper tests. Import the fixture by name: from rk_helpers import root."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

import routine

TPE = ZoneInfo("Asia/Taipei")
# 2026-10-14 08:20 UTC = 2026-10-14 16:20 Wed in Taipei
NOW = datetime(2026, 10, 14, 8, 20, tzinfo=timezone.utc)


def at_tpe(text: str) -> datetime:
    """'2026-10-14 16:20' in Taipei, as an aware UTC datetime for main(now=...)."""
    return datetime.fromisoformat(text).replace(tzinfo=TPE).astimezone(timezone.utc)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "routine-keeper"
    r.mkdir()
    return r


def run(root, capsys, *argv, now=NOW):
    code = routine.main(list(argv), now=now, root=root, default_tz="Asia/Taipei")
    return code, capsys.readouterr().out.strip()
```

- [ ] **Step 2: 寫失敗測試**

`tests/test_routine_items.py`：

```python
import json

import routine
from rk_helpers import run, root  # noqa: F401  (root is a fixture)


def test_add_a_dose_defaults_to_daily(root, capsys):
    code, out = run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D", "--slot", "after breakfast")
    assert code == 0
    assert out.splitlines() == [
        "ok: added Vitamin D (dose)",
        "confirm: Vitamin D, dose, every day, slot: after breakfast",
    ]


def test_add_a_chore_defaults_to_no_schedule(root, capsys):
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "Litter box")
    assert out.splitlines()[-1] == "confirm: Litter box, chore, no schedule, log only"


def test_add_weekly_with_window_and_aliases(root, capsys):
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry",
                    "--schedule", "weekly:sat,wed", "--alias", "washing", "--alias", "Clothes")
    assert code == 0
    assert out.splitlines()[-1] == (
        "confirm: Laundry, chore, every Wed and Sat, can be done 1 day early or 2 days late, "
        "also called: washing, Clothes")


def test_names_ignore_case_and_extra_spaces(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "魚油 EX")
    code, out = run(root, capsys, "item", "edit", "魚油   ex", "--slot", "bedtime")
    assert code == 0 and "slot: bedtime" in out
    code, out = run(root, capsys, "item", "add", "--kind", "dose", "--name", "魚油 ex")
    assert code == 2 and out.startswith("error: name_taken")


def test_alias_cannot_take_another_items_name(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry")
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "Sheets", "--alias", "laundry")
    assert code == 2 and out.startswith("error: name_taken")
    code, out = run(root, capsys, "item", "list", "--all")
    assert "Sheets" not in out  # nothing half-saved


def test_unknown_item_lists_existing_names(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D")
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium")
    code, out = run(root, capsys, "item", "edit", "Vitamin", "--slot", "x")
    assert code == 2
    assert out.splitlines()[0] == 'error: unknown_item (no item named "Vitamin"; existing: Magnesium, Vitamin D)'
    assert out.splitlines()[1].startswith("action: ")


def test_edit_schedule_window_name_and_aliases(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--alias", "washing")
    code, out = run(root, capsys, "item", "edit", "washing", "--name", "Wash", "--schedule", "weekly:wed",
                    "--window", "-0,+1", "--alias", "laundry", "--remove-alias", "washing")
    assert code == 0
    assert out.splitlines() == [
        "ok: updated Wash",
        "confirm: Wash, chore, every Wed, can be done 0 days early or 1 day late, also called: laundry",
    ]


def test_remove_unknown_alias(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry")
    code, out = run(root, capsys, "item", "edit", "Laundry", "--remove-alias", "nope")
    assert code == 2 and out.startswith("error: unknown_alias")


def test_bad_schedule_and_window(root, capsys):
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "X", "--schedule", "monthly:1")
    assert code == 1 and out.startswith("error: bad_schedule")
    code, out = run(root, capsys, "item", "add", "--kind", "chore", "--name", "X", "--window", "1,2")
    assert code == 1 and out.startswith("error: bad_window")


def test_pause_resume_and_list(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat")
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D", "--slot", "after breakfast", "--alias", "D3")
    code, out = run(root, capsys, "item", "pause", "laundry")
    assert out.splitlines() == ["ok: paused Laundry", "confirm: Laundry, chore, every Wed and Sat, can be done 1 day early or 2 days late, paused"]
    code, out = run(root, capsys, "item", "list")
    assert out.splitlines() == ["- Vitamin D (dose) daily | slot: after breakfast | also: D3"]
    code, out = run(root, capsys, "item", "list", "--all")
    assert "- Laundry (chore) weekly:wed,sat window -1,+2 [paused]" in out.splitlines()
    run(root, capsys, "item", "resume", "Laundry")
    code, out = run(root, capsys, "item", "list", "--kind", "chore")
    assert out.splitlines() == ["- Laundry (chore) weekly:wed,sat window -1,+2"]


def test_empty_list(root, capsys):
    assert run(root, capsys, "item", "list") == (0, "items: none yet")


def test_config_show_and_set(root, capsys):
    code, out = run(root, capsys, "config", "show")
    assert code == 0
    assert f"data_dir: {root / 'data'}" in out.splitlines()
    assert "timezone: Asia/Taipei" in out.splitlines()
    assert "day_boundary: 05:00" in out.splitlines()
    code, out = run(root, capsys, "config", "set", "day-boundary", "4:30")
    assert out.splitlines() == [
        "ok: day_boundary set to 04:30",
        "confirm: a new day starts at 04:30; anything logged before that counts for the previous day; past records keep their day",
    ]
    code, out = run(root, capsys, "config", "set", "timezone", "Europe/Paris")
    assert out.splitlines()[0] == "ok: timezone set to Europe/Paris"
    code, out = run(root, capsys, "config", "set", "timezone", "Mars/Base")
    assert code == 1 and out.startswith("error: bad_setting")


def test_json_output(root, capsys):
    code, out = run(root, capsys, "--json", "item", "add", "--kind", "dose", "--name", "Vitamin D")
    data = json.loads(out)
    assert data["ok"] is True and data["item"]["name"] == "Vitamin D" and data["item"]["schedule"] == "daily"
    assert data["confirm"] == "Vitamin D, dose, every day"
    code, out = run(root, capsys, "item", "edit", "nope", "--slot", "x", "--json")
    assert code == 2 and json.loads(out)["error"] == "unknown_item"


def test_bad_arguments_never_print_usage(root, capsys):
    code, out = run(root, capsys, "item", "add", "--name", "X")
    assert code == 1 and out.startswith("error: bad_arguments")
    code, out = run(root, capsys, "fly")
    assert code == 1 and out.startswith("error: bad_arguments")
    assert capsys.readouterr().err == ""


def test_version(root, capsys):
    code, out = run(root, capsys, "--version")
    assert code == 0 and out.startswith("routine-keeper 1.0.0")


def test_unexpected_exception_never_shows_traceback(root, capsys, monkeypatch):
    from routine_core import cmd_items
    monkeypatch.setattr(cmd_items, "item_list", lambda ctx, a: 1 / 0)
    code, out = run(root, capsys, "item", "list")
    assert code == 1
    assert out.splitlines()[0] == "error: internal_error (ZeroDivisionError)"
    assert "Traceback" not in out


def test_errors_roll_back(root, capsys, monkeypatch):
    from routine_core import cmd_items
    real = cmd_items.item_add

    def add_then_fail(ctx, a):
        real(ctx, a)
        raise ZeroDivisionError
    monkeypatch.setattr(cmd_items, "item_add", add_then_fail)
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D")
    monkeypatch.undo()
    assert run(root, capsys, "item", "list") == (0, "items: none yet")
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_items.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'routine'`

- [ ] **Step 4: 實作 `items.py`**

```python
"""Tracked items (chores and doses), their names, aliases, and schedules."""
from .errors import RkError
from .schedule import describe, format_schedule, parse_schedule, parse_window

DEFAULT_SCHEDULE = {"chore": "none", "dose": "daily"}
DEFAULT_WINDOW = (1, 2)


def _clean(text: str, what: str = "name") -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        raise RkError("bad_arguments", f"empty {what}")
    return cleaned


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _owner(conn, key: str) -> int | None:
    row = (conn.execute("SELECT id FROM items WHERE name_key=?", (key,)).fetchone()
           or conn.execute("SELECT item_id AS id FROM aliases WHERE key=?", (key,)).fetchone())
    return row["id"] if row else None


def _claim(conn, name: str, item_id: int | None = None) -> None:
    owner = _owner(conn, _key(name))
    if owner is not None and owner != item_id:
        raise RkError("name_taken", name)


def _get(conn, item_id: int):
    return conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()


def find_item(conn, ref: str):
    item_id = _owner(conn, _key(ref))
    if item_id is None:
        names = [r["name"] for r in conn.execute("SELECT name FROM items WHERE active=1 ORDER BY name")]
        raise RkError("unknown_item", f'no item named "{ref}"; existing: {", ".join(names) or "none yet"}')
    return _get(conn, item_id)


def aliases_of(conn, item_id: int) -> list[str]:
    return [r["alias"] for r in conn.execute("SELECT alias FROM aliases WHERE item_id=? ORDER BY rowid", (item_id,))]


def _add_alias(conn, item, alias: str) -> None:
    alias = _clean(alias, "alias")
    _claim(conn, alias, item["id"])
    if _key(alias) != item["name_key"]:
        conn.execute("INSERT OR IGNORE INTO aliases(key, alias, item_id) VALUES (?, ?, ?)",
                     (_key(alias), alias, item["id"]))


def add_item(conn, *, kind, name, schedule, window, slot, aliases, today, now) -> int:
    name = _clean(name)
    _claim(conn, name)
    sch = format_schedule(parse_schedule(schedule or DEFAULT_SCHEDULE[kind]))
    early, late = parse_window(window) if window else DEFAULT_WINDOW
    ts = now.isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO items(kind, name, name_key, schedule, window_early, window_late, slot, start_date,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (kind, name, _key(name), sch, early, late, (slot or "").strip() or None, today.isoformat(), ts, ts))
    item = _get(conn, cur.lastrowid)
    for alias in aliases:
        _add_alias(conn, item, alias)
    return item["id"]


def edit_item(conn, ref, *, name=None, schedule=None, window=None, slot=None, add_aliases=(), remove_aliases=(),
              today, now):
    item = find_item(conn, ref)
    changes = {}
    if name is not None:
        name = _clean(name)
        _claim(conn, name, item["id"])
        conn.execute("DELETE FROM aliases WHERE key=? AND item_id=?", (_key(name), item["id"]))
        changes.update(name=name, name_key=_key(name))
    if schedule is not None:
        changes["schedule"] = format_schedule(parse_schedule(schedule))
    if window is not None:
        changes["window_early"], changes["window_late"] = parse_window(window)
    if slot is not None:
        changes["slot"] = slot.strip() or None
    rule_changed = any(k in changes and changes[k] != item[k] for k in ("schedule", "window_early", "window_late"))
    if rule_changed:
        changes["start_date"] = today.isoformat()   # judge the new rule from today on, not against old history
    if changes:
        changes["updated_at"] = now.isoformat(timespec="seconds")
        conn.execute(f"UPDATE items SET {', '.join(f'{k}=?' for k in changes)} WHERE id=?",
                     (*changes.values(), item["id"]))
    for alias in remove_aliases:
        if conn.execute("DELETE FROM aliases WHERE key=? AND item_id=?", (_key(alias), item["id"])).rowcount == 0:
            raise RkError("unknown_alias", f'"{alias}" is not an alias of {item["name"]}')
    item = _get(conn, item["id"])
    for alias in add_aliases:
        _add_alias(conn, item, alias)
    return item


def set_active(conn, ref, active: bool, now):
    item = find_item(conn, ref)
    conn.execute("UPDATE items SET active=?, updated_at=? WHERE id=?",
                 (int(active), now.isoformat(timespec="seconds"), item["id"]))
    return _get(conn, item["id"])


def list_items(conn, kind=None, include_paused=False):
    sql, args = "SELECT * FROM items WHERE 1=1", []
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if not include_paused:
        sql += " AND active=1"
    return conn.execute(sql + " ORDER BY kind DESC, name", args).fetchall()


def describe_item(item, aliases: list[str]) -> str:
    parts = [item["name"], item["kind"],
             describe(parse_schedule(item["schedule"]), item["window_early"], item["window_late"])]
    if item["slot"]:
        parts.append(f"slot: {item['slot']}")
    if aliases:
        parts.append("also called: " + ", ".join(aliases))
    if not item["active"]:
        parts.append("paused")
    return ", ".join(parts)


def item_data(item, aliases: list[str]) -> dict:
    return {"id": item["id"], "name": item["name"], "kind": item["kind"], "schedule": item["schedule"],
            "window": [item["window_early"], item["window_late"]], "slot": item["slot"],
            "aliases": aliases, "active": bool(item["active"])}
```

註：`list_items` 依 `kind DESC` 排序，所以 dose 在 chore 前面（`"dose" > "chore"`）。`find_item` 錯誤訊息裡的名稱依字母排序。

- [ ] **Step 5: 實作 `context.py`**

```python
"""What every command gets: the open database, the time, and the day settings."""
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from . import db
from .dates import day_of, parse_boundary, zone


@dataclass
class Ctx:
    conn: object
    root: Path
    now: datetime        # aware, in the configured timezone, seconds dropped
    tz: ZoneInfo
    boundary: time

    @property
    def today(self) -> date:
        return day_of(self.now, self.boundary)

    @classmethod
    def build(cls, conn, root: Path, now: datetime) -> "Ctx":
        tz = zone(db.get_meta(conn, "timezone"))
        boundary = parse_boundary(db.get_meta(conn, "day_boundary"))
        return cls(conn, root, now.astimezone(tz).replace(second=0, microsecond=0), tz, boundary)


@dataclass
class Result:
    lines: list[str]
    data: dict = field(default_factory=dict)
```

- [ ] **Step 6: 實作 `cmd_items.py`**

```python
"""item add | edit | pause | resume | list"""
from .context import Ctx, Result
from .items import add_item, aliases_of, describe_item, edit_item, item_data, list_items, set_active


def _confirmed(ctx: Ctx, item, head: str) -> Result:
    aliases = aliases_of(ctx.conn, item["id"])
    text = describe_item(item, aliases)
    return Result([head, f"confirm: {text}"], {"ok": True, "item": item_data(item, aliases), "confirm": text})


def item_add(ctx: Ctx, a) -> Result:
    item_id = add_item(ctx.conn, kind=a.kind, name=a.name, schedule=a.schedule, window=a.window, slot=a.slot,
                       aliases=a.alias, today=ctx.today, now=ctx.now)
    item = ctx.conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return _confirmed(ctx, item, f"ok: added {item['name']} ({item['kind']})")


def item_edit(ctx: Ctx, a) -> Result:
    item = edit_item(ctx.conn, a.item, name=a.name, schedule=a.schedule, window=a.window, slot=a.slot,
                     add_aliases=a.alias, remove_aliases=a.remove_alias, today=ctx.today, now=ctx.now)
    return _confirmed(ctx, item, f"ok: updated {item['name']}")


def item_pause(ctx: Ctx, a) -> Result:
    item = set_active(ctx.conn, a.item, False, ctx.now)
    return _confirmed(ctx, item, f"ok: paused {item['name']}")


def item_resume(ctx: Ctx, a) -> Result:
    item = set_active(ctx.conn, a.item, True, ctx.now)
    return _confirmed(ctx, item, f"ok: resumed {item['name']}")


def item_list(ctx: Ctx, a) -> Result:
    rows = list_items(ctx.conn, kind=a.kind, include_paused=a.all)
    lines, data = [], []
    for item in rows:
        aliases = aliases_of(ctx.conn, item["id"])
        line = f"- {item['name']} ({item['kind']}) {item['schedule']}"
        if item["schedule"].startswith("weekly:"):
            line += f" window -{item['window_early']},+{item['window_late']}"
        if item["slot"]:
            line += f" | slot: {item['slot']}"
        if aliases:
            line += " | also: " + ", ".join(aliases)
        if not item["active"]:
            line += " [paused]"
        lines.append(line)
        data.append(item_data(item, aliases))
    return Result(lines or ["items: none yet"], {"items": data})
```

- [ ] **Step 7: 實作 `cmd_admin.py`（config 部分）**

```python
"""config show | set, data where | move, export"""
from . import VERSION, db, storage
from .context import Ctx, Result
from .dates import parse_boundary, zone


def config_show(ctx: Ctx, a) -> Result:
    d = storage.data_dir(ctx.root)
    data = {"data_dir": str(d), "database": str(d / storage.DB_NAME), "timezone": db.get_meta(ctx.conn, "timezone"),
            "day_boundary": db.get_meta(ctx.conn, "day_boundary"), "version": VERSION}
    return Result([f"{k}: {v}" for k, v in data.items()], data)


def config_set(ctx: Ctx, a) -> Result:
    if a.key == "day-boundary":
        value = parse_boundary(a.value).strftime("%H:%M")
        db.set_meta(ctx.conn, "day_boundary", value)
        confirm = (f"a new day starts at {value}; anything logged before that counts for the previous day; "
                   "past records keep their day")
        key = "day_boundary"
    else:
        value = zone(a.value.strip()).key
        db.set_meta(ctx.conn, "timezone", value)
        confirm = f"times are now read and shown in {value}; past records keep their day"
        key = "timezone"
    return Result([f"ok: {key} set to {value}", f"confirm: {confirm}"], {"ok": True, key: value, "confirm": confirm})
```

- [ ] **Step 8: 實作 `routine.py`**

```python
#!/usr/bin/env python3
# routine-keeper · Copyright (c) 2026 SmallYuan · MIT License · https://github.com/SmallYuanSY/skills
"""Chores and supplements for an agent to log and check. Output is written for the agent to read.

  routine.py item add|edit|pause|resume|list
  routine.py done | skip | time
  routine.py log list|edit|delete|restore
  routine.py note add|list|resolve
  routine.py config show|set
  routine.py data where|move
  routine.py export
  global: --json, --version
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routine_core import REPO, VERSION, cmd_admin, cmd_items, storage  # noqa: E402
from routine_core.context import Ctx, Result  # noqa: E402
from routine_core.dates import system_timezone  # noqa: E402
from routine_core.errors import RkError, error_data, render_error  # noqa: E402

VERSION_LINE = f"routine-keeper {VERSION} · by SmallYuan · {REPO}"


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RkError("bad_arguments", message)


def build_parser() -> Parser:
    p = Parser(prog="routine.py")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)

    item = sub.add_parser("item").add_subparsers(dest="sub", required=True, parser_class=Parser)
    add = item.add_parser("add")
    add.add_argument("--kind", required=True, choices=["chore", "dose"])
    add.add_argument("--name", required=True)
    add.add_argument("--schedule")
    add.add_argument("--window")
    add.add_argument("--slot")
    add.add_argument("--alias", action="append", default=[])
    edit = item.add_parser("edit")
    edit.add_argument("item")
    edit.add_argument("--name")
    edit.add_argument("--schedule")
    edit.add_argument("--window")
    edit.add_argument("--slot")
    edit.add_argument("--alias", action="append", default=[])
    edit.add_argument("--remove-alias", action="append", default=[])
    for name in ("pause", "resume"):
        item.add_parser(name).add_argument("item")
    lst = item.add_parser("list")
    lst.add_argument("--kind", choices=["chore", "dose"])
    lst.add_argument("--all", action="store_true")

    config = sub.add_parser("config").add_subparsers(dest="sub", required=True, parser_class=Parser)
    config.add_parser("show")
    cset = config.add_parser("set")
    cset.add_argument("key", choices=["day-boundary", "timezone"])
    cset.add_argument("value")
    return p


HANDLERS = {
    ("item", "add"): cmd_items.item_add,
    ("item", "edit"): cmd_items.item_edit,
    ("item", "pause"): cmd_items.item_pause,
    ("item", "resume"): cmd_items.item_resume,
    ("item", "list"): cmd_items.item_list,
    ("config", "show"): cmd_admin.config_show,
    ("config", "set"): cmd_admin.config_set,
}


def _handler(args):
    """Looked up at call time so tests can patch a command module."""
    fn = HANDLERS[(args.cmd, getattr(args, "sub", None))]
    return getattr(sys.modules[fn.__module__], fn.__name__)


def _print(result: Result, as_json: bool) -> None:
    print(json.dumps(result.data, ensure_ascii=False, indent=2) if as_json else "\n".join(result.lines))


def _print_error(err: RkError, as_json: bool) -> None:
    print(json.dumps(error_data(err), ensure_ascii=False, indent=2) if as_json else render_error(err))


def main(argv=None, *, now=None, root=None, default_tz=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    as_json = "--json" in argv
    argv = [x for x in argv if x != "--json"]
    root = Path(root) if root else storage.SKILL_ROOT
    now = now or datetime.now(timezone.utc)
    conn = None
    try:
        if argv == ["--version"]:
            result = Result([VERSION_LINE], {"version": VERSION})
        else:
            args = build_parser().parse_args(argv)
            if args.cmd == "data":
                result = cmd_admin.data_command(args, root=root, now=now, default_tz=default_tz or system_timezone())
            else:
                conn = storage.open_db(root, default_tz or system_timezone())
                result = _handler(args)(Ctx.build(conn, root, now), args)
                conn.commit()
    except SystemExit as e:   # --help printed its text
        return e.code if isinstance(e.code, int) else 0
    except RkError as e:
        _print_error(e, as_json)
        return e.exit_code
    except Exception as e:   # never show the agent a traceback
        _print_error(RkError("internal_error", type(e).__name__), as_json)
        return 1
    finally:
        if conn is not None:
            conn.rollback()   # no-op after a commit; drops half-done writes after an error
            conn.close()
    _print(result, as_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`cmd_admin.data_command` 在 Task 10 才實作；本 task 先在 `cmd_admin.py` 檔尾加上暫時版本，讓 import 成立：

```python
def data_command(args, *, root, now, default_tz) -> Result:
    raise RkError("bad_arguments", "data commands are not available yet")
```

並在 `cmd_admin.py` 開頭加上 `from .errors import RkError`。（Task 10 會整個換掉 `data_command`。）

- [ ] **Step 9: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_items.py -v`
Expected: 全部 PASS

- [ ] **Step 10: 跑全部測試**

Run: `uv run pytest -m "not live"`
Expected: 全部 PASS

- [ ] **Step 11: Commit**

```bash
git add src/routine-keeper/scripts tests/rk_helpers.py tests/test_routine_items.py
git commit -m "feat: routine-keeper CLI with item and config commands"
```

---

### Task 8: 記錄完成、跳過、紀錄修改、提醒

**Files:**
- Create: `src/routine-keeper/scripts/routine_core/logs.py`
- Create: `src/routine-keeper/scripts/routine_core/notes.py`
- Create: `src/routine-keeper/scripts/routine_core/cmd_logs.py`
- Modify: `src/routine-keeper/scripts/routine.py`（`build_parser` 與 `HANDLERS`）
- Create: `tests/test_routine_logs.py`

**Interfaces:**
- Consumes: `find_item`、`Ctx`、`Result`、`day_of`、`parse_at`、`parse_day`、`day_status`、`parse_schedule`
- Produces:
  - `logs.check_not_future(at, for_date, now, today) -> None`（錯誤 `future_time`）
  - `logs.logs_on(conn, item_id, day) -> list[Row]`
  - `logs.add_log(conn, item, *, at, for_date, note, force, now, today) -> int`
  - `logs.done_days(conn, item_id, until) -> list[date]`
  - `logs.skip_days(conn, item_id) -> dict[date, str | None]`
  - `logs.add_skip(conn, item, *, for_date, reason, now, today) -> bool`、`logs.undo_skip(conn, item, *, for_date, now) -> bool`
  - `logs.get_log(conn, log_id, *, deleted: bool | None = False) -> Row`（含 `item_name`）
  - `logs.list_logs(conn, *, item_id=None, start=None, end=None, limit=50) -> list[Row]`
  - `logs.edit_log(conn, log_id, *, at=None, for_date=None, note=None, boundary, now, today) -> dict[str, tuple]`
  - `logs.delete_log(conn, log_id, now) -> Row`、`logs.restore_log(conn, log_id) -> Row`
  - `notes.add_note(conn, item, text, now) -> int`、`notes.open_notes(conn, item_id=None) -> list[Row]`
  - `notes.resolve_note(conn, note_id, now) -> Row`、`notes.resolve_for_item(conn, item_id, log_id, now) -> list[Row]`
  - `cmd_logs.item_status(ctx, item, q) -> DayStatus`（Task 9 也用）
  - `cmd_logs.done / skip / log_list / log_edit / log_delete / log_restore / note_add / note_list / note_resolve`

- [ ] **Step 1: 寫失敗測試**

`tests/test_routine_logs.py`：

```python
import json

from rk_helpers import at_tpe, run, root  # noqa: F401


def setup_items(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D", "--slot", "after breakfast")
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium", "--slot", "bedtime")
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat")
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Bed sheets", "--schedule", "interval:14")
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Litter box")


def test_done_now(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "vitamin d")
    assert code == 0
    assert out.splitlines() == ["ok: logged #1 Vitamin D for 2026-10-14 (Wed) at 2026-10-14 16:20"]


def test_after_midnight_counts_for_the_night_before(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "Magnesium", now=at_tpe("2026-10-15 02:30"))
    assert out == "ok: logged #1 Magnesium for 2026-10-14 (Wed) at 2026-10-15 02:30"


def test_done_earlier_with_at_and_for(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "Litter box", "--at", "2026-10-13 23:00", "--note", "all clean")
    assert out == "ok: logged #1 Litter box for 2026-10-13 (Tue) at 2026-10-13 23:00"
    code, out = run(root, capsys, "done", "Litter box", "--at", "2026-10-14 02:00", "--for", "2026-10-14")
    assert out.startswith("ok: logged #2 Litter box for 2026-10-14 (Wed)")


def test_never_log_ahead(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "Magnesium", "--at", "2026-10-14 23:00")
    assert code == 2 and out.startswith("error: future_time")
    code, out = run(root, capsys, "done", "Magnesium", "--for", "2026-10-15")
    assert code == 2 and out.startswith("error: future_time")
    code, out = run(root, capsys, "log", "list")
    assert out == "logs: none"


def test_a_dose_twice_in_one_day_needs_force(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-14 10:42")
    code, out = run(root, capsys, "done", "Vitamin D")
    assert code == 2
    assert out.splitlines()[0] == "error: already_logged (Vitamin D for 2026-10-14 as #1 at 10:42)"
    code, out = run(root, capsys, "done", "Vitamin D", "--force")
    assert code == 0


def test_a_chore_can_be_done_twice(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "done", "Litter box", "--at", "2026-10-14 09:00")
    assert run(root, capsys, "done", "Litter box")[0] == 0


def test_paused_item_cannot_be_logged(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "item", "pause", "Laundry")
    code, out = run(root, capsys, "done", "Laundry")
    assert code == 2 and out.startswith("error: item_paused")


def test_weekly_done_explains_what_it_settled(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Mop", "--schedule", "weekly:wed,sat",
        now=at_tpe("2026-10-07 09:00"))
    run(root, capsys, "done", "Mop", "--at", "2026-10-07 10:00", now=at_tpe("2026-10-07 10:00"))
    code, out = run(root, capsys, "done", "Mop", "--at", "2026-10-14 18:00", now=at_tpe("2026-10-14 18:20"))
    assert out.splitlines() == [
        "ok: logged #2 Mop for 2026-10-14 (Wed) at 2026-10-14 18:00",
        "schedule: counts for Wed 2026-10-14 (on the day)",
        "schedule: Sat 2026-10-10 merged into this",
    ]


def test_weekly_done_early_and_extra(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Mop", "--schedule", "weekly:wed",
        now=at_tpe("2026-10-07 09:00"))
    code, out = run(root, capsys, "done", "Mop", "--at", "2026-10-13 10:00", now=at_tpe("2026-10-13 10:00"))
    assert out.splitlines()[1:] == ["schedule: counts for Wed 2026-10-14 (1 day early)",
                                    "schedule: Wed 2026-10-07 merged into this"]
    code, out = run(root, capsys, "done", "Mop", "--at", "2026-10-13 11:00", now=at_tpe("2026-10-13 11:00"))
    assert out.splitlines()[1:] == ["schedule: extra (no scheduled day nearby)"]


def test_interval_done_reports_the_plan(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "done", "Bed sheets", "--at", "2026-09-19 12:00")
    assert out.splitlines()[1:] == ["schedule: first time; next due Sat 2026-10-03"]
    code, out = run(root, capsys, "done", "Bed sheets")
    assert out.splitlines()[1:] == ["schedule: planned for Sat 2026-10-03, done 11 days after; next due Wed 2026-10-28"]


def test_notes_are_resolved_by_done(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "note", "add", "laundry", "wash the jacket")
    assert out == "ok: note #1 on Laundry: wash the jacket (shown until Laundry is next logged)"
    run(root, capsys, "note", "add", "Laundry", "use less soap")
    code, out = run(root, capsys, "note", "list")
    assert out.splitlines() == ["#1 Laundry: wash the jacket (since 2026-10-14)",
                                "#2 Laundry: use less soap (since 2026-10-14)"]
    code, out = run(root, capsys, "done", "Laundry")
    assert out.splitlines()[-2:] == ["notes_resolved: #1 wash the jacket", "notes_resolved: #2 use less soap"]
    assert run(root, capsys, "note", "list") == (0, "notes: none open")


def test_keep_notes_and_resolve_by_hand(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "note", "add", "Laundry", "wash the jacket")
    code, out = run(root, capsys, "done", "Laundry", "--keep-notes")
    assert "notes_resolved" not in out
    assert run(root, capsys, "note", "resolve", "1") == (0, "ok: resolved note #1 (Laundry: wash the jacket)")
    code, out = run(root, capsys, "note", "resolve", "1")
    assert out == "ok: note #1 was already resolved"
    code, out = run(root, capsys, "note", "resolve", "9")
    assert code == 2 and out.startswith("error: unknown_note")


def test_skip(root, capsys):
    setup_items(root, capsys)
    code, out = run(root, capsys, "skip", "Laundry", "--for", "2026-10-14", "--reason", "too tired")
    assert out == "ok: skipped Laundry on Wed 2026-10-14 (too tired)"
    assert run(root, capsys, "skip", "Laundry", "--for", "2026-10-14")[1] == "ok: Laundry was already skipped on Wed 2026-10-14"
    assert run(root, capsys, "skip", "Laundry", "--for", "2026-10-14", "--undo")[1] == "ok: Laundry is no longer skipped on Wed 2026-10-14"
    code, out = run(root, capsys, "skip", "Laundry", "--for", "2026-10-13")
    assert code == 2 and out.startswith("error: not_scheduled")
    code, out = run(root, capsys, "skip", "Bed sheets", "--for", "2026-10-14")
    assert code == 2 and out.startswith("error: skip_not_applicable")
    code, out = run(root, capsys, "skip", "Vitamin D", "--for", "2026-10-15")
    assert code == 2 and out.startswith("error: future_time")


def test_log_list_edit_delete_restore(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-13 09:00", "--note", "with toast")
    run(root, capsys, "done", "Litter box", "--at", "2026-10-14 14:10")
    code, out = run(root, capsys, "log", "list")
    assert out.splitlines() == [
        "#2 2026-10-14 (Wed) Litter box at 2026-10-14 14:10",
        "#1 2026-10-13 (Tue) Vitamin D at 2026-10-13 09:00 | note: with toast",
    ]
    assert run(root, capsys, "log", "list", "--item", "vitamin d")[1].startswith("#1 ")
    assert run(root, capsys, "log", "list", "--from", "2026-10-14")[1].startswith("#2 ")
    assert run(root, capsys, "log", "list", "--limit", "1")[1].count("\n") == 0

    code, out = run(root, capsys, "log", "edit", "1", "--at", "2026-10-14 01:00")
    assert out.splitlines() == ["ok: edited #1 Vitamin D", "changed: at 2026-10-13T09:00+08:00 -> 2026-10-14T01:00+08:00"]
    code, out = run(root, capsys, "log", "edit", "1", "--for", "2026-10-14")
    assert out.splitlines()[1] == "changed: for_date 2026-10-13 -> 2026-10-14"
    assert run(root, capsys, "log", "edit", "1", "--note", "with toast")[1] == "ok: nothing changed on #1"
    code, out = run(root, capsys, "log", "edit", "1", "--for", "2026-10-20")
    assert code == 2 and out.startswith("error: future_time")

    assert run(root, capsys, "log", "delete", "2")[1] == "ok: deleted #2 Litter box (restore with: log restore 2)"
    assert "#2" not in run(root, capsys, "log", "list")[1]
    code, out = run(root, capsys, "log", "delete", "2")
    assert code == 2 and out.startswith("error: unknown_log")
    assert run(root, capsys, "log", "restore", "2")[1] == "ok: restored #2 Litter box"
    assert "#2" in run(root, capsys, "log", "list")[1]


def test_done_json(root, capsys):
    setup_items(root, capsys)
    run(root, capsys, "note", "add", "Laundry", "wash the jacket")
    code, out = run(root, capsys, "--json", "done", "Laundry")
    data = json.loads(out)
    assert data["log"]["id"] == 1 and data["log"]["for_date"] == "2026-10-14"
    assert data["notes_resolved"] == [{"id": 1, "text": "wash the jacket"}]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_logs.py -v`
Expected: FAIL，`error: bad_arguments (argument cmd: invalid choice: 'done' ...)`

- [ ] **Step 3: 實作 `logs.py`**

```python
"""Completions, skips, and fixes to past records. Deletes are soft and can be undone."""
from datetime import date

from .dates import day_of
from .errors import RkError


def _ts(now) -> str:
    return now.isoformat(timespec="seconds")


def check_not_future(at, for_date, now, today) -> None:
    if at is not None and at > now:
        raise RkError("future_time", f"{at:%Y-%m-%d %H:%M} is later than now ({now:%Y-%m-%d %H:%M})")
    if for_date is not None and for_date > today:
        raise RkError("future_time", f"{for_date} is after today ({today})")


def logs_on(conn, item_id: int, day: date):
    return conn.execute("SELECT * FROM logs WHERE item_id=? AND for_date=? AND deleted_at IS NULL ORDER BY at, id",
                        (item_id, day.isoformat())).fetchall()


def add_log(conn, item, *, at, for_date, note, force, now, today) -> int:
    check_not_future(at, for_date, now, today)
    if item["kind"] == "dose" and not force:
        same = logs_on(conn, item["id"], for_date)
        if same:
            raise RkError("already_logged",
                          f'{item["name"]} for {for_date} as #{same[0]["id"]} at {same[0]["at"][11:16]}')
    cur = conn.execute("INSERT INTO logs(item_id, at, for_date, note, created_at) VALUES (?, ?, ?, ?, ?)",
                       (item["id"], at.isoformat(timespec="minutes"), for_date.isoformat(), note, _ts(now)))
    return cur.lastrowid


def done_days(conn, item_id: int, until: date) -> list[date]:
    rows = conn.execute("SELECT for_date FROM logs WHERE item_id=? AND deleted_at IS NULL AND for_date<=?"
                        " ORDER BY for_date, at", (item_id, until.isoformat()))
    return [date.fromisoformat(r[0]) for r in rows]


def skip_days(conn, item_id: int) -> dict:
    rows = conn.execute("SELECT for_date, reason FROM skips WHERE item_id=? AND deleted_at IS NULL", (item_id,))
    return {date.fromisoformat(r["for_date"]): r["reason"] for r in rows}


def add_skip(conn, item, *, for_date, reason, now, today) -> bool:
    check_not_future(None, for_date, now, today)
    if for_date in skip_days(conn, item["id"]):
        return False
    conn.execute("INSERT INTO skips(item_id, for_date, reason, created_at) VALUES (?, ?, ?, ?)",
                 (item["id"], for_date.isoformat(), reason, _ts(now)))
    return True


def undo_skip(conn, item, *, for_date, now) -> bool:
    cur = conn.execute("UPDATE skips SET deleted_at=? WHERE item_id=? AND for_date=? AND deleted_at IS NULL",
                       (_ts(now), item["id"], for_date.isoformat()))
    return cur.rowcount > 0


def get_log(conn, log_id: int, *, deleted: bool | None = False):
    sql = "SELECT logs.*, items.name AS item_name FROM logs JOIN items ON items.id = logs.item_id WHERE logs.id=?"
    if deleted is True:
        sql += " AND logs.deleted_at IS NOT NULL"
    elif deleted is False:
        sql += " AND logs.deleted_at IS NULL"
    row = conn.execute(sql, (log_id,)).fetchone()
    if row is None:
        raise RkError("unknown_log", f"#{log_id}" + (" is not deleted" if deleted is True else ""))
    return row


def list_logs(conn, *, item_id=None, start=None, end=None, limit=50):
    sql = ("SELECT logs.*, items.name AS item_name FROM logs JOIN items ON items.id = logs.item_id"
           " WHERE logs.deleted_at IS NULL")
    args = []
    if item_id is not None:
        sql += " AND logs.item_id=?"
        args.append(item_id)
    if start is not None:
        sql += " AND logs.for_date>=?"
        args.append(start.isoformat())
    if end is not None:
        sql += " AND logs.for_date<=?"
        args.append(end.isoformat())
    sql += " ORDER BY logs.for_date DESC, logs.at DESC, logs.id DESC LIMIT ?"
    args.append(max(1, limit))
    return conn.execute(sql, args).fetchall()


def edit_log(conn, log_id: int, *, at=None, for_date=None, note=None, boundary, now, today) -> dict:
    row = get_log(conn, log_id)
    if at is not None and for_date is None:
        for_date = day_of(at, boundary)
    check_not_future(at, for_date, now, today)
    new = {}
    if at is not None:
        new["at"] = at.isoformat(timespec="minutes")
    if for_date is not None:
        new["for_date"] = for_date.isoformat()
    if note is not None:
        new["note"] = note.strip() or None
    changes = {k: (row[k], v) for k, v in new.items() if row[k] != v}
    for field_name, (old, value) in changes.items():
        conn.execute(f"UPDATE logs SET {field_name}=? WHERE id=?", (value, log_id))
        conn.execute("INSERT INTO log_edits(log_id, field, old_value, new_value, edited_at) VALUES (?, ?, ?, ?, ?)",
                     (log_id, field_name, old, value, _ts(now)))
    return changes


def delete_log(conn, log_id: int, now):
    row = get_log(conn, log_id)
    conn.execute("UPDATE logs SET deleted_at=? WHERE id=?", (_ts(now), log_id))
    return row


def restore_log(conn, log_id: int):
    row = get_log(conn, log_id, deleted=True)
    conn.execute("UPDATE logs SET deleted_at=NULL WHERE id=?", (log_id,))
    return row
```

- [ ] **Step 4: 實作 `notes.py`**

```python
"""Reminders attached to an item, shown until the item is next logged."""
from .errors import RkError


def add_note(conn, item, text: str, now) -> int:
    text = " ".join(text.split())
    if not text:
        raise RkError("bad_arguments", "empty note")
    cur = conn.execute("INSERT INTO notes(item_id, text, created_at) VALUES (?, ?, ?)",
                       (item["id"], text, now.isoformat(timespec="seconds")))
    return cur.lastrowid


def open_notes(conn, item_id=None):
    sql = ("SELECT notes.*, items.name AS item_name FROM notes JOIN items ON items.id = notes.item_id"
           " WHERE notes.resolved_at IS NULL")
    args = []
    if item_id is not None:
        sql += " AND notes.item_id=?"
        args.append(item_id)
    return conn.execute(sql + " ORDER BY notes.id", args).fetchall()


def resolve_note(conn, note_id: int, now):
    row = conn.execute("SELECT notes.*, items.name AS item_name FROM notes JOIN items ON items.id = notes.item_id"
                       " WHERE notes.id=?", (note_id,)).fetchone()
    if row is None:
        raise RkError("unknown_note", f"#{note_id}")
    if row["resolved_at"] is None:
        conn.execute("UPDATE notes SET resolved_at=? WHERE id=?", (now.isoformat(timespec="seconds"), note_id))
    return row


def resolve_for_item(conn, item_id: int, log_id: int, now):
    rows = open_notes(conn, item_id)
    conn.execute("UPDATE notes SET resolved_at=?, resolved_by_log=? WHERE item_id=? AND resolved_at IS NULL",
                 (now.isoformat(timespec="seconds"), log_id, item_id))
    return rows
```

- [ ] **Step 5: 實作 `cmd_logs.py`**

```python
"""done, skip, log list|edit|delete|restore, note add|list|resolve"""
from datetime import date, timedelta

from .context import Ctx, Result
from .dates import day_of, long_day, parse_at, parse_day, plural, short_day
from .errors import RkError
from .items import find_item
from .logs import (add_log, add_skip, delete_log, done_days, edit_log, get_log, list_logs, restore_log,
                   skip_days, undo_skip)
from .notes import add_note, open_notes, resolve_for_item, resolve_note
from .schedule import parse_schedule
from .status import DayStatus, day_status


def item_status(ctx: Ctx, item, q: date) -> DayStatus:
    return day_status(parse_schedule(item["schedule"]), item["window_early"], item["window_late"],
                      date.fromisoformat(item["start_date"]), done_days(ctx.conn, item["id"], q),
                      set(skip_days(ctx.conn, item["id"])), q)


def _offset_text(offset: int) -> str:
    if offset == 0:
        return "on the day"
    return f"{plural(abs(offset), 'day')} {'early' if offset < 0 else 'late'}"


def _schedule_lines(ctx: Ctx, item, for_date: date) -> list[str]:
    sch = parse_schedule(item["schedule"])
    if sch.kind == "interval":
        before = [d for d in done_days(ctx.conn, item["id"], for_date) if d < for_date]
        nxt = short_day(for_date + timedelta(days=sch.n))
        if not before:
            return [f"schedule: first time; next due {nxt}"]
        planned = before[-1] + timedelta(days=sch.n)
        diff = (for_date - planned).days
        how = "on the planned day" if diff == 0 else f"{plural(abs(diff), 'day')} {'before' if diff < 0 else 'after'}"
        return [f"schedule: planned for {short_day(planned)}, done {how}; next due {nxt}"]
    if sch.kind != "weekly":
        return []
    s = item_status(ctx, item, for_date).settlement
    if s is None:
        return []
    lines = []
    if s.claimed:
        lines.append(f"schedule: counts for {short_day(s.claimed)} ({_offset_text(s.offset)})")
    lines += [f"schedule: {short_day(m)} merged into this" for m in s.merged]
    if s.extra:
        lines.append("schedule: extra (no scheduled day nearby)")
    return lines


def done(ctx: Ctx, a) -> Result:
    item = find_item(ctx.conn, a.item)
    if not item["active"]:
        raise RkError("item_paused", item["name"])
    at = parse_at(a.at, ctx.tz) if a.at else ctx.now
    for_date = parse_day(a.for_day, ctx.today) if a.for_day else day_of(at, ctx.boundary)
    log_id = add_log(ctx.conn, item, at=at, for_date=for_date, note=a.note, force=a.force, now=ctx.now,
                     today=ctx.today)
    lines = [f"ok: logged #{log_id} {item['name']} for {long_day(for_date)} at {at:%Y-%m-%d %H:%M}"]
    lines += _schedule_lines(ctx, item, for_date)
    resolved = [] if a.keep_notes else resolve_for_item(ctx.conn, item["id"], log_id, ctx.now)
    lines += [f"notes_resolved: #{n['id']} {n['text']}" for n in resolved]
    data = {"ok": True, "log": {"id": log_id, "item": item["name"], "for_date": for_date.isoformat(),
                                "at": at.isoformat(timespec="minutes")},
            "schedule": [line.split(": ", 1)[1] for line in lines if line.startswith("schedule: ")],
            "notes_resolved": [{"id": n["id"], "text": n["text"]} for n in resolved]}
    return Result(lines, data)


def skip(ctx: Ctx, a) -> Result:
    item = find_item(ctx.conn, a.item)
    sch = parse_schedule(item["schedule"])
    if sch.kind not in ("daily", "weekly"):
        raise RkError("skip_not_applicable", f"{item['name']} is {item['schedule']}")
    day = parse_day(a.for_day, ctx.today)
    if sch.kind == "weekly" and day.weekday() not in sch.days:
        raise RkError("not_scheduled", f"{item['name']} is not scheduled on {short_day(day)}")
    if a.undo:
        changed = undo_skip(ctx.conn, item, for_date=day, now=ctx.now)
        text = (f"ok: {item['name']} is no longer skipped on {short_day(day)}" if changed
                else f"ok: {item['name']} was not skipped on {short_day(day)}")
    else:
        changed = add_skip(ctx.conn, item, for_date=day, reason=a.reason, now=ctx.now, today=ctx.today)
        text = (f"ok: skipped {item['name']} on {short_day(day)}" + (f" ({a.reason})" if a.reason else "")
                if changed else f"ok: {item['name']} was already skipped on {short_day(day)}")
    return Result([text], {"ok": True, "item": item["name"], "for_date": day.isoformat(), "changed": changed,
                           "undo": a.undo})


def _log_line(r) -> str:
    line = f"#{r['id']} {long_day(date.fromisoformat(r['for_date']))} {r['item_name']} at {r['at'][:16].replace('T', ' ')}"
    return line + (f" | note: {r['note']}" if r["note"] else "")


def _log_data(r) -> dict:
    return {"id": r["id"], "item": r["item_name"], "for_date": r["for_date"], "at": r["at"], "note": r["note"]}


def log_list(ctx: Ctx, a) -> Result:
    item_id = find_item(ctx.conn, a.item)["id"] if a.item else None
    start = parse_day(a.start, ctx.today) if a.start else None
    end = parse_day(a.end, ctx.today) if a.end else None
    rows = list_logs(ctx.conn, item_id=item_id, start=start, end=end, limit=a.limit)
    return Result([_log_line(r) for r in rows] or ["logs: none"], {"logs": [_log_data(r) for r in rows]})


def log_edit(ctx: Ctx, a) -> Result:
    at = parse_at(a.at, ctx.tz) if a.at else None
    for_date = parse_day(a.for_day, ctx.today) if a.for_day else None
    changes = edit_log(ctx.conn, a.id, at=at, for_date=for_date, note=a.note, boundary=ctx.boundary, now=ctx.now,
                       today=ctx.today)
    row = get_log(ctx.conn, a.id)
    if not changes:
        return Result([f"ok: nothing changed on #{a.id}"], {"ok": True, "changes": {}})
    lines = [f"ok: edited #{a.id} {row['item_name']}"]
    lines += [f"changed: {k} {old} -> {new}" for k, (old, new) in changes.items()]
    return Result(lines, {"ok": True, "log": _log_data(row),
                          "changes": {k: [old, new] for k, (old, new) in changes.items()}})


def log_delete(ctx: Ctx, a) -> Result:
    row = delete_log(ctx.conn, a.id, ctx.now)
    return Result([f"ok: deleted #{a.id} {row['item_name']} (restore with: log restore {a.id})"],
                  {"ok": True, "log": _log_data(row)})


def log_restore(ctx: Ctx, a) -> Result:
    row = restore_log(ctx.conn, a.id)
    return Result([f"ok: restored #{a.id} {row['item_name']}"], {"ok": True, "log": _log_data(row)})


def note_add(ctx: Ctx, a) -> Result:
    item = find_item(ctx.conn, a.item)
    note_id = add_note(ctx.conn, item, a.text, ctx.now)
    text = " ".join(a.text.split())
    return Result([f"ok: note #{note_id} on {item['name']}: {text} (shown until {item['name']} is next logged)"],
                  {"ok": True, "note": {"id": note_id, "item": item["name"], "text": text}})


def note_list(ctx: Ctx, a) -> Result:
    rows = open_notes(ctx.conn)
    lines = [f"#{n['id']} {n['item_name']}: {n['text']} (since {n['created_at'][:10]})" for n in rows]
    return Result(lines or ["notes: none open"],
                  {"notes": [{"id": n["id"], "item": n["item_name"], "text": n["text"]} for n in rows]})


def note_resolve(ctx: Ctx, a) -> Result:
    row = resolve_note(ctx.conn, a.id, ctx.now)
    if row["resolved_at"] is not None:
        return Result([f"ok: note #{a.id} was already resolved"], {"ok": True, "changed": False})
    return Result([f"ok: resolved note #{a.id} ({row['item_name']}: {row['text']})"], {"ok": True, "changed": True})
```

- [ ] **Step 6: 在 `routine.py` 加上 parser 與 handler**

在 `build_parser()` 的 `config = ...` 之前加入：

```python
    d = sub.add_parser("done")
    d.add_argument("item")
    d.add_argument("--at")
    d.add_argument("--for", dest="for_day")
    d.add_argument("--note")
    d.add_argument("--keep-notes", action="store_true")
    d.add_argument("--force", action="store_true")

    s = sub.add_parser("skip")
    s.add_argument("item")
    s.add_argument("--for", dest="for_day", required=True)
    s.add_argument("--reason")
    s.add_argument("--undo", action="store_true")

    log = sub.add_parser("log").add_subparsers(dest="sub", required=True, parser_class=Parser)
    ll = log.add_parser("list")
    ll.add_argument("--item")
    ll.add_argument("--from", dest="start")
    ll.add_argument("--to", dest="end")
    ll.add_argument("--limit", type=int, default=50)
    le = log.add_parser("edit")
    le.add_argument("id", type=int)
    le.add_argument("--at")
    le.add_argument("--for", dest="for_day")
    le.add_argument("--note")
    for name in ("delete", "restore"):
        log.add_parser(name).add_argument("id", type=int)

    note = sub.add_parser("note").add_subparsers(dest="sub", required=True, parser_class=Parser)
    na = note.add_parser("add")
    na.add_argument("item")
    na.add_argument("text")
    note.add_parser("list")
    note.add_parser("resolve").add_argument("id", type=int)
```

import 改成：

```python
from routine_core import REPO, VERSION, cmd_admin, cmd_items, cmd_logs, storage  # noqa: E402
```

`HANDLERS` 加入：

```python
    ("done", None): cmd_logs.done,
    ("skip", None): cmd_logs.skip,
    ("log", "list"): cmd_logs.log_list,
    ("log", "edit"): cmd_logs.log_edit,
    ("log", "delete"): cmd_logs.log_delete,
    ("log", "restore"): cmd_logs.log_restore,
    ("note", "add"): cmd_logs.note_add,
    ("note", "list"): cmd_logs.note_list,
    ("note", "resolve"): cmd_logs.note_resolve,
```

- [ ] **Step 7: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_logs.py tests/test_routine_items.py -v`
Expected: 全部 PASS

- [ ] **Step 8: Commit**

```bash
git add src/routine-keeper/scripts tests/test_routine_logs.py
git commit -m "feat: routine-keeper done, skip, log fixes, and reminders"
```

---

### Task 9: `time` 指令

**Files:**
- Create: `src/routine-keeper/scripts/routine_core/cmd_time.py`
- Modify: `src/routine-keeper/scripts/routine.py`
- Create: `tests/test_routine_time.py`

**Interfaces:**
- Consumes: `cmd_logs.item_status`、`list_items`、`logs_on`、`open_notes`、`skip_days`、日期格式函式
- Produces: `cmd_time.time_day(ctx, a) -> Result`；`cmd_time.state_text(st: DayStatus, q: date, times: list[str], skip_reason: str | None) -> str`；`MISSED_LIST_MAX = 3`

輸出格式（spec「輸出契約」）：

```
date: 2026-10-14 (Wed)
now: 2026-10-14 16:20 Asia/Taipei
day_boundary: 05:00

doses:
- Vitamin D [daily, after breakfast]: done 10:42
- Magnesium [daily, bedtime]: not_done

chores:
- Laundry [weekly:wed,sat]: due today | last done 2026-10-10 (4 days ago)
  note #1: wash the jacket
```

各狀態的文字：

| state | 文字 |
|---|---|
| done | `done 10:42, 18:00`（當天所有紀錄的時間） |
| not_done | `not_done` |
| skipped | `skipped` 或 `skipped (too tired)` |
| idle | `no schedule` |
| never_done | `never done` |
| upcoming | `next Wed 2026-10-28 (in 14 days)` |
| due（interval，ref == q） | `due today` |
| due（interval，ref < q） | `due since Sat 2026-10-03 (11 days)` |
| due（weekly，ref == q） | `due today` |
| due（weekly，ref > q） | `due Wed 2026-10-14 (can be done from today)` |
| makeup | `makeup for Sat 2026-10-10` |
| missed | `missed Sat 2026-10-10` |

之後依序附加（用 ` | ` 連接）：
- state 不是 done、且有 last_done：`last done 2026-10-07 (7 days ago)`；idle 且從沒做過：`never done`。
- 還沒結清的錯過場次（state 是 missed 時排除 ref 那個）：≤ 3 個列出 `missed: Sat 2026-10-10, Wed 2026-10-14`；更多就 `missed 5 times since 2026-09-19`。

- [ ] **Step 1: 寫失敗測試**

`tests/test_routine_time.py`：

```python
import json

from rk_helpers import at_tpe, run, root  # noqa: F401


def test_empty(root, capsys):
    code, out = run(root, capsys, "time", "today")
    assert code == 0
    assert out.splitlines() == [
        "date: 2026-10-14 (Wed)", "now: 2026-10-14 16:20 Asia/Taipei", "day_boundary: 05:00", "",
        "doses:", "- (none)", "", "chores:", "- (none)"]


def test_a_full_day(root, capsys):
    t0 = at_tpe("2026-09-01 09:00")
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D", "--slot", "after breakfast", now=t0)
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium", "--slot", "bedtime", now=t0)
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat", now=t0)
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Bed sheets", "--schedule", "interval:14", now=t0)
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Litter box", now=t0)
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-14 10:42")
    run(root, capsys, "done", "Laundry", "--at", "2026-10-07 18:00")
    run(root, capsys, "done", "Laundry", "--at", "2026-10-10 18:00")
    run(root, capsys, "done", "Bed sheets", "--at", "2026-09-19 12:00")
    run(root, capsys, "done", "Litter box", "--at", "2026-10-14 14:10")
    run(root, capsys, "note", "add", "Laundry", "wash the jacket")
    code, out = run(root, capsys, "time", "today")
    assert out.splitlines()[4:] == [
        "doses:",
        "- Magnesium [daily, bedtime]: not_done",
        "- Vitamin D [daily, after breakfast]: done 10:42",
        "",
        "chores:",
        "- Bed sheets [interval:14]: due since Sat 2026-10-03 (11 days) | last done 2026-09-19 (25 days ago)",
        "- Laundry [weekly:wed,sat]: due today | last done 2026-10-10 (4 days ago)",
        "  note #1: wash the jacket",
        "- Litter box [none]: done 14:10",
    ]


def test_a_past_day_only_counts_records_up_to_it(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat",
        now=at_tpe("2026-10-01 09:00"))
    run(root, capsys, "done", "Laundry", "--at", "2026-10-07 18:00")
    run(root, capsys, "done", "Laundry", "--at", "2026-10-14 10:00")
    code, out = run(root, capsys, "time", "2026-10-11")
    assert "- Laundry [weekly:wed,sat]: makeup for Sat 2026-10-10 | last done 2026-10-07 (4 days ago)" in out.splitlines()
    code, out = run(root, capsys, "time", "yesterday")
    assert ("- Laundry [weekly:wed,sat]: due Wed 2026-10-14 (can be done from today) | last done 2026-10-07 "
            "(6 days ago) | missed: Sat 2026-10-10") in out.splitlines()


def test_paused_items_are_hidden(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry")
    run(root, capsys, "item", "pause", "Laundry")
    assert "Laundry" not in run(root, capsys, "time", "today")[1]


def test_skipped_day(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium")
    run(root, capsys, "skip", "Magnesium", "--for", "today", "--reason", "ran out")
    assert "- Magnesium [daily]: skipped (ran out)" in run(root, capsys, "time", "today")[1].splitlines()


def test_many_missed_days_are_summarised(root, capsys):
    run(root, capsys, "item", "add", "--kind", "chore", "--name", "Laundry", "--schedule", "weekly:wed,sat",
        now=at_tpe("2026-09-14 09:00"))
    out = run(root, capsys, "time", "today")[1]
    line = [x for x in out.splitlines() if x.startswith("- Laundry")][0]
    assert line == "- Laundry [weekly:wed,sat]: due today | missed 8 times since 2026-09-16"


def test_changing_timezone_keeps_past_days(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Magnesium")
    run(root, capsys, "done", "Magnesium", "--at", "2026-10-13 23:30")
    run(root, capsys, "config", "set", "timezone", "UTC")
    out = run(root, capsys, "time", "2026-10-13")[1]
    assert "- Magnesium [daily]: done 23:30" in out.splitlines()


def test_bad_day(root, capsys):
    code, out = run(root, capsys, "time", "someday")
    assert code == 1 and out.startswith("error: bad_date")


def test_time_json(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D")
    run(root, capsys, "done", "Vitamin D", "--at", "2026-10-14 10:42")
    data = json.loads(run(root, capsys, "time", "today", "--json")[1])
    assert data["date"] == "2026-10-14"
    assert data["items"][0] == {
        "name": "Vitamin D", "kind": "dose", "schedule": "daily", "slot": None, "state": "done", "ref": None,
        "last_done": "2026-10-14", "missed": [], "done_times": ["10:42"], "notes": [], "text": "done 10:42"}
```

註：`test_changing_timezone_keeps_past_days` 的 `done 23:30` 是紀錄當時的本地時間（紀錄存的是 `at` 原字串），改時區不會改寫既有紀錄的顯示。

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_time.py -v`
Expected: FAIL，`error: bad_arguments (argument cmd: invalid choice: 'time' ...)`

- [ ] **Step 3: 實作 `cmd_time.py`**

```python
"""time today | yesterday | YYYY-MM-DD"""
from datetime import date

from .cmd_logs import item_status
from .context import Ctx, Result
from .dates import ago, long_day, parse_day, plural, short_day
from .items import list_items
from .logs import logs_on, skip_days
from .notes import open_notes
from .status import DayStatus

MISSED_LIST_MAX = 3


def state_text(st: DayStatus, q: date, times: list[str], skip_reason: str | None) -> str:
    s = st.state
    if s == "done":
        text = "done " + ", ".join(times)
    elif s == "skipped":
        text = "skipped" + (f" ({skip_reason})" if skip_reason else "")
    elif s == "idle":
        text = "no schedule"
    elif s == "never_done":
        text = "never done"
    elif s == "upcoming":
        text = f"next {short_day(st.ref)} ({ago(st.ref, q)})"
    elif s == "due":
        if st.ref == q:
            text = "due today"
        elif st.ref < q:
            text = f"due since {short_day(st.ref)} ({plural((q - st.ref).days, 'day')})"
        else:
            text = f"due {short_day(st.ref)} (can be done from today)"
    elif s == "makeup":
        text = f"makeup for {short_day(st.ref)}"
    elif s == "missed":
        text = f"missed {short_day(st.ref)}"
    else:
        text = s   # not_done
    parts = [text]
    if s != "done" and st.last_done:
        parts.append(f"last done {st.last_done.isoformat()} ({ago(st.last_done, q)})")
    elif s == "idle":
        parts.append("never done")
    others = [m for m in st.missed if not (s == "missed" and m == st.ref)]
    if len(others) > MISSED_LIST_MAX:
        parts.append(f"missed {len(others)} times since {others[0].isoformat()}")
    elif others:
        parts.append("missed: " + ", ".join(short_day(m) for m in others))
    return " | ".join(parts)


def time_day(ctx: Ctx, a) -> Result:
    q = parse_day(a.day, ctx.today)
    lines = [f"date: {long_day(q)}", f"now: {ctx.now:%Y-%m-%d %H:%M} {ctx.tz.key}",
             f"day_boundary: {ctx.boundary:%H:%M}"]
    data = {"date": q.isoformat(), "now": ctx.now.isoformat(timespec="minutes"), "timezone": ctx.tz.key,
            "day_boundary": f"{ctx.boundary:%H:%M}", "items": []}
    for kind, title in (("dose", "doses"), ("chore", "chores")):
        lines += ["", f"{title}:"]
        items = list_items(ctx.conn, kind=kind)
        if not items:
            lines.append("- (none)")
        for item in items:
            st = item_status(ctx, item, q)
            times = [r["at"][11:16] for r in logs_on(ctx.conn, item["id"], q)]
            text = state_text(st, q, times, skip_days(ctx.conn, item["id"]).get(q))
            label = item["schedule"] + (f", {item['slot']}" if item["slot"] else "")
            lines.append(f"- {item['name']} [{label}]: {text}")
            notes = open_notes(ctx.conn, item["id"])
            lines += [f"  note #{n['id']}: {n['text']}" for n in notes]
            data["items"].append({
                "name": item["name"], "kind": kind, "schedule": item["schedule"], "slot": item["slot"],
                "state": st.state, "ref": st.ref.isoformat() if st.ref else None,
                "last_done": st.last_done.isoformat() if st.last_done else None,
                "missed": [m.isoformat() for m in st.missed], "done_times": times,
                "notes": [{"id": n["id"], "text": n["text"]} for n in notes], "text": text})
    return Result(lines, data)
```

- [ ] **Step 4: 在 `routine.py` 註冊**

`build_parser()` 加入（放在 `skip` 之後）：

```python
    sub.add_parser("time").add_argument("day")
```

import 加上 `cmd_time`：

```python
from routine_core import REPO, VERSION, cmd_admin, cmd_items, cmd_logs, cmd_time, storage  # noqa: E402
```

`HANDLERS` 加入：

```python
    ("time", None): cmd_time.time_day,
```

- [ ] **Step 5: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_time.py -v`
Expected: 全部 PASS

若 `test_many_missed_days_are_summarised` 的次數不同：item 建立於 Mon 09-14，場次為 09-16、09-19、09-23、09-26、09-30、10-03、10-07、10-10（8 個 missed，10-14 是 due）。請以這個數字為準修程式，不要改測試。

- [ ] **Step 6: Commit**

```bash
git add src/routine-keeper/scripts tests/test_routine_time.py
git commit -m "feat: routine-keeper time command shows a day's chores and doses"
```

---

### Task 10: 資料搬移與匯出

**Files:**
- Modify: `src/routine-keeper/scripts/routine_core/storage.py`（加 `move_data`、`count_rows`）
- Modify: `src/routine-keeper/scripts/routine_core/cmd_admin.py`（換掉暫時的 `data_command`，加 `export`）
- Modify: `src/routine-keeper/scripts/routine.py`
- Create: `tests/test_routine_data.py`

**Interfaces:**
- Produces:
  - `storage.count_rows(conn) -> dict[str, int]`
  - `storage.move_data(root, target: Path, *, mode: str, now: datetime, default_tz: str) -> dict`，`mode ∈ {"copy","use_existing","overwrite"}`，回傳 `{"from": str, "to": str, "kept_as": str | None, "replaced_as": str | None, "changed": bool}`
  - `cmd_admin.data_command(args, *, root, now, default_tz) -> Result`
  - `cmd_admin.export(ctx, a) -> Result`

- [ ] **Step 1: 寫失敗測試**

`tests/test_routine_data.py`：

```python
import json
import sqlite3

from routine_core import storage
from rk_helpers import run, root  # noqa: F401


def seed(root, capsys):
    run(root, capsys, "item", "add", "--kind", "dose", "--name", "Vitamin D")
    run(root, capsys, "done", "Vitamin D")


def test_data_where(root, capsys):
    code, out = run(root, capsys, "data", "where")
    assert out.splitlines() == [f"data_dir: {root / 'data'}", f"database: {root / 'data' / 'routine.db'}",
                                "exists: no"]


def test_move_copies_verifies_and_keeps_the_old_file(root, capsys, tmp_path):
    seed(root, capsys)
    target = tmp_path / "elsewhere"
    code, out = run(root, capsys, "data", "move", "--to", str(target))
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == f"ok: data moved to {target}"
    assert lines[1] == f"kept_old_copy: {root / 'data' / 'routine.db.moved-20261014082000'}"
    assert lines[2] == f"confirm: routine-keeper now keeps its data in {target}"
    assert not (root / "data" / "routine.db").exists()
    assert (target / "routine.db").exists()
    assert "Vitamin D" in run(root, capsys, "log", "list")[1]


def test_move_to_where_it_already_is(root, capsys):
    seed(root, capsys)
    code, out = run(root, capsys, "data", "move", "--to", str(root / "data"))
    assert out == f"ok: data is already in {root / 'data'}"


def test_move_refuses_to_overwrite_by_default(root, capsys, tmp_path):
    seed(root, capsys)
    target = tmp_path / "elsewhere"
    target.mkdir()
    sqlite3.connect(target / "routine.db").close()
    code, out = run(root, capsys, "data", "move", "--to", str(target))
    assert code == 2 and out.startswith("error: target_exists")
    assert (root / "data" / "routine.db").exists()


def test_use_existing_switches_without_copying(root, capsys, tmp_path):
    other = tmp_path / "other-root"
    other.mkdir()
    run(other, capsys, "item", "add", "--kind", "chore", "--name", "Laundry")
    seed(root, capsys)
    code, out = run(root, capsys, "data", "move", "--to", str(other / "data"), "--use-existing")
    assert code == 0 and out.splitlines()[0] == f"ok: now using the data in {other / 'data'}"
    assert "Laundry" in run(root, capsys, "item", "list")[1]
    assert (root / "data" / "routine.db").exists()   # left alone


def test_overwrite_keeps_the_replaced_file(root, capsys, tmp_path):
    seed(root, capsys)
    target = tmp_path / "elsewhere"
    target.mkdir()
    sqlite3.connect(target / "routine.db").close()
    code, out = run(root, capsys, "data", "move", "--to", str(target), "--overwrite")
    assert code == 0
    assert f"replaced_copy: {target / 'routine.db.replaced-20261014082000'}" in out.splitlines()
    assert "Vitamin D" in run(root, capsys, "item", "list")[1]


def test_failed_verification_changes_nothing(root, capsys, tmp_path, monkeypatch):
    seed(root, capsys)
    counts = iter([{"items": 1}, {"items": 0}])
    monkeypatch.setattr(storage, "count_rows", lambda conn: next(counts))
    target = tmp_path / "elsewhere"
    code, out = run(root, capsys, "data", "move", "--to", str(target))
    assert code == 3 and out.startswith("error: move_verify_failed")
    assert (root / "data" / "routine.db").exists()
    assert not (target / "routine.db").exists()
    assert list(target.iterdir()) == []
    monkeypatch.undo()
    assert storage.data_dir(root) == root / "data"


def test_move_options_are_exclusive(root, capsys, tmp_path):
    code, out = run(root, capsys, "data", "move", "--to", str(tmp_path), "--use-existing", "--overwrite")
    assert code == 1 and out.startswith("error: bad_arguments")


def test_export_to_stdout_and_file(root, capsys, tmp_path):
    seed(root, capsys)
    data = json.loads(run(root, capsys, "export")[1])
    assert data["version"] == "1.0.0"
    assert data["tables"]["items"][0]["name"] == "Vitamin D"
    assert len(data["tables"]["logs"]) == 1
    target = tmp_path / "backup.json"
    code, out = run(root, capsys, "export", "--file", str(target))
    assert out == f"ok: exported 1 items, 1 logs to {target}"
    assert json.loads(target.read_text())["tables"]["items"][0]["name"] == "Vitamin D"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_data.py -v`
Expected: FAIL，`error: bad_arguments (argument cmd: invalid choice: 'data' ...)`

- [ ] **Step 3: 在 `storage.py` 檔尾實作 `move_data`**

```python
def count_rows(conn) -> dict:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in db.TABLES}


def _point_config_to(root: Path, target: Path) -> None:
    cfg = load_config(root)
    cfg["data_dir"] = str(target)
    save_config(root, cfg)


def move_data(root: Path, target: Path, *, mode: str, now, default_tz: str) -> dict:
    """Copy the database to target (verified by row counts), point config.json at it, and keep the old
    file renamed. use_existing only switches; overwrite keeps the replaced file renamed."""
    target = Path(target).expanduser().resolve()
    old_dir = data_dir(root).resolve()
    result = {"from": str(old_dir), "to": str(target), "kept_as": None, "replaced_as": None, "changed": True}
    if target == old_dir:
        return {**result, "changed": False}
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RkError("data_unavailable", f"{target}: {type(e).__name__}") from None
    old_db, new_db = old_dir / DB_NAME, target / DB_NAME
    stamp = now.strftime("%Y%m%d%H%M%S")
    if mode == "use_existing":
        if not new_db.exists():
            raise RkError("data_unavailable", f"no {DB_NAME} in {target}")
        try:
            conn = db.connect(new_db)
            db.init(conn, default_tz)
            conn.close()
        except sqlite3.Error as e:
            raise RkError("data_unavailable", f"{new_db}: {type(e).__name__}") from None
        _point_config_to(root, target)
        return result
    if new_db.exists() and mode != "overwrite":
        raise RkError("target_exists", str(new_db))
    src = open_db(root, default_tz)
    incoming = target / f".{DB_NAME}.incoming-{stamp}"
    try:
        dst = db.connect(incoming)
        src.backup(dst)
        same = count_rows(src) == count_rows(dst)
        dst.close()
    except sqlite3.Error as e:
        incoming.unlink(missing_ok=True)
        raise RkError("data_unavailable", f"{target}: {type(e).__name__}") from None
    finally:
        src.close()
    if not same:
        incoming.unlink(missing_ok=True)
        raise RkError("move_verify_failed", "row counts differ after copying")
    if new_db.exists():
        replaced = new_db.with_name(f"{DB_NAME}.replaced-{stamp}")
        new_db.rename(replaced)
        result["replaced_as"] = str(replaced)
    os.replace(incoming, new_db)
    _point_config_to(root, target)
    kept = old_db.with_name(f"{DB_NAME}.moved-{stamp}")
    old_db.rename(kept)
    result["kept_as"] = str(kept)
    return result
```

註：`stamp` 用傳進來的 `now`（UTC），所以測試裡是 `20261014082000`。

- [ ] **Step 4: 換掉 `cmd_admin.py` 的 `data_command`，加上 `export`**

刪掉 Task 7 的暫時版 `data_command`，改成：

```python
def data_command(args, *, root, now, default_tz) -> Result:
    if args.sub == "where":
        d = storage.data_dir(root)
        path = d / storage.DB_NAME
        data = {"data_dir": str(d), "database": str(path), "exists": path.exists()}
        return Result([f"data_dir: {d}", f"database: {path}", f"exists: {'yes' if path.exists() else 'no'}"], data)
    mode = "use_existing" if args.use_existing else "overwrite" if args.overwrite else "copy"
    r = storage.move_data(root, Path(args.to), mode=mode, now=now, default_tz=default_tz)
    if not r["changed"]:
        return Result([f"ok: data is already in {r['to']}"], {"ok": True, **r})
    head = f"ok: now using the data in {r['to']}" if mode == "use_existing" else f"ok: data moved to {r['to']}"
    lines = [head]
    if r["kept_as"]:
        lines.append(f"kept_old_copy: {r['kept_as']}")
    if r["replaced_as"]:
        lines.append(f"replaced_copy: {r['replaced_as']}")
    confirm = f"routine-keeper now keeps its data in {r['to']}"
    lines.append(f"confirm: {confirm}")
    return Result(lines, {"ok": True, **r, "confirm": confirm})


def export(ctx: Ctx, a) -> Result:
    tables = {t: [dict(r) for r in ctx.conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in db.TABLES}
    data = {"version": VERSION, "exported_at": ctx.now.isoformat(timespec="seconds"), "tables": tables}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if not a.file:
        return Result([text], data)
    path = Path(a.file).expanduser()
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    n_items, n_logs = len(tables["items"]), len(tables["logs"])
    return Result([f"ok: exported {n_items} items, {n_logs} logs to {path}"],
                  {"ok": True, "file": str(path), "items": n_items, "logs": n_logs})
```

`cmd_admin.py` 開頭的 import 改成：

```python
"""config show | set, data where | move, export"""
import json
import os
from pathlib import Path

from . import VERSION, db, storage
from .context import Ctx, Result
from .dates import parse_boundary, zone
```

（`RkError` 不再需要，刪掉那行 import。）

註：`export` 不加 `--file` 時，`--json` 與文字模式輸出相同的 JSON；`main` 在 `as_json` 時會再 dump `result.data`，結果一樣。

- [ ] **Step 5: 在 `routine.py` 註冊**

`build_parser()` 的 `return p` 之前加入：

```python
    data = sub.add_parser("data").add_subparsers(dest="sub", required=True, parser_class=Parser)
    data.add_parser("where")
    move = data.add_parser("move")
    move.add_argument("--to", required=True)
    how = move.add_mutually_exclusive_group()
    how.add_argument("--use-existing", action="store_true")
    how.add_argument("--overwrite", action="store_true")

    sub.add_parser("export").add_argument("--file")
```

`HANDLERS` 加入：

```python
    ("export", None): cmd_admin.export,
```

- [ ] **Step 6: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_data.py -v`
Expected: 全部 PASS

- [ ] **Step 7: 跑全部測試**

Run: `uv run pytest -m "not live"`
Expected: 全部 PASS

- [ ] **Step 8: Commit**

```bash
git add src/routine-keeper/scripts tests/test_routine_data.py
git commit -m "feat: routine-keeper data move with verification, and JSON export"
```

---

### Task 11: Hermes 版與 Claude Code 版的 skill 文件

**Files:**
- Create: `src/routine-keeper/hermes/DESCRIPTION.md`
- Create: `src/routine-keeper/hermes/routine-log/SKILL.md`
- Create: `src/routine-keeper/hermes/routine-setup/SKILL.md`
- Create: `src/routine-keeper/hermes/routine-history/SKILL.md`
- Create: `src/routine-keeper/claude/SKILL.md`
- Create: `src/routine-keeper/claude/references/setup.md`
- Create: `src/routine-keeper/claude/references/history.md`
- Create: `tests/test_routine_skills.py`

**Interfaces:**
- Consumes: `routine.main`（檢查文件中的子指令都存在）

- [ ] **Step 1: 寫失敗測試**

`tests/test_routine_skills.py`：

```python
import re
from pathlib import Path

import pytest

import routine

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "routine-keeper"
HERMES = SRC / "hermes"
CLAUDE = SRC / "claude"
HERMES_SKILLS = ["routine-log", "routine-setup", "routine-history"]
HERMES_CMD = "${HERMES_SKILL_DIR}/../scripts/routine.py"
CLAUDE_CMD = "${CLAUDE_SKILL_DIR}/scripts/routine.py"
GROUPS = {"item", "log", "note", "config", "data"}


def frontmatter(path: Path) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    raw = text.split("---\n", 2)[1]
    fields = {}
    for line in raw.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            fields[m[1]] = m[2].strip().strip("'\"")
    return raw, fields


def all_md(base: Path):
    return sorted(base.rglob("*.md"))


@pytest.mark.parametrize("name", HERMES_SKILLS)
def test_hermes_sub_skills_fit_the_index(name):
    raw, fm = frontmatter(HERMES / name / "SKILL.md")
    assert fm["name"] == name
    assert 0 < len(fm["description"]) <= 60, fm["description"]
    for key in ("version", "author", "license"):
        assert fm.get(key), key
    assert len(raw) < 4000


def test_hermes_category_description():
    _, fm = frontmatter(HERMES / "DESCRIPTION.md")
    assert "家事" in fm["description"] and "chores" in fm["description"]


def test_claude_skill_frontmatter():
    _, fm = frontmatter(CLAUDE / "SKILL.md")
    assert fm["name"] == "routine-keeper"
    assert 0 < len(fm["description"]) <= 1024


def test_command_paths_match_each_agent():
    for path in all_md(HERMES):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "routine.py" in line and "scripts/routine.py" in line:
                assert HERMES_CMD in line, f"{path}: {line}"
    for path in all_md(CLAUDE):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "scripts/routine.py" in line:
                assert CLAUDE_CMD in line, f"{path}: {line}"
    for path in all_md(SRC):
        assert "{{" not in path.read_text(encoding="utf-8"), path


def documented_commands():
    found = set()
    for path in all_md(SRC):
        for m in re.finditer(r"routine\.py ([a-z]+)(?: ([a-z]+))?", path.read_text(encoding="utf-8")):
            cmd, sub = m[1], m[2]
            found.add((cmd, sub if cmd in GROUPS else None))
    return sorted(found, key=str)


def test_every_documented_command_exists(capsys):
    cmds = documented_commands()
    assert ("done", None) in cmds and ("item", "add") in cmds
    for cmd, sub in cmds:
        argv = [cmd] + ([sub] if sub else []) + ["--help"]
        assert routine.main(argv) == 0, argv
    capsys.readouterr()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_routine_skills.py -v`
Expected: FAIL，`FileNotFoundError: ... hermes/routine-log/SKILL.md`

- [ ] **Step 3: 寫 `hermes/DESCRIPTION.md`**

```markdown
---
description: Track the user's recurring chores and supplements or medication — log what was done, check any day, set schedules and reminders. 家事、吃藥、保健品、維他命、洗衣服、倒垃圾、換床單、有沒有做過、有沒有吃藥、今天該做什麼、下次記得。
---
```

- [ ] **Step 4: 寫 `hermes/routine-log/SKILL.md`**

````markdown
---
name: routine-log
description: Log a chore or dose as done/skipped; check a day
version: 1.0.0
author: SmallYuan
license: MIT
homepage: https://github.com/SmallYuanSY/skills
platforms: [macos, linux]
metadata:
  hermes:
    tags: [routine, chores, supplements, medication, 家事, 吃藥, 保健品]
---

# routine-log

Use this when the user says they did a chore or took a supplement or medication, or asks what was done or is due on a day. Only run these commands. Never keep these records anywhere else, and never open or edit the data files. The output is written for you, not for the user: read it and answer in the user's own language.

```bash
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py time today
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py time yesterday
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py time 2026-10-13
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py done "<name>" [--at "YYYY-MM-DD HH:MM"] [--for YYYY-MM-DD] [--note "<text>"]
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py skip "<name>" --for YYYY-MM-DD [--reason "<text>"] [--undo]
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py note add "<name>" "<text>"
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py note list
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py note resolve <id>
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py item list
```

## Logging

- Log only what the user says already happened. "I'm going to bed" does not mean "I took my bedtime pills": ask. The command refuses future times.
- If it happened earlier, pass `--at` with the real time. The day it counts for comes from the day boundary (default 05:00, so 2 a.m. counts for the night before). Use `--for` only when the user names the day.
- One message can mean several commands: "took A and B" is two `done`.
- The user skipped on purpose ("too tired, no laundry today"): `skip`. Not doing it is not the same as skipping; don't skip for them.
- "Remember to X next time I do Y": `note add "Y" "X"`.
- `notes_resolved:` after `done`: these were reminders for this task. Ask the user whether they got done.

## Reading `time`

- `due`, `makeup`: it should be done now. `makeup` means a scheduled day just passed and there is still time.
- `missed`: a scheduled day passed without it. Doing it once settles every missed day; never tell the user they owe several.
- `next …`, `no schedule`, `never done`, `last done … (N days ago)`: facts, not judgments. Choose your own tone.
- `note #N`: a reminder for that item; mention it.

## Errors

- Do what the `action:` line says.
- `unknown_item`: use the exact name from the list in the error. If none fits, ask the user, then add it with routine-setup.
- `already_logged`: tell the user. Add `--force` only if they confirm it really happened twice.

Changing what is tracked or the settings: routine-setup. Past records, fixing a wrong entry, export: routine-history.
````

- [ ] **Step 5: 寫 `hermes/routine-setup/SKILL.md`**

````markdown
---
name: routine-setup
description: Add or change tracked chores, doses, settings
version: 1.0.0
author: SmallYuan
license: MIT
homepage: https://github.com/SmallYuanSY/skills
platforms: [macos, linux]
metadata:
  hermes:
    tags: [routine, chores, supplements, settings, 家事, 吃藥]
---

# routine-setup

Use this to add, change, pause, or rename the chores and supplements being tracked, and to change settings. Only run these commands; never edit `config.json` or the data files by hand.

```bash
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py item add --kind chore|dose --name "<name>" [--schedule <rule>] [--window -1,+2] [--slot "<when>"] [--alias "<other name>"]
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py item edit "<name>" [--name "<new>"] [--schedule <rule>] [--window -E,+L] [--slot "<when>"] [--alias "<add>"] [--remove-alias "<remove>"]
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py item pause "<name>"
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py item resume "<name>"
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py item list [--kind chore|dose] [--all]
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py config show
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py config set day-boundary 05:00
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py config set timezone Asia/Taipei
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py data where
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py data move --to "<folder>" [--use-existing | --overwrite]
```

## Always confirm

After every `confirm:` line, tell the user exactly what was saved and ask whether it is right. If not, fix it with `item edit` (or `config set`).

## Items

- `--kind dose` for supplements and medication, `--kind chore` for everything else.
- Schedules: `daily` (default for doses), `none` (log only, default for chores), `interval:14` (14 days after the last time), `weekly:wed,sat` (fixed weekdays: mon tue wed thu fri sat sun).
- `--window -1,+2` (weekly only): how many days early or late still counts. Default -1,+2.
- `--slot`: when a dose is taken, in the user's words ("after breakfast", "bedtime").
- `--alias`: other names the user uses for the same item, so later messages match.
- If the user doesn't say how often, ask; don't guess a schedule.
- Stopped for now: `item pause`. Pausing keeps the history.

## Settings

- `day-boundary`: when a new day starts. Before it, records count for the previous day. Ask before changing it.
- `timezone`: an IANA name such as `Asia/Taipei`.
- `data move`: only when the user asks. If the error is `target_exists`, ask whether to use the data already there (`--use-existing`) or replace it (`--overwrite`).
- Upgrading routine-keeper: copy the new version over this folder. Never delete the folder first: `config.json` and `data/` live in it.
````

- [ ] **Step 6: 寫 `hermes/routine-history/SKILL.md`**

````markdown
---
name: routine-history
description: Browse, fix, or export past chore/dose records
version: 1.0.0
author: SmallYuan
license: MIT
homepage: https://github.com/SmallYuanSY/skills
platforms: [macos, linux]
metadata:
  hermes:
    tags: [routine, history, chores, supplements, 家事, 吃藥]
---

# routine-history

Use this to look back over records, fix a wrong one, or export everything. Only run these commands.

```bash
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py log list [--item "<name>"] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--limit 50]
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py log edit <id> [--at "YYYY-MM-DD HH:MM"] [--for YYYY-MM-DD] [--note "<text>"]
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py log delete <id>
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py log restore <id>
python3 ${HERMES_SKILL_DIR}/../scripts/routine.py export [--file "<path>.json"]
```

- Find the id with `log list` first. Newest come first; at most 50 unless you pass `--limit`.
- Changing `--at` also moves the record to the day that time belongs to, unless you pass `--for`.
- Before `log delete`, tell the user which record it is and ask. Deleted records can be brought back with `log restore`.
- For one day's overview, use `time <date>` from routine-log instead.
````

- [ ] **Step 7: 寫 `claude/SKILL.md`**

````markdown
---
name: routine-keeper
description: Track the user's recurring chores and supplements or medication — log what was done, check what is due on any day, set schedules and reminders. Use when the user says they did a chore or took a pill, asks whether something was done, or wants to change what is tracked. 家事、吃藥、保健品、洗衣服、倒垃圾、有沒有做過、有沒有吃藥。
version: 1.0.0
author: SmallYuan
license: MIT
homepage: https://github.com/SmallYuanSY/skills
---

# routine-keeper

Only run these commands. Never keep these records anywhere else, and never open or edit the data files. The output is written for you, not for the user: read it and answer in the user's own language.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py time today
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py time yesterday
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py time 2026-10-13
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py done "<name>" [--at "YYYY-MM-DD HH:MM"] [--for YYYY-MM-DD] [--note "<text>"]
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py skip "<name>" --for YYYY-MM-DD [--reason "<text>"] [--undo]
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py note add "<name>" "<text>"
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py note list
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py note resolve <id>
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py item list
```

- Adding or changing what is tracked, or settings: read `${CLAUDE_SKILL_DIR}/references/setup.md` first.
- Past records, fixing a wrong entry, export: read `${CLAUDE_SKILL_DIR}/references/history.md` first.

## Logging

- Log only what the user says already happened. "I'm going to bed" does not mean "I took my bedtime pills": ask. The command refuses future times.
- If it happened earlier, pass `--at` with the real time. The day it counts for comes from the day boundary (default 05:00, so 2 a.m. counts for the night before). Use `--for` only when the user names the day.
- One message can mean several commands: "took A and B" is two `done`.
- The user skipped on purpose ("too tired, no laundry today"): `skip`. Not doing it is not the same as skipping; don't skip for them.
- "Remember to X next time I do Y": `note add "Y" "X"`.
- `notes_resolved:` after `done`: these were reminders for this task. Ask the user whether they got done.

## Reading `time`

- `due`, `makeup`: it should be done now. `makeup` means a scheduled day just passed and there is still time.
- `missed`: a scheduled day passed without it. Doing it once settles every missed day; never tell the user they owe several.
- `next …`, `no schedule`, `never done`, `last done … (N days ago)`: facts, not judgments. Choose your own tone.
- `note #N`: a reminder for that item; mention it.

## Errors

- Do what the `action:` line says.
- `unknown_item`: use the exact name from the list in the error. If none fits, ask the user, then add it (see setup.md).
- `already_logged`: tell the user. Add `--force` only if they confirm it really happened twice.
````

- [ ] **Step 8: 寫 `claude/references/setup.md`**

內容與 Step 5 的 `routine-setup/SKILL.md` 相同，但：沒有 frontmatter；標題改成 `# routine-keeper: setup`；所有指令路徑改成 `${CLAUDE_SKILL_DIR}/scripts/routine.py`。完整內容：

````markdown
# routine-keeper: setup

Use this to add, change, pause, or rename the chores and supplements being tracked, and to change settings. Only run these commands; never edit `config.json` or the data files by hand.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py item add --kind chore|dose --name "<name>" [--schedule <rule>] [--window -1,+2] [--slot "<when>"] [--alias "<other name>"]
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py item edit "<name>" [--name "<new>"] [--schedule <rule>] [--window -E,+L] [--slot "<when>"] [--alias "<add>"] [--remove-alias "<remove>"]
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py item pause "<name>"
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py item resume "<name>"
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py item list [--kind chore|dose] [--all]
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py config show
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py config set day-boundary 05:00
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py config set timezone Asia/Taipei
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py data where
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py data move --to "<folder>" [--use-existing | --overwrite]
```

## Always confirm

After every `confirm:` line, tell the user exactly what was saved and ask whether it is right. If not, fix it with `item edit` (or `config set`).

## Items

- `--kind dose` for supplements and medication, `--kind chore` for everything else.
- Schedules: `daily` (default for doses), `none` (log only, default for chores), `interval:14` (14 days after the last time), `weekly:wed,sat` (fixed weekdays: mon tue wed thu fri sat sun).
- `--window -1,+2` (weekly only): how many days early or late still counts. Default -1,+2.
- `--slot`: when a dose is taken, in the user's words ("after breakfast", "bedtime").
- `--alias`: other names the user uses for the same item, so later messages match.
- If the user doesn't say how often, ask; don't guess a schedule.
- Stopped for now: `item pause`. Pausing keeps the history.

## Settings

- `day-boundary`: when a new day starts. Before it, records count for the previous day. Ask before changing it.
- `timezone`: an IANA name such as `Asia/Taipei`.
- `data move`: only when the user asks. If the error is `target_exists`, ask whether to use the data already there (`--use-existing`) or replace it (`--overwrite`).
- Upgrading routine-keeper: copy the new version over this folder. Never delete the folder first: `config.json` and `data/` live in it.
````

- [ ] **Step 9: 寫 `claude/references/history.md`**

````markdown
# routine-keeper: history

Use this to look back over records, fix a wrong one, or export everything. Only run these commands.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py log list [--item "<name>"] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--limit 50]
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py log edit <id> [--at "YYYY-MM-DD HH:MM"] [--for YYYY-MM-DD] [--note "<text>"]
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py log delete <id>
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py log restore <id>
python3 ${CLAUDE_SKILL_DIR}/scripts/routine.py export [--file "<path>.json"]
```

- Find the id with `log list` first. Newest come first; at most 50 unless you pass `--limit`.
- Changing `--at` also moves the record to the day that time belongs to, unless you pass `--for`.
- Before `log delete`, tell the user which record it is and ask. Deleted records can be brought back with `log restore`.
- For one day's overview, use `time <date>` instead.
````

- [ ] **Step 10: 跑測試確認通過**

Run: `uv run pytest tests/test_routine_skills.py -v`
Expected: 全部 PASS

- [ ] **Step 11: Commit**

```bash
git add src/routine-keeper/hermes src/routine-keeper/claude tests/test_routine_skills.py
git commit -m "feat: routine-keeper skill docs for Hermes (category) and Claude Code"
```

---

### Task 12: 打包工具、release workflow、README

**Files:**
- Create: `tools/package.py`
- Create: `tests/test_package.py`
- Create: `.github/workflows/release-routine-keeper.yml`
- Modify: `README.md`

**Interfaces:**
- Produces:
  - `package.AGENTS = ("hermes", "claude")`
  - `package.assemble(skill_src: Path, agent: str, dest: Path) -> Path`（回傳 `dest/<skill name>`）
  - `package.package(skill: str, out: Path, src_root: Path = ROOT / "src") -> list[Path]`（產生 `out/<agent>/<skill>/` 與 `out/<skill>-<agent>.zip`）

- [ ] **Step 1: 寫失敗測試**

`tests/test_package.py`：

```python
import subprocess
import sys
import zipfile

import package

ROOT = package.ROOT


def test_zips_hold_each_agents_layout(tmp_path):
    zips = package.package("routine-keeper", tmp_path)
    assert sorted(z.name for z in zips) == ["routine-keeper-claude.zip", "routine-keeper-hermes.zip"]
    hermes = set(zipfile.ZipFile(tmp_path / "routine-keeper-hermes.zip").namelist())
    assert {"routine-keeper/DESCRIPTION.md", "routine-keeper/routine-log/SKILL.md",
            "routine-keeper/routine-setup/SKILL.md", "routine-keeper/routine-history/SKILL.md",
            "routine-keeper/scripts/routine.py", "routine-keeper/scripts/routine_core/schedule.py"} <= hermes
    claude = set(zipfile.ZipFile(tmp_path / "routine-keeper-claude.zip").namelist())
    assert {"routine-keeper/SKILL.md", "routine-keeper/references/setup.md",
            "routine-keeper/scripts/routine.py"} <= claude
    for names in (hermes, claude):
        assert not [n for n in names if "__pycache__" in n or n.endswith((".pyc", "config.json"))
                    or "/data/" in n or ".DS_Store" in n]


def test_local_config_and_data_never_ship(tmp_path):
    src = tmp_path / "src" / "demo"
    for agent in ("hermes", "claude"):
        (src / agent).mkdir(parents=True)
        (src / agent / "SKILL.md").write_text("x\n")
    (src / "scripts" / "data").mkdir(parents=True)
    (src / "scripts" / "run.py").write_text("print(1)\n")
    (src / "scripts" / "data" / "routine.db").write_bytes(b"\0")
    (src / "scripts" / "config.json").write_text("{}")
    package.package("demo", tmp_path / "out", src_root=tmp_path / "src")
    names = [n for n in zipfile.ZipFile(tmp_path / "out" / "demo-hermes.zip").namelist() if not n.endswith("/")]
    assert sorted(names) == ["demo/SKILL.md", "demo/scripts/run.py"]


def test_assembled_hermes_copy_runs_and_keeps_data_inside(tmp_path):
    package.package("routine-keeper", tmp_path)
    skill = tmp_path / "hermes" / "routine-keeper"
    r = subprocess.run([sys.executable, str(skill / "scripts" / "routine.py"), "time", "today"],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.startswith("date: ")
    assert (skill / "data" / "routine.db").exists()
    assert r.stderr == ""
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_package.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'package'`

- [ ] **Step 3: 實作 `tools/package.py`**

```python
#!/usr/bin/env python3
"""Release zips for skills that ship hand-written per-agent folders (e.g. routine-keeper).

  uv run tools/package.py routine-keeper [--out build]

src/<skill>/scripts/ is copied into each src/<skill>/<agent>/ folder. The result goes to
build/<agent>/<skill>/ (copy that folder to install locally) and build/<skill>-<agent>.zip.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ("hermes", "claude")
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "config.json", "data", ".config-*")


def assemble(skill_src: Path, agent: str, dest: Path) -> Path:
    out = dest / skill_src.name
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(skill_src / agent, out, ignore=_IGNORE)
    shutil.copytree(skill_src / "scripts", out / "scripts", ignore=_IGNORE)
    return out


def package(skill: str, out: Path, src_root: Path = ROOT / "src") -> list[Path]:
    skill_src = src_root / skill
    out.mkdir(parents=True, exist_ok=True)
    zips = []
    for agent in AGENTS:
        folder = assemble(skill_src, agent, out / agent)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / f"{skill}-{agent}"
            archive = shutil.make_archive(str(base), "zip", root_dir=folder.parent, base_dir=folder.name)
            target = out / f"{skill}-{agent}.zip"
            shutil.move(archive, target)
        zips.append(target)
    return zips


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build release zips for a skill with per-agent folders.")
    p.add_argument("skill")
    p.add_argument("--out", default=str(ROOT / "build"))
    a = p.parse_args(argv)
    if not all((ROOT / "src" / a.skill / x).is_dir() for x in ("scripts", *AGENTS)):
        print(f"error: src/{a.skill} needs scripts/, hermes/, and claude/")
        return 1
    for z in package(a.skill, Path(a.out)):
        print(f"built {z}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

註：`test_local_config_and_data_never_ship` 的 demo 沒有 `routine_core`，`hermes/` 裡只有 `SKILL.md`，所以 zip 內容只有那兩個檔案。

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_package.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 寫 release workflow**

`.github/workflows/release-routine-keeper.yml`：

```yaml
name: release-routine-keeper
on:
  push:
    tags: ["routine-keeper-v*"]
permissions:
  contents: write
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv run pytest -m "not live"
      - run: uv run tools/package.py routine-keeper --out build
      - run: >
          gh release create "$GITHUB_REF_NAME"
          build/routine-keeper-hermes.zip build/routine-keeper-claude.zip
          --title "$GITHUB_REF_NAME" --generate-notes
        env:
          GH_TOKEN: ${{ github.token }}
```

- [ ] **Step 6: 更新 README**

在 `README.md` 的 skill 表格加一列：

```markdown
| [routine-keeper](src/routine-keeper/claude/SKILL.md) | Chores and supplements/medication: log what was done, check any day, weekly or every-N-days schedules that forgive doing it early or late, and reminders for next time. Hermes gets a category of three small skills; Claude Code gets one. |
```

在 `## Install` 一節末尾加：

````markdown
### routine-keeper

routine-keeper ships as release zips instead of `dist/`: download the one for your agent from the [releases](https://github.com/SmallYuanSY/skills/releases) page.

```bash
# Hermes
unzip routine-keeper-hermes.zip -d ~/.hermes/skills/

# Claude Code
unzip routine-keeper-claude.zip -d ~/.claude/skills/
```

It needs Python 3.10+ and nothing else. Its settings (`config.json`) and records (`data/`) live inside the skill folder, so **to upgrade, unzip over the existing folder; never delete it first.** Ask your agent to move the data elsewhere (`data move`) if you'd rather keep it outside.
````

在 `## Development` 一節末尾加：

````markdown
routine-keeper keeps one `scripts/` and two hand-written skill folders (`hermes/`, `claude/`); the translator skips it. Build its zips with:

```bash
uv run tools/package.py routine-keeper   # build/<agent>/routine-keeper/ and build/routine-keeper-<agent>.zip
```

Pushing a `routine-keeper-v*` tag publishes them as a GitHub release.
````

- [ ] **Step 7: 跑全部測試與 translate check**

Run: `uv run pytest -m "not live" && uv run tools/translate.py --check`
Expected: 全部 PASS；`dist/ is up to date`

- [ ] **Step 8: Commit**

```bash
git add tools/package.py tests/test_package.py .github/workflows/release-routine-keeper.yml README.md
git commit -m "feat: package routine-keeper into per-agent release zips"
```

---

### Task 13: 最終驗證（不 push、不發 release）

**Files:** 無新增

- [ ] **Step 1: 全部測試**

Run: `uv run pytest -m "not live" -q`
Expected: 全部 PASS，0 failed

- [ ] **Step 2: 隱私檢查（本機有 deny-list）**

Run: `uv run pytest tests/test_privacy.py -v`
Expected: PASS（不是 SKIPPED；若 SKIPPED 表示 `tests/private-terms.local.txt` 不存在，回報給使用者）

- [ ] **Step 3: 打包並手動煙霧測試組裝後的 Hermes 版**

```bash
uv run tools/package.py routine-keeper --out build
cd build/hermes/routine-keeper
python3 scripts/routine.py item add --kind dose --name "Vitamin D" --slot "after breakfast"
python3 scripts/routine.py done "Vitamin D"
python3 scripts/routine.py time today
python3 scripts/routine.py --json time today
python3 scripts/routine.py data where
cd -
```

Expected：每個指令 exit 0；`time today` 顯示 `- Vitamin D [daily, after breakfast]: done HH:MM`；`data where` 的路徑在 `build/hermes/routine-keeper/data/`。

- [ ] **Step 4: 清掉煙霧測試資料**

```bash
rm -rf build
```

- [ ] **Step 5: 確認 git 狀態乾淨**

Run: `git status --short`
Expected: 沒有輸出（`build/` 在 gitignore，`data/`、`config.json` 不應出現在 `src/`）

- [ ] **Step 6: 回報**

回報測試數量、隱私檢查結果、煙霧測試輸出。push、開 PR、打 tag 發 release 都要先問使用者。
