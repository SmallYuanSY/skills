# weatherwise 與 skill 轉譯器：設計

日期：2026-10-07
狀態：已確認

## 目標

建立公開的 skills repo（`SmallYuanSY/skills`，MIT）。第一個 skill 是 `weatherwise`，由私人的 `macos-weather` 改寫而成。同時做出轉譯器第一版：只維護一份 skill 原始檔，產生 Hermes 和 Claude Code 可以直接安裝的版本。

**成功標準**

- 沒有 Apple 開發者帳號的人，裝好 `uv`、複製資料夾，就能查天氣，不用註冊任何東西。
- 有 Apple 開發者帳號的人，照教學設定好，就會自動改用 WeatherKit。
- 使用者只要跟 agent 用講的（例如「預設地點改成台中」），agent 就能透過 `config` 指令完成設定，不用手改任何檔案。
- 模型讀了輸出不會答錯：日期對得上，不會把「不支援警報」說成「沒有警報」。
- 同一份原始檔產生的 Hermes 版和 Claude Code 版，執行指令的路徑都正確。
- repo 裡沒有任何私人資訊，例如住址、地點、金鑰、私人代號。

**不做的事**

- 不支援 Codex 或其他 agent。之後只要在轉譯器加一種輸出即可。
- 免費模式不提供天氣警報。
- 不做任何防複製機制：不混淆程式碼、不在回答中提及作者、不回傳任何資料。

## Repo 結構

```
skills/
├── LICENSE                     MIT，Copyright (c) 2026 SmallYuan
├── README.md                   英文：有哪些 skill、怎麼安裝到 Hermes 或 Claude Code、怎麼設定
├── src/                        ← 唯一要手動編輯的地方
│   └── weatherwise/
│       ├── SKILL.md            路徑寫成佔位符 {{SKILL_DIR}}
│       ├── scripts/weatherwise.py
│       └── references/weatherkit-setup.md
├── dist/                       ← 轉譯器產生，commit 進 repo，讓人直接複製
│   ├── hermes/weatherwise/...
│   └── claude/weatherwise/...
├── tools/translate.py          轉譯器
├── tests/
└── docs/specs/
```

`dist/` 也 commit 進 repo，因為使用者是直接複製資料夾來安裝，不會自己跑 build。CI 會檢查 `dist/` 跟 `src/` 是否同步。

## weatherwise

### 輸出是給模型讀的

這個指令的讀者是 agent，不是人，人看到的是 agent 轉述後的回答。所以輸出的目標是讓模型讀得準、不會誤解、省 token，不求好看：

- 欄位名稱、天氣狀況、錯誤代碼都用英文，結構固定為 `key: value`。不用 emoji 當標記。
- 一定附上地點當地的現在時間（模型通常不知道今天幾號），日期一律用 ISO 格式加星期。
- 每種狀態都明講，不讓模型自己推論，例如警報分成 `none`、`unsupported`，或列出內容。
- 錯誤一律是 `error: <代碼>` 加 `action: <下一步該做什麼>`。

### 資料來源

| 模式 | 什麼時候用 | 警報 |
|---|---|---|
| Open-Meteo（預設） | 設定檔沒有 `weatherkit` 區塊，或根本沒有設定檔 | 一律 `unsupported` |
| WeatherKit（選配） | 設定檔有完整的 `weatherkit` 區塊 | 先查 availability 端點：Apple 在該地有警報資料才是 `none` 或列出內容，否則 `unsupported`。**台灣、日本都沒有**（2026-10-07 實測），美國有 |

兩個來源各寫一個函式，回傳同一種結構（目前天氣、每日預報、警報狀態），再由同一段程式輸出，所以兩種模式的輸出格式完全相同。天氣狀況統一成英文名稱：WeatherKit 的 `conditionCode` 轉成可讀的英文（例如 `PartlyCloudy` → `Partly Cloudy`），Open-Meteo 的 WMO 代碼對照到同一組英文名稱。

**WeatherKit 認證失敗時自動改用 Open-Meteo**：只有 HTTP 401／403 會這樣做，輸出最前面會多一行 `notice`（見下方）。設定檔寫錯（欄位缺漏、`.p8` 不見）不在此列，一律直接報錯。

### 指令與輸出

```
weatherwise [地點] [--global] [--days N] [--json] [--version]
```

地點可以是台灣地名、`--global` 加上國外地名，或 `lat,lon`。地名轉座標用 Nominatim，台灣優先，跟現在的做法一樣。

```
source: open-meteo
location: 台北市, 臺灣 (25.033, 121.565) timezone=Asia/Taipei
local_time: 2026-10-07T20:41 Wed
current: Partly Cloudy, 27.0°C, feels 29.1°C, humidity 70%, wind 12 km/h, UV 6
daily:
  2026-10-08 Thu: Rain, 23–27°C, precipitation chance 80%
alerts: unsupported (this source has no official alert data here; do not tell the user there are none)
```

WeatherKit 模式的警報：

```
alerts: none
```
或
```
alerts:
  - Heavy Rain Advisory (Central Weather Administration)
```

認證失敗自動切換時，最前面多一行：

```
notice: weatherkit_auth_failed (HTTP 401), fell back to open-meteo; tell the user their WeatherKit key may be revoked or their Apple Developer membership may have expired
```

- `--days`：預設 3，超出範圍時自動限制在 1 到 10 之間。
- `--json`：輸出 `{"source": ..., "notice": ...（有才出現）, "data": <資料來源原始 JSON>}`。
- `--version`：印出 `weatherwise 1.0.0 · by SmallYuan · https://github.com/SmallYuanSY/skills`。

### 錯誤

格式固定為兩行，結束碼不為 0：

```
error: no_default_location
action: ask the user where they are, then run: config set-default <place>
```

| 代碼 | 意思 | action |
|---|---|---|
| `no_default_location` | 沒給地點，也沒設定預設地點 | 問使用者在哪裡，再執行 `config set-default` |
| `place_not_found` | 地名查不到 | 換個寫法、加 `--global`，或用 `lat,lon` |
| `network_error` | 連不上 | 照實告訴使用者查不到 |
| `weatherkit_config_incomplete` | 設定缺欄位（訊息會列出缺哪些） | 執行 `config weatherkit` 補齊，或用 `--remove` 改回免費模式 |
| `weatherkit_key_missing` | `.p8` 檔不見了 | 同上 |
| `unsupported_lang` | `lang` 不是 BCP 47 格式 | 改用 `zh-TW`、`en`、`ja` 這類格式 |
| `config_invalid` | 設定檔不是合法的 JSON | 請使用者檢查或刪除設定檔，再用 `config` 指令重設 |
| `service_error` | 天氣服務回傳 401／403 以外的 HTTP 錯誤 | 告訴使用者稍後再試 |
| `weatherkit_auth_failed` | 只出現在 `config weatherkit`：測試請求被拒（401／403） | 告訴使用者 ID 或金鑰有誤，設定沒有寫入 |
| `invalid_key_file` | `.p8` 檔不存在或不是有效的金鑰 | 跟使用者要正確的 `AuthKey_<KeyID>.p8` 路徑 |
| `bad_arguments` | 指令參數錯誤 | 對照 SKILL.md 修正指令 |

### 語言（i18n）

輸出本身是英文，模型會自己用使用者的語言回答，所以程式不做翻譯表。`lang` 只控制外部 API 回來的文字：

- Nominatim 的 `accept-language`，也就是地名用哪種語言顯示（「台北市」或「Taipei」）。
- WeatherKit 網址裡的語言代碼，也就是警報內容的語言。

設定方式：CLI `--lang`，然後設定檔的 `lang`，最後預設 `zh-TW`。值必須是 BCP 47 格式（例如 `zh-TW`、`en`、`ja`），格式不對就回 `unsupported_lang`。

日期和星期幾自己產生，不使用系統 locale，輸出才不會因為每台機器的語言設定不同而改變。

之後若要做多語版的 SKILL.md 或教學，由轉譯器處理（例如 `SKILL.en.md`），這部分第一版不做。

### 設定檔

位置：`~/.config/weatherwise/config.json`，整個檔案都是選配。正常情況下不手改，用下一節的 `config` 指令寫入。

```json
{
  "lang": "zh-TW",
  "default": { "name": "台北市", "lat": 25.0330, "lon": 121.5654, "timezone": "Asia/Taipei" },
  "weatherkit": {
    "team_id": "...", "key_id": "...", "service_id": "...",
    "key_path": "~/.config/weatherwise/AuthKey_XXXX.p8",
    "country_code": "TW"
  }
}
```

### 設定指令

讓 agent 幫使用者設定時，不直接改 JSON（容易改壞），一律透過指令。指令會先驗證，通過才寫入：

```
weatherwise config show
weatherwise config set-default <地點> [--global]
weatherwise config set-lang <lang>
weatherwise config weatherkit --team-id … --service-id … --key-file <路徑> [--key-id …] [--country-code TW]
weatherwise config weatherkit --remove
```

- **`show`**：印出目前的設定，以及現在用的是哪個資料來源。ID 只顯示前後兩碼（例如 `AB…YZ`），`.p8` 只顯示路徑。
- **`set-default`**：用查天氣時相同的邏輯查地名，把找到的名稱、座標、時區印出來給 agent 跟使用者確認，然後寫入。
- **`weatherkit`**：
  - 把 `.p8` **複製**到 `~/.config/weatherwise/`，權限設為 `600`。原始檔被刪掉也不影響。
  - 沒給 `--key-id` 時，從 Apple 固定的檔名 `AuthKey_<KeyID>.p8` 解析出來。
  - 寫入前實際呼叫一次 API。失敗就不寫入，並回報是 401 還是 403。
- **`--remove`**：刪掉設定裡的 `weatherkit` 區塊和複製進來的 `.p8`，改回免費模式。
- 設定檔的寫入要一次完成（先寫暫存檔再改名），中途失敗也不會留下壞掉的檔案。

**關於三個 ID 的安全性**：Team ID、Key ID、Service ID 是識別碼，不是密鑰。它們本來就以明碼出現在每個 WeatherKit token 裡，沒有 `.p8` 什麼都做不了。所以讓 agent 經手這三個值是可以接受的。但它們會留在對話紀錄裡，因此 SKILL.md 也提供另一種做法：使用者可以自己在終端機執行指令，ID 就不會進入對話。

### SKILL.md

- 內文用英文寫，因為讀者是模型；description 中英文都有，中文的問法才能觸發。
- frontmatter：`name: weatherwise`、`author: SmallYuan`、`license: MIT`、repo 網址，以及中英文都有的 description。
- 指令寫成 `uv run {{SKILL_DIR}}/scripts/weatherwise.py`。
- 怎麼讀輸出、怎麼回答：
  1. 依照 `local_time` 判斷「今天」「明天」對應到哪一天。
  2. `alerts: unsupported` 時，不可以說「沒有警報」。使用者問到颱風或豪雨，或看起來是颱風季時，要提醒他去看當地氣象單位。
  3. 有 `notice` 時，一定要轉告使用者。
  4. 出現 `error` 時，照 `action` 做。
  5. 回答時用使用者的語言，不用提資料來源。
- 設定（新的一節）：
  - 使用者想換預設地點或語言 → 執行對應的 `config` 指令。`set-default` 找到的地點要先跟使用者確認。
  - 使用者想用 WeatherKit → 照 `references/weatherkit-setup.md` 一步一步帶。Apple 網站上的操作只能由使用者自己做；agent 負責告訴他每個值去哪裡找，最後執行 `config weatherkit`。
  - 如果使用者不想把 ID 貼進對話，就把完整指令給他自己執行（Claude Code 可以用 `!` 開頭）。
  - **絕對不讀出、不貼出 `.p8` 的內容**，只處理它的路徑。
- 不提作者，也不叫 agent 在回答裡做任何宣傳。

### 署名（全部公開）

LICENSE、SKILL.md 的 frontmatter、`weatherwise.py` 開頭的版權註解、`--version`，以及 Nominatim 規定要有的 User-Agent：`weatherwise/1.0 (+https://github.com/SmallYuanSY/skills)`。

### WeatherKit 教學（`references/weatherkit-setup.md`）

1. 加入 Apple Developer Program（每年 US$99）。
2. 在 Certificates, Identifiers & Profiles 建立 WeatherKit 用的 Service ID，以及啟用 WeatherKit 的金鑰。
3. 下載 `.p8` 檔。只能下載一次，下載後放在安全的地方。
4. Team ID、Service ID 各在網站的哪個位置（Key ID 在檔名裡，不用另外找）。
5. 執行 `weatherwise config weatherkit --team-id … --service-id … --key-file <下載的 .p8>`。程式會複製金鑰並實際測試一次。不想讓 ID 進入對話的人，可以自己在終端機執行。
6. 確認：`weatherwise config show` 顯示 `source: weatherkit`。
7. 常見問題：
   - 401：金鑰被撤銷、ID 填錯，或開發者會員到期。
   - 403：Service ID 沒有啟用 WeatherKit。
   - `.p8` 本身不會過期，但會員到期後 API 就不能用，續約後會自動恢復。這段期間 weatherwise 會自動改用免費資料，並在輸出裡提醒。
   - 不想用了：`weatherwise config weatherkit --remove`。

SKILL.md 只寫一句「想用 WeatherKit 請看 references/weatherkit-setup.md」，教學本身不會載入 agent 的 context。

## 轉譯器（`tools/translate.py`）

只用 Python 標準庫，用 `uv run` 執行。

```
uv run tools/translate.py           # 依 src/ 重新產生 dist/
uv run tools/translate.py --check   # dist/ 跟 src/ 不同步就回傳失敗（CI 用）
```

每個 target 的規則：

| target | `{{SKILL_DIR}}` 換成 | 輸出位置 |
|---|---|---|
| hermes | `${HERMES_SKILL_DIR}` | `dist/hermes/<skill>/` |
| claude | `${CLAUDE_SKILL_DIR}` | `dist/claude/<skill>/` |

- 只替換 `.md` 檔裡的佔位符，其他檔案原樣複製。
- 先清空 `dist/<target>/` 再重新產生，這樣 `src/` 刪掉的檔案在 dist 裡也會消失。
- 產生之後，如果還有沒被替換的 `{{...}}` 佔位符，就報錯。
- target 用一個小表格定義，之後要加 Codex，只要多一列。
- frontmatter 兩邊用同一份：Hermes 專用的欄位（`metadata.hermes`、`prerequisites`），Claude Code 會忽略。

## 隱私檢查

跟首頁一樣：deny-list 放在本機 `tests/private-terms.local.txt`，加進 gitignore；repo 裡只放一份 `private-terms.example.txt` 範例。測試會掃描 `src/` 和 `dist/` 的所有文字檔，有符合就失敗。沒有 deny-list 的環境（例如 CI）就跳過這項測試，其他測試照跑。

已知要清掉的：現有 skill 裡的家庭地點和稱呼，以及 User-Agent 裡的私人名稱。

## 測試

- **真的 API 是主要的驗證方式**（`tests/test_live.py`）：Open-Meteo、Nominatim 直接打真的請求；這台電腦有 WeatherKit 金鑰時也打真的 WeatherKit。檢查回傳格式、時區、日期，以及假資料用到的欄位真的 API 都有。CI 沒有金鑰，所以會跳過 WeatherKit 的部分。
- 假資料只用在真的 API 無法照需求產生的情況：401／403、500、null、警報。
- 401 自動切換和完整的設定流程，最後由使用者實際撤銷金鑰、建立新金鑰來測一次（見發布順序）。
- 各模組的單元測試涵蓋以下項目：
  - 兩種來源轉成相同格式的輸出，`local_time` 和日期依地點的時區計算。
  - 警報的三種狀態：`unsupported`、`none`、列出內容。
  - 401／403 時自動改用 Open-Meteo，並輸出 `notice`；其他 HTTP 錯誤不切換。
  - 每一種 `error` 代碼都有對應的 `action`，結束碼不為 0。
  - `--lang` 和設定檔的 `lang` 優先順序正確，格式錯誤時回 `unsupported_lang`。
  - `--version`、User-Agent。
- `tests/test_config.py`：每個測試都用暫存的設定目錄。
  - `set-default` 寫入的名稱、座標和時區正確。
  - `weatherkit` 會複製 `.p8` 並設權限為 `600`；能從檔名解析出 Key ID；API 測試失敗時不寫入；`--remove` 會刪掉區塊和複製的檔案。
  - `show` 會遮蔽 ID，而且永遠不印出 `.p8` 的內容。
  - 寫入中途失敗時，原本的設定檔保持不變。
- `tests/test_translate.py`：佔位符替換、只替換 `.md`、清空舊檔、殘留佔位符時報錯、`--check` 偵測不同步。
- `tests/test_privacy.py`：上面說的 deny-list 掃描。
- 一行指令跑全部：`uv run pytest`。
- GitHub Actions：跑測試（包含真實 API）加上 `translate.py --check`。

## 發布順序

1. 本機完成，測試全過。
2. 手動實測：免費模式查一次台北和東京；用你現有的 WeatherKit 金鑰透過 `config weatherkit` 設定後再查一次。
3. **讓飛予實際使用**：把 `dist/hermes/weatherwise` 裝進這台電腦的 `~/.hermes/skills/`。測試期間暫停 `macos-weather`，避免兩個 skill 搶著觸發。用真實的對話測試，例如「明天要帶傘嗎」「預設地點改成台中」「東京這週天氣」「颱風要來了嗎」，確認她讀輸出不會答錯。發現問題就回頭改輸出格式或 SKILL.md。
4. **撤銷金鑰實測**：使用者在 Apple 網站撤銷目前的金鑰，確認真的 401 會自動切換並告知使用者；再讓飛予帶使用者建立新金鑰、走完整個設定流程。撤銷會讓舊的 `macos-weather` 一起失效，要一併處理。
5. 建立公開的 GitHub repo 並 push（推之前會先問你）。
6. smallyuan.dev：卡片標籤從 `macos-weather` 改成 `weatherwise`，並連到 repo。這是首頁 repo 的另一個小改動。

## 待決定

- 測試結束後，`macos-weather` 要不要直接換成 `weatherwise`。不影響這次的實作，可以發布後再決定。
