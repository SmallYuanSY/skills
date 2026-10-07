# weatherwise 與 skill 轉譯器：設計

日期：2026-10-07
狀態：草稿，待確認

## 目標

建立公開的 skills repo（`SmallYuanSY/skills`，MIT）。第一個 skill 是 `weatherwise`，由私人的 `macos-weather` 改寫而成。同時做出轉譯器第一版：只維護一份 skill 原始檔，產生 Hermes 和 Claude Code 可以直接安裝的版本。

**成功標準**

- 沒有 Apple 開發者帳號的人，裝好 `uv`、複製資料夾，就能查天氣，不用註冊任何東西。
- 有 Apple 開發者帳號的人，照教學填好設定檔，就會自動改用 WeatherKit。
- 同一份原始檔產生的 Hermes 版和 Claude Code 版，執行指令的路徑都正確。
- repo 裡沒有任何私人資訊，例如住址、地點、金鑰、私人代號。

**不做的事**

- 不支援 Codex 或其他 agent。之後只要在轉譯器加一種輸出即可。
- 第一版不做繁體中文以外的輸出語言，但架構預留 i18n。
- 免費模式不提供天氣警報。
- 不做任何防複製機制：不混淆程式碼、不在回答中提及作者、不回傳任何資料。

## Repo 結構

```
skills/
├── LICENSE                     MIT，Copyright (c) 2026 SmallYuan
├── README.md                   英文：有哪些 skill、怎麼安裝到 Hermes 或 Claude Code
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

### 資料來源

| 模式 | 什麼時候用 | 警報 |
|---|---|---|
| Open-Meteo（預設） | 設定檔沒有 `weatherkit` 區塊，或根本沒有設定檔 | 沒有 |
| WeatherKit（選配） | 設定檔有完整的 `weatherkit` 區塊 | 有 |

兩種模式的**一般輸出格式完全相同**，SKILL.md 的回答規則不必分開寫。程式碼裡兩個來源各寫一個函式，各自回傳同一種結構（目前天氣、每日預報、警報清單或「不支援」），之後由同一段程式印出結果。

天氣狀況要翻成中文：WeatherKit 用現有的 `conditionCode` 對照表；Open-Meteo 用 WMO 天氣代碼，另外寫一張對照表，翻出來的中文詞跟 WeatherKit 那張一致（例如「晴」「多雲」「雨」）。

### 設定檔

位置：`~/.config/weatherwise/config.json`。整個檔案都是選配。

```json
{
  "default": { "name": "台北", "lat": 25.0330, "lon": 121.5654, "timezone": "Asia/Taipei" },
  "weatherkit": {
    "team_id": "...", "key_id": "...", "service_id": "...",
    "key_path": "~/.config/weatherwise/AuthKey_XXXX.p8",
    "country_code": "TW"
  }
}
```

- 沒有 `default`、也沒給地點時，程式會印出 `沒有預設地點`。SKILL.md 規定 agent 這時要問使用者在哪裡，不能自己猜。
- `weatherkit` 區塊只填一部分時，直接報錯，列出缺了哪幾個欄位。不會默默退回 Open-Meteo，以免使用者以為已經在用 WeatherKit。

### 指令與輸出

```
weatherwise [地點] [--global] [--days N] [--json] [--version]
```

地點可以是台灣地名、`--global` 加上國外地名，或 `lat,lon`。地名轉座標用 Nominatim，跟現在的做法一樣。

```
📍 台北市（25.033, 121.565）
現在：晴時多雲 27.0°C，體感 29.1°C，濕度 70%，風速 12 km/h，UV 6
預報：
  10/08 (Thu)  雨  23–27°C  降雨機率 80%
ℹ️  免費模式沒有官方警報；颱風或豪雨請看當地氣象單位
```

- WeatherKit 模式：有警報時印出 `⚠️ ...` 行，跟現在一樣。
- 免費模式：一律印出最後那行 `ℹ️`。用 ℹ️ 而不是 ⚠️，避免 agent 誤以為真的有警報。
- `--json`：原樣輸出資料來源的 JSON，另外加上 `"source": "open-meteo"` 或 `"weatherkit"`。
- `--version`：印出 `weatherwise 1.0.0 · by SmallYuan · https://github.com/SmallYuanSY/skills`。
- 輸出語言第一版只有繁體中文，但架構預留 i18n，見下一節。

### i18n（第一版只有 `zh-TW`，架構先預留）

- **所有使用者看得到的文字集中在一個語言表**：`MESSAGES = {"zh-TW": {...}}`。輸出的每一行、錯誤訊息、兩張天氣狀況對照表、星期幾都從這裡取，程式其他地方不寫死任何中文。
- **語言設定**：設定檔加上 `"lang": "zh-TW"`，CLI 加上 `--lang`，優先順序是 CLI → 設定檔 → `zh-TW`。指定了表裡沒有的語言時，直接報錯並列出支援的語言，不會默默退回中文。
- **對外 API 也跟著語言走**：WeatherKit 網址裡的語言代碼、Nominatim 的 `accept-language`，都從目前的語言設定帶入，不寫死 `zh-TW`。
- **日期不用系統的 locale**：`%a` 會跟著系統語言變，所以星期幾改由語言表提供，輸出才不會因為機器設定不同而改變。
- **測試**：測試裡臨時加一個假語言，所有 key 都填成 `<key>`，確認輸出的每個字都來自語言表，沒有遺漏的寫死文字；另外檢查每個語言的 key 都跟 `zh-TW` 一致。
- **之後要加英文時**：在語言表加 `"en"`。SKILL.md 和教學的英文版，由轉譯器依語言產生（例如 `src/weatherwise/SKILL.en.md`），這部分第一版不做。

README 是英文，內容只寫安裝方式，並註明「目前輸出為繁體中文」。

### 錯誤訊息

延續現有的寫法，但改成給公開使用者看：`找不到地點`、`連線失敗`、`HTTP 401/403`（WeatherKit 金鑰有問題）、`WeatherKit 設定缺少：...`、`沒有預設地點`。

### SKILL.md

- frontmatter：`name: weatherwise`、`author: SmallYuan`、`license: MIT`、repo 網址，以及中英文都有的 description。
- 指令寫成 `uv run {{SKILL_DIR}}/scripts/weatherwise.py`。
- 回答規則：
  1. 看到 `ℹ️ 免費模式沒有官方警報` 時，不可以說「沒有警報」。颱風季或使用者問到颱風、豪雨時，要提醒他去看當地氣象單位。
  2. 看到 `沒有預設地點` 時，要問使用者在哪裡。
  3. 其餘規則沿用現有 skill。
- 不提作者，也不叫 agent 在回答裡做任何宣傳。

### 署名（全部公開）

LICENSE、SKILL.md 的 frontmatter、`weatherwise.py` 開頭的版權註解、`--version`，以及 Nominatim 規定要有的 User-Agent：`weatherwise/1.0 (+https://github.com/SmallYuanSY/skills)`。

### WeatherKit 教學（`references/weatherkit-setup.md`）

1. 加入 Apple Developer Program（每年 US$99）。
2. 在 Certificates, Identifiers & Profiles 建立 WeatherKit 用的 Service ID，以及啟用 WeatherKit 的金鑰。
3. 下載 `.p8` 檔（只能下載一次），放到 `~/.config/weatherwise/`，權限設為 `chmod 600`。
4. 填寫設定檔的 `weatherkit` 區塊：Team ID、Key ID、Service ID 各自在哪裡找。
5. 驗證：執行 `weatherwise --json`，確認 `source` 是 `weatherkit`。
6. 常見錯誤：401（金鑰或 ID 填錯）、403（Service 沒有開 WeatherKit）。

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

- `tests/test_weatherwise.py`：用錄好的 JSON fixture（WeatherKit 和 Open-Meteo 各一份）測試兩種來源都轉成同樣的輸出，不打網路。另外涵蓋：免費模式的 ℹ️ 行、WeatherKit 的 ⚠️ 行、設定不完整時報錯、沒有預設地點、`--version`。
- `tests/test_translate.py`：佔位符替換、只替換 `.md`、清空舊檔、殘留佔位符時報錯、`--check` 偵測不同步。
- `tests/test_privacy.py`：上面說的 deny-list 掃描。
- 一行指令跑全部：`uv run --with pytest pytest`。
- GitHub Actions：跑測試加上 `translate.py --check`。

## 發布順序

1. 本機完成，測試全過。
2. 手動實測：免費模式查一次台北和東京；用你現有的 WeatherKit 金鑰查一次。
3. 建立公開的 GitHub repo 並 push（推之前會先問你）。
4. smallyuan.dev：卡片標籤從 `macos-weather` 改成 `weatherwise`，並連到 repo。這是首頁 repo 的另一個小改動。

## 待決定

- 你自己 Hermes 裡的 `macos-weather` 要不要換成 `dist/hermes/weatherwise`。不影響這次的實作，可以發布後再決定。
