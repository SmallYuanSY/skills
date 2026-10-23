# weatherwise 警報改版：免帳號、多國、颱風：設計

日期：2026-10-22
狀態：草稿（待確認）
前一版：`2026-10-07-weatherwise-and-translator-design.md`

## 為什麼要做

WeatherKit 的警報只涵蓋北美和歐洲。2026-10-22 實測各城市的 availability，只有美、加、墨、英、法、德、義有 `weatherAlerts`；台灣、日本、韓國、香港、東南亞、印度、澳紐、巴西都沒有。所以颱風來的時候，台灣使用者看到的是 `alerts: unsupported`，這正是最需要警報的時候。實測當天第 29 號颱風（薔琵／CHAMPI）的颱風警報已經發布，新北市也有大豪雨特報，skill 卻一則都沒顯示。

這個 skill 要給各國的 agent 使用，不能要求使用者去申請帳號。所以警報要改用**各國官方、免帳號**的來源，再加上一個全球的熱帶氣旋來源補上缺口。

## 目標

- 沒有任何帳號的人，在台灣、日本、香港、美國、加拿大、歐洲（MeteoAlarm 成員國）都能看到當地的官方氣象警報。
- 全世界任何地方，只要有熱帶氣旋**可能靠近**，就會被提醒。
- 警報和預報來源各自獨立：預設用 Open-Meteo，有設定 WeatherKit 的人改用 WeatherKit 預報，但警報都走同一套來源。
- 使用者說「我今天要去礁溪」，agent 可以一次查多個地點。
- 輸出要精簡。agent（例如使用者的「飛予」）讀到的只有回答需要的資訊。
- 不會因為 agent 連續詢問就對外部服務大量發送請求。

## 不做的事

- **封路、路況、路線規劃**。導航 app（Google Maps、Apple Maps）已經會依實際路線即時提醒封路，而且做得比我們好。NCDR 裡公路局的「道路封閉」示警要排除，也不做沿途或路線的計算。以後不要再把封路加回來。
- **非氣象的災害示警**：土石流（農業部）、水庫放流（水利署）、地震等。只保留氣象單位發布的天氣類警報。*（排除土石流是設計者的判斷）*
- **需要帳號的來源**：韓國氣象廳（實測回傳 401）。
- **條款禁止使用的來源**：澳洲 BOM 的 API 回應明寫「You must not use, copy or share it」。
- **中國大陸**。
- WeatherKit 的警報不再使用（理由見「WeatherKit 的角色」）。

## 失敗條件（即使程式跑得動也算失敗）

- 使用者在台灣北部，結果列出其他縣市或其他國家的警報。
- 把 `unsupported` 說成「沒有警報」。
- 同一則警報的舊版本、已過期的版本，或同一則警報在多個地點，重複出現好幾次。
- 輸出塞進特報全文，或列出 30 幾則警報，讓 token 暴增。
- 對外部服務的請求量隨著 agent 提問的次數直線上升。

## 已實測的來源（2026-10-22）

| 範圍 | 來源 | 端點 | 授權 | 備註 |
|---|---|---|---|---|
| 台灣 | NCDR 災害示警 CAP | `https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx`（Atom，含 CAP 欄位） | Public Domain | **請求間隔至少 3 秒**，太快會回傳 `<Warning>限制存取間隔時間為3秒</Warning>`（HTTP 200）。全國只有一個 feed |
| 日本 | 氣象廳 bosai | `https://www.jma.go.jp/bosai/warning/data/warning/<都道府縣碼>.json` | 政府標準利用規約（需標示出處） | 依都道府縣分檔，細分到市町村的區域碼 |
| 香港 | 天文台開放資料 | `https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum&lang=tc` | 開放資料 | 全港共用一份；目前沒有警報時回傳 `{}` |
| 美國 | NWS | `https://api.weather.gov/alerts/active?point=<lat>,<lon>` | Public Domain | 依座標查，**必須帶 User-Agent** |
| 加拿大 | ECCC | `https://api.weather.gc.ca/collections/weather-alerts/items?f=json`（OGC API，可用 `bbox`） | Open Government Licence | 每則附多邊形範圍 |
| 歐洲約 38 國 | MeteoAlarm | `https://feeds.meteoalarm.org/api/v1/warnings/feeds-<country>`（JSON），或 Atom 版 | 等同 CC BY 4.0，轉發另有條款 | 每國一份，區域用 EMMA_ID 等地理代碼表示 |
| 全球熱帶氣旋 | GDACS | 列表：`https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=TC`；路徑與暴風範圍：`.../api/polygons/getgeometry?eventtype=TC&eventid=<id>&episodeid=<ep>` | 標示出處 | geometry 裡有目前位置（`Point_Centroid`）、預測路徑（`LineString`，屬性 `forecast=True`），以及綠／橙／紅三級暴風範圍多邊形 |

實測當天 GDACS 列出 `Tropical Cyclone CHAMPI-26`，等級 Red，eventid 1001338，episode 32。預測路徑為 20.9N 125.4E → 22.2N 124.3E → 23.9N 123.3E → 25.7N 122.8E。

**格式上的實測重點（會影響實作）**

- **NCDR 的 Atom entry 只有這些欄位**：`title`（類別，例如 `降雨`）、`author/name`（發布者）、`summary`（全文）、`updated`、`link`（指向個別 CAP 檔），以及 `cap:status`、`cap:msgType`、`cap:effective`、`cap:expires`。**沒有** area、geocode、severity、references，這些只在個別 CAP 檔裡。實測一次 feed 有 53 則。因為有 3 秒限制，**只用 Atom，不抓個別的 CAP 檔**。`cap:effective` 和 `cap:expires` 的格式是 `2026/10/23 下午 08:00:00`（台灣時間，中文的上午／下午）。
- **NCDR 颱風警報的 summary 裡有英文名稱和預測位置**，例如 `…29CHAMPI薔琵…2026-10-23T09:00:00+00:00 24.10,122.90…中度颱風 薔琵（國際命名 CHAMPI）22日19時的中心位置在北緯 21.…`。
- **GDACS 的預測路徑沒有個別時間**：`LineString` 只有 `forecast: True` 和整體的 `polygondate`，每個點都沒有時間。屬性裡有 `affectedcountries`（ISO2 清單）、`severitydata.severitytext`、`iscurrent`。
- **fixtures**：實作時用 `live` 請求抓真實回應，精簡後存成 fixtures。

## 設計

### 1. 國家判斷（也一併修正國碼 bug）

現在 `ww_sources.py` 的 `fetch_weatherkit` 一律送 `country_code`，預設是 `TW`。實測用 `TW` 查紐約和倫敦，availability 都不會回傳 `weatherAlerts`。這是 bug。

- 每個 `Place` 都要帶 `country_code`（ISO 3166-1 alpha-2）。
  - 用地名查詢時，向 Nominatim 要 `addressdetails=1`，國碼從 `address.country_code` 取得。
  - 輸入座標，或舊設定檔裡的預設地點沒有國碼時，用 Nominatim reverse 查一次。預設地點查到後寫回設定檔，以後就不用再查。
- WeatherKit 請求一律改用地點本身的國碼。設定裡的 `country_code` 和 `--country-code` 不再使用。舊設定檔裡有這個欄位也不會報錯，直接忽略。
- 依國碼選擇警報來源（見第 3 節）。

### 2. 地名搜尋修正

實測查「坪林」時，Nominatim 回傳**苗栗縣卓蘭鎮**的坪林，而不是新北市坪林區。現在的程式只取第一筆結果（`limit=1`）。

- 要求：在台灣搜尋時，若有行政區（鄉鎮市區、縣市）和查詢名稱相符，要優先採用行政區，而不是同名的村里或地標。
- 測試至少涵蓋：「坪林」→ 新北市坪林區、「礁溪」→ 宜蘭縣礁溪鄉、「板橋」→ 新北市板橋區。
- 具體做法交給實作者決定（例如 `limit` 調大後依 `addresstype` 或 `place_rank` 選擇）。

### 3. 警報來源的分派

```
國碼 TW → NCDR（只保留中央氣象署的天氣類示警）
     JP → JMA
     HK → HKO
     US → NWS
     CA → ECCC
     MeteoAlarm 成員國 → MeteoAlarm
     其他 → 沒有官方警報來源
所有地點 → 另外查 GDACS 熱帶氣旋
```

每個來源各寫一個 provider，輸出相同的結構：

```
Alert(kind, severity, title, areas, summary, onset, expires, source, key)
```

- `kind`：類別，例如 `typhoon`、`rain`、`wind`、`heat`、`cold`、`fog`、`marine`，名稱由實作者決定，但各來源要對到同一組。
- `severity`：`extreme` / `severe` / `moderate` / `minor`，依 CAP 的 severity 或燈號顏色對應。
- `key`：判斷「是否為同一則警報」用的鍵，用於去重（見第 5 節）。

**只看涵蓋地點的警報**（各來源的判斷方式）：

| 來源 | 怎麼判斷涵蓋 |
|---|---|
| NCDR | 依縣市：summary 裡出現該縣市名稱就算涵蓋（臺／台兩種寫法都要比對）。地點的縣市從 Nominatim 的 address 取得。颱風警報是全國性的，一律涵蓋 |
| JMA | 用 Nominatim 取得的市町村名稱，比對氣象廳 `area.json` 裡的區域名稱，找出區域碼，只取這個區域的警報與注意報。比對不到就輸出 `unsupported`。**不使用邊界圖資**（檔案有幾十 MB）。*（設計者的判斷）* |
| HKO | 全港共用 |
| NWS | API 本身就是依座標查 |
| ECCC | 用座標判斷是否落在多邊形內 |
| MeteoAlarm | 有多邊形就判斷座標是否在內；只有 EMMA_ID 的話，用 MeteoAlarm 公開的區域對照表 |

找不到地點屬於哪個區域時，該地點的警報就輸出 `unsupported`，**不可以把全國的警報都列出來**。

**NCDR 只保留**：發布者是「中央氣象署」，且類別屬於颱風、降雨、強風、高溫、低溫、濃霧、巨浪。實測 feed 裡出現的類別有：`降雨`、`颱風`、`強風`、`高溫`、`巨浪`、`道路封閉`、`土石流及大規模崩塌`。

**嚴重程度不篩**：特報、注意報、黃色燈號都要列，依嚴重程度排序。NCDR 的 Atom 沒有 severity 欄位，從文字推斷：`紅色燈號`、`超大豪雨`、颱風警報 → `severe` 或以上，`橙色燈號`、`大豪雨`、`豪雨` → `severe` 或 `moderate`，`黃色燈號`、`大雨` → `minor` 或 `moderate`。對應表交給實作者，但同一則警報涵蓋多種程度時，取最高的。

### 4. 熱帶氣旋（GDACS）

使用者說「知道可能靠近就該提醒」，所以門檻設得寬：

- 先抓列表，排除已經結束的事件（`todate` 太舊）。只有目前位置在地點 3500 km 以內的事件，才去抓 geometry（五天路徑可以走超過 2000 km；結果不可以取決於同時查詢的其他地點）。
- 符合任一條件就提醒：
  - 地點落在任何一個預測暴風範圍多邊形內；或
  - 目前位置或預測路徑上任一點，距離地點 800 km 以內。
  - geometry 抓不到（逾時、錯誤、被拒）時沒有路徑可判斷：目前位置在 3500 km 以內就列出，寫 `forecast track unavailable`，不可以默默漏掉。*（R24）*
- 輸出一行：名稱、GDACS 等級、目前距離和方位、預測路徑最接近的距離。**GDACS 沒有預測時間**，只有當地官方資料提供時間時（例如 NCDR 颱風摘要裡的預測位置和時刻），才寫出最接近的時間。
- **同一顆颱風只列一次**，合併規則適用於所有來源（NCDR、JMA、HKO、NWS、ECCC、MeteoAlarm），在共用的步驟處理，不寫在個別 provider 裡：
  - 如果當地警報的 title 或 summary 裡出現 GDACS 名稱去掉年份後的部分（例如 `CHAMPI-26` → `CHAMPI`，不分大小寫），就視為同一顆。實測 NCDR 的摘要裡有「國際命名 CHAMPI」。
  - 合併後以當地警報為主（名稱用「薔琵」這種當地名稱），GDACS 只補上距離資訊。
  - 比對不到時兩者都列。寧可重複，也不要漏掉。*（設計者的判斷）*
- 只有 GDACS、沒有當地官方警報時，要標示「這是熱帶氣旋路徑資訊，不是當地官方警報」，讓 agent 知道要提醒使用者去看當地氣象單位。
- 800 km 和 3500 km 寫成常數，方便日後調整。*（數值是設計者的判斷）*

### 5. 過濾與去重

- 排除已過期（`expires` 早於現在）的警報。
- NCDR 的 feed 會保留同一則特報的歷次版本（實測強風約 10 則、颱風每小時一則）。**同一個 `key` 只保留最新且仍有效的一則**。NCDR 的 `key` 是「發布者 + title（類別）」，以 `updated` 判斷哪則最新。其他來源有事件代碼或 references 時，就用那個當 `key`。
- 同一則警報涵蓋多個查詢地點時，只列一次，並標註適用哪些地點（`[1][2]`）。
- 每個地點最多列 6 則，超過就顯示 `+N more`。
- summary 精簡成「什麼、哪裡、到什麼時候」，大約 60 個字以內。特報原文不放進輸出。

### 6. 預報來源與 WeatherKit 的角色

| | Open-Meteo（預設） | WeatherKit（選用） |
|---|---|---|
| 帳號 | 不用 | 付費的 Apple Developer |
| 現在／每日預報 | 有 | 有，天況描述比較細 |
| 未來一小時逐分鐘降雨 | 沒有 | 部分國家有（實測美、加、英、日、澳有；台灣沒有） |
| 警報 | 一律走第 3 節的來源 | 同左，不使用 WeatherKit 的 `weatherAlerts` |

- WeatherKit 不再呼叫 availability 端點來判斷警報，只用它判斷有沒有 `forecastNextHour`。*（實作者也可以選擇直接請求 `forecastNextHour`，沒有資料時再當作不支援，只要省下一次請求就好）*
- **未來一小時降雨**：有資料時，輸出一行摘要（例如 `next_hour: rain starting ~21:05, heavy by 21:20`）。沒有資料時，輸出 `next_hour: unavailable here`；用 Open-Meteo 時則完全不輸出這行。不列出逐分鐘的數值。
- WeatherKit 認證失敗（401／403）時，自動改用 Open-Meteo 的行為維持不變。

使用者的態度：喜歡 WeatherKit，但同意它不應該是必要的。

### 7. 多個地點

```
weatherwise [地點 ...] [--global] [--days N] [--lang TAG] [--json]
```

- 位置參數改為 0 到 5 個。沒給就用預設地點。超過 5 個時，回傳 `too_many_places`（見第 10 節）。
- **某個地點失敗時，其他地點照常輸出**：查不到的地點寫成 `[2] error: place_not_found (<名稱>)`，加上 `action`。只有全部地點都失敗時，才用現有的單一錯誤格式並以非 0 結束。單一地點時的行為不變。*（設計者的判斷）*
- 用途是「我今天要去哪裡」：agent 會帶入出發地與目的地，或是只帶目的地。SKILL.md 要教 agent：**不要**自己補上沿途經過的地點（封路不做，也就不需要）。
- 單一地點時的輸出應和現在的格式相近，讓舊的使用方式不受影響。

### 8. 流量控制

- **同一個來源，一次執行只抓一次**：NCDR、MeteoAlarm（每國）、HKO、GDACS 列表都是整國或全球一份，抓一次後在本機篩選。JMA 依都道府縣，每縣只抓一次。ECCC 用涵蓋所有地點的 bbox 一次查完。NWS 依座標查，每個地點一次。
- **預報**：Open-Meteo 用一次請求帶入多組座標（API 支援以逗號分隔的經緯度）。WeatherKit 每個地點一次。
- **GDACS geometry**：只對 3500 km 內的事件才抓。
- **本機快取**：`~/.cache/weatherwise/`（遵循 `XDG_CACHE_HOME`），依 URL 存放。TTL：警報 5 分鐘（MeteoAlarm 整國 feed 大而慢，15 分鐘）、GDACS 15 分鐘、預報 15 分鐘、Nominatim 查詢結果 30 天。快取壞掉或無法寫入時，直接忽略，不可以因此報錯。來源拒絕的回應（例如 NCDR 限流訊息、無法解析的內容）不寫入快取；若有一小時內的上一份正常資料就改用它，「as of」顯示它的時間。*（TTL 數值是設計者的判斷）*
- NCDR 的 3 秒限制：同一次執行只會請求一次。被擋時（收到那段 `<Warning>` XML），視為暫時失敗，不重試，該地點的警報輸出 `unavailable`（見下）。
- 所有請求都帶現有的 `User-Agent`（NWS、Nominatim 都要求）。

### 9. 輸出格式

輸出仍是給模型讀的 `key: value`。目標 token 量：單一地點 150 到 250，兩個地點 200 到 300（2026-10-22 實際資料估算）。

單一地點：

```
local_time: 2026-10-22T20:32 Thu
location: 板橋區, 新北市, 臺灣 (25.011, 121.459)
now: Rain 23°C, wind 16 km/h
next_hour: unavailable here
daily:
  2026-10-22 Thu: Rain, 22–24°C, rain 99%
  2026-10-23 Fri: Heavy Rain, 24–27°C, rain 100%
  2026-10-24 Sat: Heavy Rain, 24–26°C, rain 100%
alerts (as of 20:17, current only — not a forecast for later days):
  - [severe] 颱風警報 中度颱風 薔琵: now ~470 km SE, closest ~150 km E on 10-23 17:00
  - [severe] 大豪雨 新北市 山區: until 10-23 20:00
  - [moderate] 強風 橙色 新北市: 陣風11級以上, until 10-23 23:00
```

多個地點（「我今天要去礁溪」）：

```
local_time: 2026-10-22T20:32 Thu
[1] 板橋區, 新北市: Rain 23°C; today 22–24°C, rain 99%
[2] 礁溪鄉, 宜蘭縣: Rain 24°C; today 22–24°C, rain 99%
alerts (as of 20:17, current only — not a forecast for later days):
  - [severe] 颱風警報 中度颱風 薔琵 [1][2]: now ~470 km SE of [1], closest ~120 km E of [2] on 10-23 17:00
  - [severe] 超大豪雨 [2] / 大豪雨 [1]: 山區, until 10-23 20:00
  - [moderate] 強風 橙色 [1][2]: 陣風11級以上, until 10-23 23:00
```

規則：

- 天氣只列天況、氣溫、降雨機率。濕度、體感溫度、UV 不列。風速只有在強風警報期間，或風速明顯偏強時才列（門檻交給實作者）。*（這一條會改變現有的輸出，是使用者「要過濾」的要求）*
- 多個地點時，每日預報只列到 `--days` 指定的天數；沒指定時，多地點預設只列今天。*（設計者的判斷）*
- `source:` 這行只在 `--json` 或有 `notice` 時才需要。是否保留交給實作者，但 SKILL.md 本來就要求不提資料來源。
- 警報狀態都要明講：
  - `alerts: none`：有來源，而且目前沒有警報
  - `alerts: unsupported`：該地沒有官方警報來源。如果有熱帶氣旋，仍然列出
  - `alerts: unavailable (<原因>)`：有來源，但這次抓不到（網路錯誤、被限速）。**不可以說成沒有警報**
- 警報一定附上「抓取的時間」，並註明只代表目前的狀態。這樣 agent 回答「明天去」時，才不會把現在的警報說成明天的。
- `--detail`：可以看單則警報的全文，或沒被列出的 `+N more`。格式交給實作者，但預設輸出不放全文。
- `--json` 要包含結構化的 alerts 和 cyclone 資料。

### 10. 錯誤

沿用現有的 `error:` + `action:` 格式。新增：

| 代碼 | 意思 | action |
|---|---|---|
| `too_many_places` | 超過 5 個地點 | 縮減成最重要的幾個地點，例如只留目的地 |

**某個警報來源失敗，不應該讓整個指令失敗**：天氣照樣輸出，只把該地點的警報標成 `unavailable`。預報來源失敗時，沿用現有的錯誤處理。

### 11. SKILL.md 要更新的地方

- 讀警報：`none` / `unsupported` / `unavailable` 三種狀態的差別；每一則都要提到；警報只代表現在，不代表之後幾天。
- 颱風那一行要轉述距離和最接近的時間。只有 GDACS 資料時，提醒使用者去看當地氣象單位。
- **方位和距離要換成使用者聽得懂的說法**：不要直接說「東南方 470 公里」，要說「颱風在台灣東南方海面，明天傍晚最接近，大約在宜蘭外海 120 公里」。輸出裡的 `SE`、`km` 是給 agent 判斷用的資料，不是要原封不動唸給使用者聽。（使用者的例子：導航說「朝西南行駛」，人根本不知道西南是哪邊。）
- 多個地點：使用者說要去某地時，帶入目的地（需要時加上出發地）。不要補上沿途經過的地點。路況和封路請使用者看導航 app。
- `config weatherkit` 移除 `--country-code` 的說明。
- 移除「WeatherKit 才有警報」的相關說明。
- description 加上「颱風路徑」「特報」「警報」等觸發詞。
- 資料來源的出處標示（JMA、MeteoAlarm、GDACS 要求標示）寫在 README 或 references，不放進回答。*（設計者的判斷：SKILL.md 本來就要求不提資料來源，標示出處的義務由 repo 文件處理）*

### 12. 測試

- 沿用現有的 pytest 結構（`tests/`，`http` 以參數注入，`live` 標記用於真實連線）。
- 每個 provider 都要有離線測試，fixture 用 2026-10-22 實際抓到的回應來精簡，**fixture 裡不可以有私人地點**（`tests/test_privacy.py` 會檢查）。
- 必測情境：NCDR 舊版本去重、已過期的排除、只保留氣象署的天氣類示警、縣市篩選（臺／台）、GDACS 距離門檻、多地點共用警報合併、`unavailable` 和 `unsupported` 的區別、快取命中時不發出請求、單次執行同一來源只請求一次、坪林的地名修正。
- 每個來源各一個 `live` 測試，確認端點和格式沒變。

## 留給實作者決定的

- 模組怎麼拆（建議一個來源一個檔案，例如 `ww_alerts_ncdr.py`，但不強制）。
- `Alert.kind` 的確切名稱、severity 的對應表。
- JMA 區域定義檔、MeteoAlarm 區域對照表要在執行時下載（加快取），還是打包進 repo。要考慮檔案大小。
- MeteoAlarm 實測：各國 feed 的 area 只有名稱和 geocode，沒有 polygon，且沒有公開的 EMMA_ID 對照表（404）。因此改用正規化後的區域名稱（含 county／Kreis）比對地點的 region、locality、district；feed 只列出生效中的警報，所以沒有警報的地點會顯示為不支援（unsupported）。
- 點是否在多邊形內、兩點距離的算法（純 Python 就好，不要加相依套件）。
- 風速門檻、`--detail` 的格式。
- `dist/` 要用 `tools/translate.py` 重新產生，並通過 `tests/test_package.py`。

## 版本

改了輸出格式和 CLI（多地點、移除 `--country-code`），版本升為 `2.0.0`。
