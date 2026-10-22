# weatherwise 警報改版：實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 weatherwise 不需要任何帳號，就能顯示台灣、日本、香港、美國、加拿大、歐洲的官方氣象警報，以及全球的熱帶氣旋；支援一次查最多 5 個地點；輸出更精簡。

**Architecture:** 警報和預報分開處理。`ww_alerts.py` 依地點的國碼分派給各國的 provider（`ww_alerts_<區>.py`），另外一律查 GDACS（`ww_cyclones.py`），再統一做過期排除、去重、跨地點合併、颱風合併、數量上限。所有網路請求都經過 `ww_cache.py`：同一次執行內同一個 URL 只請求一次，並且有依 URL 設定 TTL 的磁碟快取。預報仍由 `ww_sources.py` 處理，WeatherKit 只負責預報和未來一小時降雨。

**Tech Stack:** Python ≥ 3.10（只用標準庫，WeatherKit 簽章沿用 PyJWT）、uv、pytest。

**Spec:** `docs/specs/2026-10-22-weatherwise-alerts-design.md`（實作前先讀完。本計畫不重複 spec 裡的理由。）

## Global Constraints

- 版本 `2.0.0`：`ww_http.VERSION`、User-Agent、`--version`、SKILL.md frontmatter 都要改。
- 不新增任何第三方相依套件。幾何計算（距離、方位、點是否在多邊形內）用純 Python。
- 輸出給模型讀：英文 `key: value`，警報標題和摘要保留原文（中文、日文等）。錯誤是 `error: <code>` 加 `action:`。
- **不做封路、路況、非氣象災害示警**。NCDR 只保留發布者是 `中央氣象署`、title 是 `颱風`／`降雨`／`強風`／`高溫`／`低溫`／`濃霧`／`巨浪` 的 entry。
- 地點最多 5 個；每個地點最多列 6 則警報；摘要最多 60 字。
- 熱帶氣旋門檻：目前位置在 2000 km 內才抓 geometry；落在暴風範圍內，或目前位置／預測路徑任一點在 800 km 內，就提醒。兩個數字寫成 `ww_cyclones.py` 的常數。
- 快取 TTL：警報 300 秒、GDACS 900 秒、預報 900 秒、Nominatim 30 天。快取目錄 `$XDG_CACHE_HOME/weatherwise`，預設 `~/.cache/weatherwise`，可用 `WEATHERWISE_CACHE_DIR` 覆寫（測試用）。快取出錯一律忽略。
- NCDR 有 3 秒的請求間隔限制：一次執行最多請求一次 feed，**不抓個別的 CAP 檔**。
- 所有請求都帶 `ww_http.USER_AGENT`。
- repo 裡不能有私人地點。fixtures 和測試的地點只用台北市、板橋、坪林、礁溪、東京、紐約、多倫多、柏林、香港這類公開地名。每個 task commit 前跑 `uv run pytest -q tests/test_privacy.py`。
- 測試：離線 `uv run pytest -q -m 'not live'`，全部 `uv run pytest -q`。`live` 測試對 Nominatim 每秒最多 1 次，對 NCDR 每 3 秒最多 1 次。
- 不 push、不開 PR，除非使用者同意。

## Review Focus

1. **地點跨時區**：同時查台北和東京時，`local_time` 只有一個，可能讓模型把東京的「今天」算錯。期望：時區和 [1] 不同的地點，在自己那一行附上 `local_time`。→ Task 11 測試 `test_multi_place_in_another_timezone_gets_its_own_local_time`。
2. **NCDR 的時間格式**：`2026/10/23 下午 08:00:00`，其中「上午 12 點」和「下午 12 點」最容易算錯。期望：`上午 12:xx` 是 00:xx，`下午 12:xx` 是 12:xx。→ Task 6 測試 `test_ncdr_time_parses_noon_and_midnight`。
3. **某個警報來源壞掉或格式改變**：例如 NCDR 回傳限速訊息、GDACS 回傳 500、MeteoAlarm 改了 JSON。期望：天氣照常輸出，該地點顯示 `alerts: unavailable (...)`，不會變成 `internal_error`。→ Task 5 測試 `test_provider_crash_marks_unavailable_not_internal_error`。
4. **舊設定檔**：預設地點沒有 `country_code`，WeatherKit 區塊還留著 `country_code: TW`。期望：不報錯，第一次執行時 reverse geocode 一次並寫回，之後就不再查。→ Task 3 測試 `test_default_without_country_is_filled_once_and_saved`。
5. **颱風跨越換日線**：GDACS 的經度可能出現 180 和 -179.2 這種寫法。期望：距離用大圓距離計算，不會因為經度差 359 度就判定成很遠。→ Task 1 測試 `test_distance_across_the_dateline`。

---

## 檔案結構

```
src/weatherwise/
├── SKILL.md                       更新：警報三種狀態、颱風轉述、多地點、移除 --country-code
├── scripts/
│   ├── weatherwise.py             修改：多地點、--detail、too_many_places、單一地點失敗不影響其他地點
│   ├── ww_errors.py               修改：新增 too_many_places
│   ├── ww_http.py                 修改：get(url, headers, text=False)、VERSION 2.0.0
│   ├── ww_cache.py                新增：單次執行去重 + 磁碟 TTL 快取
│   ├── ww_geo.py                  新增：距離、方位、點到折線距離、點是否在多邊形內
│   ├── ww_model.py                修改：Place 加國碼與行政區、Alert、PlaceAlerts、Cyclone、Report.next_hour
│   ├── ww_places.py               修改：addressdetails、行政區優先、reverse geocode
│   ├── ww_sources.py              修改：用地點國碼、移除 WeatherKit 警報、forecastNextHour、Open-Meteo 多座標
│   ├── ww_alerts.py               新增：分派、過期排除、去重、跨地點合併、颱風合併、上限
│   ├── ww_alerts_tw.py            新增：NCDR
│   ├── ww_alerts_jp.py            新增：JMA
│   ├── ww_alerts_hk.py            新增：HKO
│   ├── ww_alerts_us.py            新增：NWS
│   ├── ww_alerts_ca.py            新增：ECCC
│   ├── ww_alerts_eu.py            新增：MeteoAlarm
│   ├── ww_cyclones.py             新增：GDACS
│   ├── ww_render.py               修改：新的單一／多地點格式
│   ├── ww_config.py               修改：default 可帶 country_code／region／locality
│   └── ww_setup.py                修改：set-default 存國碼與行政區、移除 country_code
├── references/sources.md          新增：各資料來源與出處標示（JMA、MeteoAlarm、GDACS 要求）
tests/
├── fixtures/alerts/               新增：精簡過的真實回應（ncdr.xml、gdacs_list.json、gdacs_geometry.json、jma_area.json、jma_130000.json、hko_warnsum.json、nws_point.json、eccc.json、meteoalarm_de.json）
├── test_geo.py  test_cache.py  test_alerts.py  test_alerts_tw.py  test_alerts_jp.py
├── test_alerts_simple.py（HKO、NWS）  test_alerts_poly.py（ECCC、MeteoAlarm）  test_cyclones.py
└── 修改：conftest.py、test_places.py、test_sources.py、test_render.py、test_cli.py、test_robustness.py、test_live.py、test_setup.py
```

---

### Task 0: 分支

- [ ] **Step 1：問使用者**。spec 的 commit `745eddc` 不小心落在 `routine-keeper` 分支。問使用者要怎麼處理：(a) 從 `main` 開 `weatherwise-alerts` 分支，cherry-pick `745eddc` 和這份計畫的 commit，再把這兩個 commit 從 `routine-keeper` 移除；(b) 直接在目前的分支上做。**沒得到回答前不要改動 `routine-keeper`。**
- [ ] **Step 2**：照使用者的回答建立分支，然後執行 `uv run pytest -q -m 'not live'`。預期結果：`264 passed`。

---

### Task 1: 基礎：HTTP 文字回應、幾何、資料結構、錯誤代碼

**Files:**
- Modify: `src/weatherwise/scripts/ww_http.py`、`ww_model.py`、`ww_errors.py`、`weatherwise.py`（`http=get_json` → `http=get`）、`ww_places.py`、`ww_sources.py`、`ww_setup.py`（呼叫端改名）
- Create: `src/weatherwise/scripts/ww_geo.py`
- Test: `tests/test_geo.py`、`tests/test_model.py`、`tests/conftest.py`

**Interfaces:**
- Produces:
  - `ww_http.get(url: str, headers: dict | None = None, *, text: bool = False)`：`text=True` 時回傳解碼後的 `str`，不解析 JSON。錯誤處理和原本的 `get_json` 相同。`get_json` 刪除，全部呼叫端改用 `get`。
  - `ww_http.VERSION = "2.0.0"`。
  - `ww_geo.distance_km(lat1, lon1, lat2, lon2) -> float`（haversine，地球半徑 6371 km）
  - `ww_geo.bearing(lat1, lon1, lat2, lon2) -> str`：從點 1 看點 2 的 8 方位（`N NE E SE S SW W NW`）
  - `ww_geo.distance_to_path_km(lat, lon, path: list[tuple[float, float]]) -> float`：到折線（`(lat, lon)` 序列）的最短距離。以 300 km 以內的線段來說，用等距圓柱投影近似即可
  - `ww_geo.point_in_polygon(lat, lon, ring: list[tuple[float, float]]) -> bool`（ray casting，`(lat, lon)` 順序）
  - `ww_model.Place` 新增欄位（都有預設值 `None`）：`country_code: str | None`（小寫 ISO2）、`region: str | None`（台灣的縣市、日本的都道府縣、美國的州）、`locality: str | None`（台灣的鄉鎮市區、日本的市區町村）
  - `ww_model.Alert`（dataclass）：`kind: str`、`severity: str`（`extreme`／`severe`／`moderate`／`minor`）、`title: str`、`summary: str`（≤ 60 字）、`detail: str`（全文）、`expires: datetime | None`（aware）、`updated: datetime | None`、`source: str`（例如 `ncdr`）、`key: str`
  - `ww_model.PlaceAlerts`（dataclass）：`status: str`（`ok`／`unsupported`／`unavailable`）、`alerts: list[Alert]`、`reason: str = ""`
  - `ww_model.Cyclone`（dataclass）：`name: str`（例如 `CHAMPI-26`）、`level: str`（`Green`／`Orange`／`Red`）、`lat: float`、`lon: float`、`track: list[tuple[float, float]]`、`wind_polygons: list[list[tuple[float, float]]]`、`severity_text: str`
  - `ww_model.Report`：移除 `alerts`，新增 `next_hour: str | None = None`（`None` 代表這個來源沒有這項資料，例如 Open-Meteo）
  - `SEVERITY_ORDER = ["extreme", "severe", "moderate", "minor"]`，放在 `ww_model.py`
  - `ww_errors.ACTIONS["too_many_places"] = "keep only the places that matter most (for a trip: the destination, plus the start if needed), at most 5, and run again"`
- `tests/conftest.py`：`FakeHttp.__call__(self, url, headers=None, *, text=False)`，簽名要相容。新增 `fixture(name) -> str`，讀取 `tests/fixtures/alerts/<name>`。新增 autouse fixture，把 `WEATHERWISE_CACHE_DIR` 指向 `tmp_path`，避免測試寫到真實的快取。

- [ ] **Step 1：寫失敗的測試**（`tests/test_geo.py`）

```python
def test_distance_taipei_to_champi_position():
    assert 480 < distance_km(25.033, 121.565, 21.2, 125.0) < 560

def test_distance_across_the_dateline():
    assert distance_km(24.2, 180.0, 24.2, -179.2) < 100

def test_bearing_of_a_typhoon_southeast_of_taipei():
    assert bearing(25.033, 121.565, 21.2, 125.0) == "SE"

def test_distance_to_forecast_path():
    path = [(20.9, 125.4), (22.2, 124.3), (23.9, 123.3), (25.7, 122.8)]
    assert 100 < distance_to_path_km(24.83, 121.77, path) < 180  # 礁溪

def test_point_in_polygon():
    square = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]
    assert point_in_polygon(5, 5, square) and not point_in_polygon(15, 5, square)
```

`tests/test_model.py` 新增：`Place("x", 1, 2)` 的 `country_code`、`region`、`locality` 都是 `None`；`Report` 沒有 `alerts` 屬性。

- [ ] **Step 2**：`uv run pytest -q tests/test_geo.py tests/test_model.py`。預期結果：FAIL（`ww_geo` 不存在）。
- [ ] **Step 3**：依 Interfaces 實作。`Report.alerts` 移除後，`ww_sources.py` 和 `ww_render.py` 會壞掉：`ww_sources` 先不回傳 alerts；`render_report` 先暫時不輸出警報那一行（Task 11 會重寫）。同時刪掉 `test_render.py`、`test_sources.py`、`test_cli.py` 裡只測 WeatherKit 警報的測試（`test_alerts_none_and_listed`、`test_unsupported_alerts_tell_the_model_not_to_say_none`、`test_weatherkit_limits_days_and_lists_alerts`、`test_weatherkit_where_apple_has_no_alerts_is_unsupported`、`test_weatherkit_with_no_active_alerts_is_none`、`test_weatherkit_skips_alerts_where_apple_has_none`，以及 CLI 裡斷言最後一行是 alerts 的部分）。這些行為由後面的 task 取代。
- [ ] **Step 4**：`uv run pytest -q -m 'not live'`。預期結果：全部 PASS。
- [ ] **Step 5**：commit `refactor: weatherwise http text responses, geo helpers, alert data types`

---

### Task 2: 快取

**Files:**
- Create: `src/weatherwise/scripts/ww_cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Produces: `ww_cache.Cached(http, now_ts: int, cache_dir: Path | None = None)`。它是一個可呼叫物件，簽名和 `ww_http.get` 相同（`(url, headers=None, *, text=False)`）。`ww_cache.cache_dir() -> Path`。`ww_cache.ttl_for(url: str) -> int`（0 代表只做單次執行去重，不寫磁碟）。
- TTL 依 URL 前綴：`alerts.ncdr.nat.gov.tw`、`www.jma.go.jp/bosai/warning`、`data.weather.gov.hk`、`api.weather.gov`、`api.weather.gc.ca`、`feeds.meteoalarm.org` → 300；`www.gdacs.org` → 900；`api.open-meteo.com`、`weatherkit.apple.com/api/v1/weather` → 900；`www.jma.go.jp/bosai/common/const/area.json` → 30 天；`nominatim.openstreetmap.org` → 30 天；其他 → 0。
- 磁碟格式：每個 URL 一個檔案，檔名是 `sha256(url)`，內容是 `{"t": <寫入時間>, "text": bool, "body": <回應>}`。寫入用暫存檔加 `os.replace`。
- 例外（`HttpError`、`WwError`）不快取，直接往上丟。

- [ ] **Step 1：寫失敗的測試**

```python
def test_same_url_in_one_run_is_fetched_once(tmp_path):
    http = FakeHttp({"https://api.weather.gov/": {"features": []}})
    c = Cached(http, now_ts=1000, cache_dir=tmp_path)
    c("https://api.weather.gov/alerts/active?point=1,2"); c("https://api.weather.gov/alerts/active?point=1,2")
    assert len(http.calls) == 1

def test_disk_cache_is_used_within_ttl_and_refreshed_after(tmp_path):
    url = "https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx"
    http = FakeHttp({url: "<feed/>"})
    Cached(http, 1000, tmp_path)(url, text=True)
    Cached(http, 1000 + 299, tmp_path)(url, text=True)
    assert len(http.calls) == 1
    Cached(http, 1000 + 301, tmp_path)(url, text=True)
    assert len(http.calls) == 2

def test_errors_are_not_cached(tmp_path): ...       # 第一次 raise HttpError(500)，第二次成功時要真的再請求
def test_broken_cache_file_is_ignored(tmp_path): ... # 快取檔寫入垃圾內容 → 照常請求，不報錯
def test_unwritable_cache_dir_is_ignored(tmp_path): ...  # cache_dir 指向一個檔案 → 照常回傳
def test_unknown_url_is_not_written_to_disk(tmp_path): ...  # ttl 0 → tmp_path 裡沒有檔案
```

- [ ] **Step 2**：執行 `uv run pytest -q tests/test_cache.py`。預期結果：FAIL。
- [ ] **Step 3**：實作。
- [ ] **Step 4**：執行 `uv run pytest -q tests/test_cache.py`。預期結果：PASS。
- [ ] **Step 5**：commit `feat: weatherwise request cache — one fetch per run, TTL on disk`

---

### Task 3: 地點：國碼、行政區、坪林修正

**Files:**
- Modify: `src/weatherwise/scripts/ww_places.py`、`ww_config.py`（`_shape_problem` 接受 `default.country_code`／`region`／`locality` 為字串或不存在）、`ww_setup.py`（`set_default` 把三個欄位一起存進設定）
- Test: `tests/test_places.py`、`tests/test_setup.py`、`tests/test_live.py`

**Interfaces:**
- Consumes：`Place` 的新欄位（Task 1）。
- Produces：
  - `geocode(query, lang, global_search, http) -> Place`：回傳的 Place 會帶 `country_code`、`region`、`locality`。
  - `reverse(lat, lon, lang, http) -> Place`：呼叫 `https://nominatim.openstreetmap.org/reverse?format=json&addressdetails=1&zoom=14&lat=..&lon=..&accept-language=..`。
  - `resolve_place(...)`：座標輸入時，用 `reverse` 補上國碼和行政區（名稱維持 `"lat,lon"`）。預設地點缺 `country_code` 時，也用 `reverse` 補上。
  - `ensure_default_complete(cfg, d, lang, http) -> None`，放在 `ww_setup.py`：預設地點缺 `country_code` 時，reverse 一次並 `save_config` 寫回。由 CLI 在用到預設地點時呼叫。
- 規則：
  - 搜尋參數加上 `addressdetails=1`、`limit=5`。在結果中，優先選 `class == "boundary"` 且 `type == "administrative"`，而且 `name` 等於查詢字串或以查詢字串開頭的結果。沒有的話，取第一筆。
  - `country_code` 取 `address.country_code`。
  - `region`：依序取 `address` 裡的 `city`（直轄市）、`county`、`state`、`province`，取第一個有值的。`locality`：依序取 `suburb`、`town`、`city_district`、`village`、`municipality`、`city`，取第一個不等於 `region` 的值。**實作前**先用 Step 1 的 live 測試確認台灣、日本、美國的實際欄位；如果和上面的對照不同，改對照表並在測試裡註明。

- [ ] **Step 1：寫 live 測試**（`tests/test_live.py`，每個之間要有既有的 `polite` 間隔）

```python
@pytest.mark.parametrize("q,region,locality", [
    ("坪林", "新北市", "坪林區"), ("礁溪", "宜蘭縣", "礁溪鄉"), ("板橋", "新北市", "板橋區")])
def test_geocode_prefers_the_district_over_a_same_named_village(q, region, locality, polite):
    p = geocode(q, "zh-TW", False, get)
    assert (p.country_code, p.region, p.locality) == ("tw", region, locality)

def test_geocode_tokyo_has_japanese_municipality(polite): ...  # 東京都千代田区 → country_code "jp"、region 含「東京」
def test_reverse_fills_country_for_coordinates(polite): ...    # 40.71,-74.0 → "us"
```

- [ ] **Step 2**：執行 `uv run pytest -q -m live tests/test_live.py -k "geocode or reverse"`，記錄實際的 address 欄位。預期結果：坪林會 FAIL（現在會定位到苗栗）。
- [ ] **Step 3：寫離線測試**（`tests/test_places.py`），用 Step 2 看到的真實 JSON 精簡成 fixture：

```python
def test_administrative_match_beats_the_first_result():
    # 第一筆是苗栗縣卓蘭鎮的「坪林」（村里），第三筆是新北市坪林區（boundary/administrative）
    p = geocode("坪林", "zh-TW", False, FakeHttp({NOMINATIM: PINGLIN_RESULTS}))
    assert p.region == "新北市" and p.locality == "坪林區"

def test_search_asks_for_address_details_and_five_results(): ...
def test_coordinates_get_country_from_reverse_geocoding(): ...
def test_default_without_country_is_filled_once_and_saved(config_dir): ...  # 第二次呼叫不再請求 reverse
def test_old_weatherkit_country_code_in_config_is_accepted(config_dir): ...  # load_config 不報錯
```

`tests/test_setup.py`：`set_default` 存進去的 `default` 要有 `country_code`、`region`、`locality`。

- [ ] **Step 4**：實作，然後執行 `uv run pytest -q -m 'not live'` 和 Step 1 的 live 測試。預期結果：全部 PASS。
- [ ] **Step 5**：commit `fix: weatherwise geocoding prefers districts (坪林) and records country and region`

---

### Task 4: 預報來源：國碼 bug、WeatherKit 未來一小時、Open-Meteo 多座標

**Files:**
- Modify: `src/weatherwise/scripts/ww_sources.py`、`ww_setup.py`（`set_weatherkit` 移除 `country_code` 參數，`wk` 字典不再寫入這個欄位）、`weatherwise.py`（移除 `--country-code`）
- Test: `tests/test_sources.py`、`tests/test_setup.py`、`tests/test_live.py`

**Interfaces:**
- Consumes：`Place.country_code`（Task 3）。
- Produces：
  - `fetch_weatherkit(place, days, lang, wk, http, now_ts) -> Report`：**不再呼叫 availability**。`dataSets=currentWeather,forecastDaily,forecastNextHour`，`countryCode=place.country_code.upper()`（沒有國碼時就不帶這個參數）。回應裡沒有 `forecastNextHour` 時，`next_hour = "unavailable here"`。
  - `summarize_next_hour(data: dict, tz: str) -> str`：依 `forecastNextHour.summary`（每段有 `startTime`、`condition`、`precipitationIntensity`）和 `minutes` 產生一行摘要。規則：全部是 `clear` → `"no rain expected in the next hour"`；現在就在下雨且一小時內會停 → `"rain now, stopping ~HH:MM"`；現在沒下但之後會下 → `"rain starting ~HH:MM"`；持續下整個小時 → `"rain for the whole hour"`。最大強度 ≥ 4 mm/h 時，加上 `", heavy"`。時間用地點的時區。
  - `fetch_open_meteo_many(places: list[Place], days: int, http) -> list[Report]`：一次請求，`latitude`、`longitude`、`timezone` 都用逗號串接。地點只有 1 個時回應是 dict，多個時是 list，兩種都要處理。`fetch_open_meteo(place, days, http)` 改成呼叫這個函式並取第一筆。
  - `WEATHERKIT_AVAILABILITY` 常數刪除。

- [ ] **Step 1：寫失敗的測試**

```python
def test_weatherkit_uses_the_place_country_not_a_setting(p8_key):
    http = FakeHttp({WK: WEATHERKIT})
    fetch_weatherkit(Place("New York", 40.71, -74.0, "America/New_York", "us"), 1, "en", wk(p8_key), http, NOW_TS)
    assert "countryCode=US" in http.calls[0][0] and "availability" not in http.calls[0][0]

def test_weatherkit_asks_for_next_hour_and_reports_unavailable_when_missing(p8_key): ...
def test_next_hour_rain_starting(): assert summarize_next_hour(NEXT_HOUR_RAIN_AT_2105, "Asia/Tokyo") == "rain starting ~21:05"
def test_next_hour_all_clear(): ...
def test_next_hour_heavy_rain_now_stopping(): ...  # → "rain now, stopping ~21:40, heavy"
def test_open_meteo_many_places_is_one_request(): ...  # 2 個地點 → 1 次呼叫，URL 含 "latitude=25.033,24.827"，回傳 2 個 Report
def test_open_meteo_has_no_next_hour(): assert fetch_open_meteo(...).next_hour is None
def test_weatherkit_setup_no_longer_saves_country_code(config_dir, p8_key): ...
```

`NEXT_HOUR_*` fixtures 放在 `conftest.py`。WeatherKit `forecastNextHour` 的欄位名稱以 Apple 的 WeatherKit REST API 文件為準；實作者可以用 `test_live.py` 查日本或美國的地點（實測這兩國有這項資料）來確認。

- [ ] **Step 2**：執行 `uv run pytest -q tests/test_sources.py tests/test_setup.py`。預期結果：FAIL。
- [ ] **Step 3**：實作。
- [ ] **Step 4**：執行 `uv run pytest -q -m 'not live'`。預期結果：PASS。另外在 `test_live.py` 加上 `test_weatherkit_next_hour_in_tokyo`（本機有金鑰時才跑），並執行它。
- [ ] **Step 5**：commit `fix: weatherkit uses each place's country; add next-hour rain; one open-meteo request for many places`

---

### Task 5: 警報核心

**Files:**
- Create: `src/weatherwise/scripts/ww_alerts.py`
- Test: `tests/test_alerts.py`

**Interfaces:**
- Consumes：`Alert`、`PlaceAlerts`、`Cyclone`、`Place`（Task 1、3），以及 `ww_geo`。
- Produces：
  - provider 的介面：`def alerts_for(places: list[Place], http, now: datetime) -> list[list[Alert] | None]`。回傳的 list 長度等於 `places`，`None` 代表這個地點找不到所屬區域（輸出 `unsupported`）。抓不到資料時直接 raise（任何例外都可以）。
  - `PROVIDERS: dict[str, Callable]`：`{"tw": ww_alerts_tw.alerts_for, "jp": ..., "hk": ..., "us": ..., "ca": ..., **{cc: ww_alerts_eu.alerts_for for cc in ww_alerts_eu.COUNTRIES}}`。每個 provider task 完成時自己加進來。這個 task 先放空的 dict，測試用 monkeypatch 替換。
  - `collect(places: list[Place], http, now: datetime) -> tuple[list[PlaceAlerts], list[tuple[Cyclone, list[int]]]]`：
    1. 依 `country_code` 把地點分組，每個 provider 只呼叫一次，傳入同國的所有地點。
    2. provider raise → 那一組地點都是 `PlaceAlerts("unavailable", [], reason)`，`reason` 是例外的類別名稱，或 `WwError.code`／`HttpError` 的狀態碼，例如 `"ncdr HTTP 500"`。沒有 provider 的國家 → `unsupported`。
    3. 排除 `expires < now` 的警報。同一個 `key` 只保留 `updated` 最新的一則。依 `SEVERITY_ORDER` 排序。
    4. 呼叫 `ww_cyclones.nearby(places, http, now)`（Task 7；這個 task 先用 monkeypatch）。GDACS 失敗時，忽略並當作沒有颱風，不影響各地點的狀態。
    5. 颱風合併：某則 `kind == "typhoon"` 的 Alert，若它的 `title + detail` 裡出現颱風名稱去掉 `-NN` 後的部分（不分大小寫），就把該颱風記為「已合併到這則 Alert」。回傳的颱風清單裡每項附上適用的地點索引；已合併的颱風改掛在 Alert 上（`Alert` 新增欄位 `cyclone: Cyclone | None = None`）。
  - `CAP = 6`。

- [ ] **Step 1：寫失敗的測試**（provider 和 `nearby` 都用 monkeypatch 換成假的）

```python
def test_each_provider_is_called_once_for_all_its_places(): ...      # 兩個台灣地點 → tw provider 被呼叫 1 次，收到 2 個地點
def test_country_without_provider_is_unsupported(): ...             # "kr" → status "unsupported"
def test_provider_crash_marks_unavailable_not_internal_error(): ...  # raise ValueError → "unavailable"，reason 含 "ValueError"
def test_expired_alerts_are_dropped(): ...
def test_only_the_newest_alert_per_key_is_kept(): ...               # 同 key 的 3 則 → 留 updated 最大的
def test_alerts_sorted_by_severity(): ...
def test_cyclone_named_in_a_local_alert_is_merged():
    # Alert(kind="typhoon", detail="…國際命名 CHAMPI…") + Cyclone("CHAMPI-26") → 回傳的颱風清單為空，alert.cyclone.name == "CHAMPI-26"
def test_cyclone_not_named_locally_is_listed_on_its_own(): ...
def test_gdacs_failure_does_not_change_alert_status(): ...
```

- [ ] **Step 2**：執行 `uv run pytest -q tests/test_alerts.py`。預期結果：FAIL。
- [ ] **Step 3**：實作。
- [ ] **Step 4**：執行 `uv run pytest -q tests/test_alerts.py`。預期結果：PASS。
- [ ] **Step 5**：commit `feat: weatherwise alert pipeline — dispatch, expiry, dedupe, cyclone merge`

---

### Task 6: 台灣 NCDR

**Files:**
- Create: `src/weatherwise/scripts/ww_alerts_tw.py`、`tests/fixtures/alerts/ncdr.xml`
- Modify: `ww_alerts.py`（`PROVIDERS["tw"]`）
- Test: `tests/test_alerts_tw.py`、`tests/test_live.py`

**Interfaces:**
- Produces：`ww_alerts_tw.alerts_for(places, http, now)`、`parse_ncdr_time(s: str) -> datetime`（Asia/Taipei）、`FEED = "https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx"`。
- 規則（細節見 spec 的「已實測的來源」）：
  - 用 `http(FEED, text=True)` 抓一次，以 `xml.etree.ElementTree` 解析（命名空間 Atom 是 `http://www.w3.org/2005/Atom`，CAP 是 `urn:oasis:names:tc:emergency:cap:1.1`）。內容有 `<WarningMessage>` 時，raise `WwError("service_error", "ncdr rate limited")`。
  - 只保留 `author/name == "中央氣象署"`、title 在 `{"颱風", "降雨", "強風", "高溫", "低溫", "濃霧", "巨浪"}` 裡、`cap:status == "Actual"` 的 entry。
  - `kind` 對照：颱風 → `typhoon`、降雨 → `rain`、強風 → `wind`、高溫 → `heat`、低溫 → `cold`、濃霧 → `fog`、巨浪 → `marine`。
  - `key = "ncdr:" + title`；`updated` 取 `<updated>`；`expires` 取 `cap:expires`。
  - 涵蓋判斷：颱風一律涵蓋。其他類別要 `summary` 裡出現地點的 `region`，比對前把「台」換成「臺」再比。地點沒有 `region` 時，回傳 `None`。
  - severity：文字裡有 `紅色燈號`、`超大豪雨` → `extreme`；有 `橙色燈號`、`大豪雨`、`豪雨`，或 kind 是颱風 → `severe`；有 `黃色燈號`、`大雨` → `moderate`；其他 → `minor`。取最高的一個。
  - `title` 顯示用：降雨類用文字裡最高的雨量等級（`超大豪雨`／`大豪雨`／`豪雨`／`大雨`），強風類用 `強風 <顏色>燈號`，颱風類用 `颱風警報` 加上 summary 裡的「X度颱風 名稱」（例如 `颱風警報 中度颱風 薔琵`），其他類就用原本的 title。
  - `summary`：在 summary 中，找出第一個包含地點 `region` 的句段（以 `，`、`。` 分段），截到 60 字。颱風類用「中心位置」那一段。找不到時，取前 60 字。
  - `detail`：原始 summary 全文。
- `parse_ncdr_time`：`2026/10/23 下午 08:00:00` → 2026-10-23 20:00 +08:00；`上午 12:30:00` → 00:30；`下午 12:30:00` → 12:30。

- [ ] **Step 1：抓 fixture**：寫一個暫時的腳本（放 scratchpad，不 commit），抓一次 feed，保留下列 entry 後存成 `tests/fixtures/alerts/ncdr.xml`：最新的降雨（涵蓋新北市、宜蘭縣）、同一則降雨的較舊版本、強風兩個版本、颱風兩個版本、一則公路局道路封閉、一則已過期的高溫。過期判斷以 `conftest.NOW` 之外另定的 `NCDR_NOW` 為準。存檔後執行 `uv run pytest -q tests/test_privacy.py`。
- [ ] **Step 2：寫失敗的測試**

```python
NCDR_NOW = datetime(2026, 10, 22, 20, 30, tzinfo=ZoneInfo("Asia/Taipei"))
BANQIAO = Place("板橋區", 25.011, 121.459, "Asia/Taipei", "tw", "新北市", "板橋區")
JIAOXI = Place("礁溪鄉", 24.827, 121.775, "Asia/Taipei", "tw", "宜蘭縣", "礁溪鄉")
TAICHUNG_NO_RAIN = Place("x", 24.15, 120.67, "Asia/Taipei", "tw", "南投縣", "x")  # 依 fixture 選一個不在降雨名單裡的縣市

def test_ncdr_keeps_only_cwa_weather_alerts(): ...         # 沒有 "道路封閉"
def test_ncdr_filters_by_county(): ...                      # 降雨只出現在 BANQIAO 和 JIAOXI，不出現在 TAICHUNG_NO_RAIN
def test_ncdr_typhoon_covers_every_place(): ...
def test_ncdr_severity_and_display_title(): ...             # 宜蘭的降雨 → extreme（超大豪雨）
def test_ncdr_summary_is_short_and_about_the_place(): ...   # len ≤ 60 且含 "宜蘭"
def test_ncdr_time_parses_noon_and_midnight(): ...
def test_ncdr_rate_limit_message_raises(): ...              # FakeHttp 回傳 "<WarningMessage><Warning>限制存取間隔時間為3秒</Warning></WarningMessage>"
def test_ncdr_place_without_region_is_none(): ...
def test_ncdr_through_collect_dedupes_versions(): ...       # 經過 ww_alerts.collect，強風只剩 1 則
```

- [ ] **Step 3**：執行 `uv run pytest -q tests/test_alerts_tw.py`。預期結果：FAIL。實作後再執行，預期結果：PASS。
- [ ] **Step 4**：`test_live.py` 加上 `test_ncdr_feed_still_has_the_fields_we_parse`（feed 能解析，每則 entry 都有 `author`、`title`、`cap:expires`）。執行一次。
- [ ] **Step 5**：commit `feat: weatherwise alerts for Taiwan from NCDR`

---

### Task 7: 全球熱帶氣旋 GDACS

**Files:**
- Create: `src/weatherwise/scripts/ww_cyclones.py`、`tests/fixtures/alerts/gdacs_list.json`、`gdacs_geometry.json`
- Test: `tests/test_cyclones.py`、`tests/test_live.py`

**Interfaces:**
- Produces：`ww_cyclones.nearby(places, http, now) -> list[tuple[Cyclone, list[int]]]`、`describe(c: Cyclone, place: Place) -> str`、常數 `FETCH_KM = 2000`、`NEAR_KM = 800`、`MAX_AGE_HOURS = 24`。
- 規則：
  - 列表：`https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=TC`。只留 `iscurrent == "true"`，且 `todate` 在 `now` 前 `MAX_AGE_HOURS` 小時內的事件。
  - 對任一地點在 `FETCH_KM` 內的事件，抓 `properties.url.geometry`。`Point_Centroid` 是目前位置；`forecast == True` 的 `LineString` 依序接成 `track`；`Poly_Green` 多邊形是 `wind_polygons`（綠色是最外圈的暴風範圍）。座標是 `[lon, lat]`，要轉成 `(lat, lon)`。
  - 某地點符合「落在任一 `wind_polygons` 內」，或「到目前位置或 `track` 的距離 ≤ `NEAR_KM`」，就加入該地點的索引。
  - `describe` 輸出：`"<name> (GDACS <level>): now ~<d> km <bearing>, forecast closest ~<d2> km"`，距離四捨五入到 10 km。**不寫時間**（GDACS 沒有提供）。

- [ ] **Step 1**：抓 fixture。列表只保留 CHAMPI-26，以及一個遠方的事件（例如東太平洋的 VANCE-26）。geometry 只保留 centroid、Poly_Green 和 forecast 線段。
- [ ] **Step 2：寫失敗的測試**

```python
GDACS_NOW = datetime(2026, 10, 22, 12, 30, tzinfo=timezone.utc)

def test_champi_is_near_taipei_and_jiaoxi(): ...       # 兩個地點的索引都在
def test_far_cyclone_is_ignored_and_its_geometry_not_fetched(): ...  # VANCE 的 geometry URL 不在 http.calls 裡
def test_cyclone_not_near_berlin(): ...
def test_old_events_are_ignored(): ...                  # GDACS_NOW 加 3 天 → 空
def test_describe_has_distance_bearing_and_no_time(): ...  # 含 "SE"，不含 ":" 開頭的時間
def test_gdacs_list_parsed_once_for_many_places(): ...
```

- [ ] **Step 3**：執行測試，預期 FAIL，實作後再執行，預期 PASS。把 `ww_alerts.collect` 改為呼叫真正的 `nearby`，並用 Task 6 的 fixture 加上一個測試：台灣地點的颱風 Alert 會被合併，而且 `alert.cyclone.name == "CHAMPI-26"`。
- [ ] **Step 4**：在 `test_live.py` 加上 `test_gdacs_list_and_geometry_shape`，並執行。
- [ ] **Step 5**：commit `feat: weatherwise tropical cyclones near any place from GDACS`

---

### Task 8: 日本 JMA

**Files:**
- Create: `src/weatherwise/scripts/ww_alerts_jp.py`、`tests/fixtures/alerts/jma_area.json`（精簡版）、`jma_130000.json`
- Modify: `ww_alerts.py`（`PROVIDERS["jp"]`）
- Test: `tests/test_alerts_jp.py`、`tests/test_live.py`

**Interfaces:**
- Produces：`ww_alerts_jp.alerts_for(places, http, now)`。
- 規則：
  - 區域定義：`https://www.jma.go.jp/bosai/common/const/area.json`（快取 30 天）。用地點的 `locality` 比對 `class20s` 的 `name`，完全相符才算；比不到時，去掉結尾的「市」「区」「町」「村」再比一次。找到 class20 後，沿著 `parent` 往上找 `offices` 的代碼。都比不到時，回傳 `None`。
  - 警報：`https://www.jma.go.jp/bosai/warning/data/warning/<office code>.json`，同一個 office 只抓一次。在 `areaTypes` 中找出該 class20 代碼的 `warnings`，略過 `status` 是 `解除` 或 `発表警報・注意報はなし` 的項目。
  - 警報代碼（`code`）轉成名稱和 kind 的對照表，以 JMA 公開的代碼表為準，至少要涵蓋：大雨、洪水、暴風、暴風雪、大雪、波浪、高潮的警報與注意報，以及特別警報。severity：特別警報 → `extreme`，警報 → `severe`，注意報 → `moderate`。
  - `key = "jma:" + class20 code + ":" + code`；`summary` 用 `headlineText` 截到 60 字；`expires = None`（JMA 沒有提供）；`updated = reportDatetime`。

- [ ] **Step 1**：抓 fixture。`jma_area.json` 只保留東京都的 office，以及千代田区等 2 到 3 個 class20 和它們的上層。抓一份有警報的東京 warning JSON；如果當天沒有警報，就手動在 fixture 裡改一個項目的 status，並在檔案旁的註解說明。
- [ ] **Step 2：寫失敗的測試**：`test_jma_finds_chiyoda_by_municipality_name`、`test_jma_unknown_municipality_is_none`、`test_jma_lists_active_warning_with_severity`、`test_jma_skips_cleared_warnings`、`test_jma_one_request_per_office_for_two_tokyo_places`。
- [ ] **Step 3**：先執行測試，預期 FAIL；實作後再執行，預期 PASS。
- [ ] **Step 4**：在 live 測試加上 `test_jma_area_and_tokyo_warning_shape`，並執行一次。
- [ ] **Step 5**：commit `feat: weatherwise alerts for Japan from JMA`

---

### Task 9: 香港 HKO、美國 NWS

**Files:**
- Create: `src/weatherwise/scripts/ww_alerts_hk.py`、`ww_alerts_us.py`、`tests/fixtures/alerts/hko_warnsum.json`、`nws_point.json`
- Modify: `ww_alerts.py`（`PROVIDERS["hk"]`、`PROVIDERS["us"]`）
- Test: `tests/test_alerts_simple.py`、`tests/test_live.py`

**Interfaces / 規則:**
- HKO：抓 `https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum&lang=tc` 一次，所有香港地點共用。回應是 `{}` 時，就是空清單。每個 key（例如 `WRAIN`、`WTCSGNL`）是一則警報：`title = name`、`key = "hko:" + code`、`updated = updateTime`、`expires = expireTime`（如果有）。熱帶氣旋信號（`WTCSGNL`）的 kind 是 `typhoon`。8 號以上、紅雨、黑雨 → `severe`，其他 → `moderate`。
- NWS：每個地點請求一次 `https://api.weather.gov/alerts/active?point=<lat>,<lon>`（座標到小數點後 4 位）。`title = properties.event`、`summary = properties.headline` 截 60 字、`detail = properties.description`、`severity = properties.severity` 轉小寫（`Unknown` → `minor`）、`expires = properties.expires`（沒有的話用 `ends`）、`key = "nws:" + properties.id`。`event` 裡有 `Hurricane` 或 `Tropical Storm` 時，kind 是 `typhoon`。

- [ ] **Step 1**：抓 fixture。HKO 當天回傳 `{}`，所以另外依 HKO 開放資料文件的格式，寫一份有 `WRAIN` 和 `WTCSGNL` 的 fixture，並註明是依文件手寫的。NWS 找一個目前有警報的點來抓（可以先查 `https://api.weather.gov/alerts/active` 挑一個），存成精簡版。
- [ ] **Step 2：寫失敗的測試**：`test_hko_empty_is_no_alerts`、`test_hko_signal_8_is_severe_typhoon`、`test_hko_one_request_for_two_places`、`test_nws_maps_fields`、`test_nws_one_request_per_place`、`test_nws_hurricane_is_typhoon_kind`。
- [ ] **Step 3**：先執行測試，預期 FAIL；實作後再執行，預期 PASS。
- [ ] **Step 4**：live 測試：`test_nws_point_shape`、`test_hko_warnsum_is_a_dict`。
- [ ] **Step 5**：commit `feat: weatherwise alerts for Hong Kong (HKO) and the US (NWS)`

---

### Task 10: 加拿大 ECCC、歐洲 MeteoAlarm

**Files:**
- Create: `src/weatherwise/scripts/ww_alerts_ca.py`、`ww_alerts_eu.py`、`tests/fixtures/alerts/eccc.json`、`meteoalarm_de.json`
- Modify: `ww_alerts.py`（`PROVIDERS["ca"]` 和 `ww_alerts_eu.COUNTRIES` 裡的所有國家）
- Test: `tests/test_alerts_poly.py`、`tests/test_live.py`

**Interfaces / 規則:**
- ECCC：用涵蓋所有加拿大地點的 bbox（外擴 0.5 度）請求一次 `https://api.weather.gc.ca/collections/weather-alerts/items?f=json&bbox=<minlon>,<minlat>,<maxlon>,<maxlat>&limit=500`。每個 feature 用 `point_in_polygon` 判斷是否涵蓋該地點（MultiPolygon 只要任一個涵蓋就算）。欄位對照依 Step 1 實際抓到的 properties 決定，要有標題（英文）、嚴重程度、失效時間、ID。`key = "eccc:" + id`。
- MeteoAlarm：`COUNTRIES: dict[str, str]`，ISO2 對應 feed 的 slug（例如 `"de": "germany"`、`"fr": "france"`、`"gb": "united-kingdom"`、`"it": "italy"`）。完整清單以 `https://feeds.meteoalarm.org` 首頁列出的國家為準，寫成常數。每個國家請求一次 `https://feeds.meteoalarm.org/api/v1/warnings/feeds-<slug>`。
  - 每則警報的 `alert.info[]` 取英文（`language` 以 `en` 開頭）的那一份，沒有的話取第一份。涵蓋判斷：`area[].polygon` 有值時，用 `point_in_polygon`；只有 geocode 時，比對 `areaDesc` 是否等於地點的 `region` 或 `locality`。都比不到時，該地點回傳 `None`。
  - severity 取 `info.severity` 轉小寫。`title = info.event`、`summary = info.headline`、`expires = info.expires`、`key = "meteoalarm:" + alert.identifier`。
  - 只保留 `info.category` 含 `Met` 的警報（排除非氣象類）。

- [ ] **Step 1**：抓 fixture（各保留 2 到 3 則：一則涵蓋測試地點、一則不涵蓋）。在 fixture 旁的註解記錄 MeteoAlarm 和 ECCC 實際的欄位名稱。如果 MeteoAlarm 的 area 都沒有 polygon，就在測試和 spec 的「留給實作者決定的」裡記錄這個狀況，改用 areaDesc 比對。
- [ ] **Step 2：寫失敗的測試**：`test_eccc_point_inside_polygon_gets_alert`、`test_eccc_point_outside_gets_none_listed`、`test_eccc_one_bbox_request_for_two_places`、`test_meteoalarm_berlin_gets_only_its_region`、`test_meteoalarm_unknown_region_is_none`、`test_meteoalarm_one_request_per_country`、`test_meteoalarm_non_met_category_is_dropped`。
- [ ] **Step 3**：先執行測試，預期 FAIL；實作後再執行，預期 PASS。
- [ ] **Step 4**：live 測試：`test_eccc_shape`、`test_meteoalarm_germany_shape`。
- [ ] **Step 5**：commit `feat: weatherwise alerts for Canada (ECCC) and Europe (MeteoAlarm)`

---

### Task 11: 輸出與 CLI

**Files:**
- Modify: `src/weatherwise/scripts/ww_render.py`、`weatherwise.py`
- Test: `tests/test_render.py`、`tests/test_cli.py`、`tests/test_robustness.py`

**Interfaces:**
- Consumes：`collect`（Task 5）、`fetch_open_meteo_many`、`fetch_weatherkit`（Task 4）、`describe`（Task 7）、`Cached`（Task 2）。
- Produces：
  - `render(entries: list[tuple[Place, Report | WwError, PlaceAlerts]], cyclones: list[tuple[Cyclone, list[int]]], now: datetime, fetched_at: datetime, days: int, notice: str | None, detail: bool) -> str`
  - CLI：`weatherwise [place ...] [--global] [--days N] [--lang TAG] [--json] [--detail] [--version]`
- 單一地點的格式（`days` 沒指定時預設 3）：

```
local_time: 2026-10-22T20:32 Thu
location: 板橋區, 新北市, 臺灣 (25.011, 121.459)
now: Rain 23°C
next_hour: unavailable here
daily:
  2026-10-22 Thu: Rain, 22–24°C, rain 99%
alerts (as of 20:17, current only — not a forecast for later days):
  - [extreme] 超大豪雨 新北市: <summary>, until 10-23 20:00
  - [severe] 颱風警報 中度颱風 薔琵: <summary>; CHAMPI-26 (GDACS Red): now ~470 km SE, forecast closest ~150 km
cyclones (track data, not a local official warning):
  - <describe()>
```

- 多地點的格式（`days` 沒指定時預設 1）：`[i] <name>: <cond> <temp>°C; today <lo>–<hi>°C, rain <n>%`。如果有 `next_hour`，接 `; next hour: <...>`。`days > 1` 時，改成 `[i] <name>: now <cond> <temp>°C`，下面縮排列出每日預報。警報如果涵蓋多個地點，同一個 `key` 只列一次，並在 title 後面標 `[1][2]`。
- 狀態行：`alerts: none (as of HH:MM)`；`alerts: unsupported (no official alert source here; do not tell the user there are none)`；`alerts: unavailable (<reason>; do not tell the user there are none)`。多地點時，前面加上 `[i] `。
- `now:` 這行：只有在該地點有 kind 是 `wind` 的警報，或風速 ≥ 40 km/h 時，才加上 `, wind N km/h`。
- 每個地點超過 6 則警報時，加一行 `  - +N more (run again with --detail)`。`--detail`：不設上限，每則警報下面縮排列出 `detail` 全文。
- `source:` 這行不再輸出。`--json` 輸出 `{"places": [{"location", "source", "forecast": raw, "alerts": {"status", "reason", "items": [...]}}], "cyclones": [...], "notice"?}`。
- `fetched_at`：警報抓取的時間。用 `now`；如果是從快取取得，就用快取的寫入時間（`Cached` 要提供 `fetched_at(url) -> int | None`，在 Task 2 的檔案裡補上）。
- 某個地點的 `resolve_place` 或預報失敗時，該地點那一行改成 `[i] error: <code> (<detail>)`，下一行是 `    action: <ACTIONS[code]>`。只有全部失敗時，才用原本的單一錯誤格式，結束碼 1。只有一個地點時，行為和原本一樣，失敗就直接回錯誤。
- 超過 5 個地點 → `WwError("too_many_places", str(n))`。
- `main()` 裡用 `Cached(get, now_ts)` 包住 http（測試注入的 `http` 也要包，這樣才能測到「同一次執行只請求一次」）。

- [ ] **Step 1：寫失敗的測試**

```python
def test_single_place_with_alerts_and_cyclone(): ...   # 完整比對上面的單一地點格式
def test_multi_place_shared_alert_listed_once_with_tags(): ...  # "[1][2]" 只出現在一行
def test_multi_place_in_another_timezone_gets_its_own_local_time(): ...  # 台北 + 東京 → 東京那行有 "local_time: ... "
def test_unavailable_and_unsupported_lines_differ(): ...
def test_cap_six_and_more_line(): ...
def test_detail_shows_full_text_without_cap(): ...
def test_wind_only_when_warned_or_strong(): ...
def test_one_bad_place_does_not_fail_the_others(config_dir, capsys): ...  # ["台北", "zzzz"] → 結束碼 0，含 "[2] error: place_not_found"
def test_six_places_is_too_many(config_dir, capsys): ...   # 結束碼 1，"error: too_many_places"
def test_two_taiwan_places_fetch_ncdr_once(config_dir, capsys): ...  # http.calls 裡 NCDR feed 只出現 1 次
def test_second_run_within_ttl_makes_no_alert_requests(config_dir, capsys, tmp_path): ...
def test_json_has_places_alerts_and_cyclones(config_dir, capsys): ...
def test_country_code_flag_is_gone(config_dir, capsys): ...  # config weatherkit --country-code → bad_arguments
```

並更新既有的 `test_cli.py`、`test_render.py`，讓它們符合新格式（去掉 `source:`、humidity、feels、UV）。`test_both_sources_give_the_same_weather_lines` 保留，比較除了 `next_hour` 之外的天氣行。

- [ ] **Step 2**：執行 `uv run pytest -q tests/test_render.py tests/test_cli.py`，預期 FAIL。
- [ ] **Step 3**：實作。
- [ ] **Step 4**：執行 `uv run pytest -q -m 'not live'`，預期全部 PASS。用真實資料跑一次：`uv run src/weatherwise/scripts/weatherwise.py 板橋 礁溪` 和 `uv run src/weatherwise/scripts/weatherwise.py Berlin --global`，人工確認輸出符合 spec 第 9 節，並計算 token 量（用 `wc -c`，換算成約 1.5 字元 / token 的粗估，或用 tiktoken 以外的任何方法），單一地點應在 150 到 250 tokens 之間。
- [ ] **Step 5**：commit `feat: weatherwise multi-place output with local alerts and cyclones`

---

### Task 12: SKILL.md、文件、dist、最終驗證

**Files:**
- Modify: `src/weatherwise/SKILL.md`、`README.md`、`src/weatherwise/references/weatherkit-setup.md`（移除「WeatherKit 有警報」和 `--country-code` 的部分）
- Create: `src/weatherwise/references/sources.md`
- Regenerate: `dist/`

- [ ] **Step 1：SKILL.md**，依 spec 第 11 節：
  - `version: 2.0.0`；description 加上 typhoon track、warnings、特報、颱風路徑、警報；`tags` 加上 `alerts`、`GDACS`。
  - Commands 加上多地點的用法：`weatherwise.py 板橋 礁溪`，並註明最多 5 個；加上 `--detail`。
  - Reading the output：`none`／`unsupported`／`unavailable` 的差別；每一則都要提到；警報只代表現在；`next_hour` 有的時候要轉述；`cyclones:` 只有路徑資料時，要提醒使用者去看當地氣象單位；方位和距離要換成使用者聽得懂的說法，並附上 spec 裡的例子。
  - Trips：使用者說要去某個地方時，帶入目的地（需要時再加出發地）；不要加途經點；路況和封路請使用者看導航 app。
  - Settings：移除 `--country-code`。
- [ ] **Step 2**：`references/sources.md` 列出每個來源的名稱、網址、授權和出處標示（JMA：「出典：気象庁ホームページ」；MeteoAlarm：「MeteoAlarm.org」及 CC BY 4.0；GDACS：「GDACS, European Commission / United Nations」；NCDR、NWS、ECCC、HKO 也一併列出）。README 的 weatherwise 段落加上一行，連結到這份文件。
- [ ] **Step 3**：執行 `uv run tools/translate.py`，再執行 `uv run tools/translate.py --check`，預期輸出 `dist/ is up to date`。
- [ ] **Step 4：最終驗證**：執行 `uv run pytest -q`（包含 live 測試；本機有 WeatherKit 金鑰），預期全部 PASS。如果有 live 測試因為外部服務當下沒有資料而跳過或失敗，照實記錄。再執行 `uv run pytest -q tests/test_privacy.py tests/test_package.py`，預期 PASS。
- [ ] **Step 5**：commit `docs: weatherwise 2.0.0 — alerts, cyclones, trips in SKILL.md; rebuild dist`
