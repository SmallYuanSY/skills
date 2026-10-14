# routine-keeper：設計

日期：2026-10-14
狀態：待審

## 目標

做一個讓 AI 個人助理管理使用者**家事**與**保健品／藥品**的 skill。agent 只呼叫 CLI，不讀、也不改任何 Markdown 或資料檔。

起因：用 Markdown 週表讓 agent 讀完再 patch，會出現排序錯亂、打勾跟內容對不上、「最後更新」沒同步、檔案越長越大、每次都要讀一大段等問題。

**成功標準**

- 使用者用講的（「我吃藥了」「洗衣服改成每週三、六」「10/13 我做了什麼」），agent 都能透過一個 CLI 指令完成，不需要讀任何資料檔。
- 提前做、延後做、補做、刻意跳過，系統都算得對，不會累積「欠債」。
- 跨夜的紀錄（例如凌晨 2 點吃睡前藥）會歸到正確的那一天。
- agent 不會預先填寫還沒發生的事。
- 新增或修改設定時，agent 一定會跟使用者確認實際存下的內容。
- 在 Hermes 的 skill 索引裡觸發詞不會被截斷。
- Hermes 和 Claude Code 都能直接安裝。
- repo 裡沒有任何私人資訊。

**不做的事**

- 不做輸出的多語言：輸出固定英文，給 agent 讀，agent 用使用者的語言回答。
- 不做 `import`：初始資料由使用者（或 agent）用一般的 CLI 指令建立。
- 不做推播或排程通知：何時提醒由 agent 和使用者自己的 cron 決定，本 skill 只回答「某天狀態如何」。
- 不做轉譯器支援；Hermes 版和 Claude Code 版各自手寫。

## Repo 結構

```
src/routine-keeper/
├── scripts/                       唯一一份程式
│   ├── routine.py                 薄 CLI：argparse，只負責分派
│   └── routine_core/              db / items / logs / notes / schedule / dates / storage / render / errors
├── hermes/                        Hermes 版（分類結構）
│   ├── DESCRIPTION.md
│   ├── routine-log/SKILL.md
│   ├── routine-setup/SKILL.md
│   └── routine-history/SKILL.md
└── claude/                        Claude Code 版（單一 skill）
    ├── SKILL.md
    └── references/
        ├── setup.md
        └── history.md
tests/test_routine_*.py
.github/workflows/release-routine-keeper.yml
```

- `scripts/` 只有一份。release workflow 把它分別複製進 `hermes/` 和 `claude/` 的組裝結果，打包成 `routine-keeper-hermes.zip` 和 `routine-keeper-claude.zip`，附在 GitHub release 上。這是組裝，不做任何文字轉換。
- weatherwise 的 `tools/translate.py` 和 `dist/` 流程不受影響。
- Python 3.10 以上，只用標準函式庫（`sqlite3`、`zoneinfo`、`argparse`、`json`），零依賴。指令寫成 `python3 .../routine.py`，不需要 `uv`。

### 安裝後的樣子

Hermes（解壓到 `~/.hermes/skills/`）：
```
~/.hermes/skills/routine-keeper/
├── DESCRIPTION.md
├── scripts/
├── config.json          ← 第一次執行時產生
├── data/routine.db      ← 預設資料位置
├── routine-log/SKILL.md
├── routine-setup/SKILL.md
└── routine-history/SKILL.md
```

Claude Code（解壓到 `~/.claude/skills/`）：
```
~/.claude/skills/routine-keeper/
├── SKILL.md
├── references/
├── scripts/
├── config.json
└── data/routine.db
```

- Hermes 子 skill 用 `${HERMES_SKILL_DIR}/../scripts/routine.py` 呼叫；Claude 版用 `${CLAUDE_SKILL_DIR}/scripts/routine.py`。
- 程式以 `routine.py` 所在位置往上一層當作 skill 根目錄，從那裡找 `config.json`，不依賴環境變數。
- **升級方式**：把新版解壓後直接覆蓋，不要先刪資料夾，否則 `config.json` 和 `data/` 會一起消失。README 和 SKILL.md 都要寫明；想保險的話可以先用 `data move` 把資料搬到 skill 外面。
- `config.json`、`data/` 加進 `.gitignore`，release zip 裡也不包含這兩個。

## Skill 撰寫規則

Hermes 的 system prompt 索引會把每個 skill 的 `description` 截成 60 字元（`agent/skill_utils.py` 的 `SKILL_PROMPT_DESC_LIMIT`），超過的部分變成 `...`。分類資料夾的 `DESCRIPTION.md` 則會完整顯示。另外列出 skill 時只解析 SKILL.md 前 4000 字元的 frontmatter，terminal 輸出上限是 50,000 bytes。

因此：

- Hermes 版用**分類結構**：`DESCRIPTION.md` 寫完整的觸發詞（可以多語言，例如 chores, supplements, medication, 家事、吃藥、保健品、洗衣服、有沒有做過）。
- 每個子 skill 的 `description` **不超過 60 字元**，`name` 必須跟資料夾名稱相同（Hermes linter 的 `name-dir-mismatch`）。
- frontmatter 保持精簡，帶 `version`、`author`、`license`。
- 子 skill 依情境拆分，讓日常最常用的那個最短：

| 子 skill | 用途 | description（草稿） |
|---|---|---|
| `routine-log` | 記錄完成、跳過、提醒，查某天狀態 | `Log a chore or dose as done/skipped; check a day` |
| `routine-setup` | 新增或修改項目、設定、搬移資料 | `Add or change tracked chores, doses, settings` |
| `routine-history` | 查歷史、修改或刪除紀錄、匯出 | `Browse, fix, or export past chore/dose records` |

- Claude 版是單一 skill：`SKILL.md` 放 `routine-log` 的內容，另外兩個變成 `references/setup.md`、`references/history.md`，SKILL.md 寫明什麼時候要去讀。
- SKILL.md 只放三件事：指令、怎麼讀輸出、什麼時候要跟使用者確認。排程規則的細節放 references。

## 資料模型（SQLite）

```
items      id, kind('chore'|'dose'), name UNIQUE, aliases(JSON list), schedule, window_early, window_late,
           slot, active, created_at, updated_at
logs       id, item_id, at(真實時間, ISO8601 含時區), for_date(YYYY-MM-DD), note, created_at, deleted_at
skips      id, item_id, for_date, reason, created_at, deleted_at
log_edits  id, log_id, field, old_value, new_value, edited_at
notes      id, item_id, text, created_at, resolved_at, resolved_by_log
meta       key, value   -- schema_version, day_boundary, timezone
```

- 名稱比對時，`name` 和 `aliases` 都不分大小寫，且在所有 item 之間不能重複。
- 刪除一律是軟刪除（`deleted_at`），可以還原。
- `meta` 預設值：`day_boundary=05:00`；`timezone` 預設用系統時區，第一次執行時寫入。

### 設定檔 `config.json`

只放一個欄位：`data_dir`。不存在時視為 `<skill 根目錄>/data`。寫入一律先寫暫存檔再改名。

## 日期規則

- **日界線**：預設 05:00，可以調整。真實時間落在日界線之前的紀錄，`for_date` 算前一天。例如日界線 05:00，10/02 03:10 吃的睡前藥會算在 10/01。
- **`--for DATE`**：手動指定歸屬日，優先於日界線。
- **`--at`**：補記過去的時間，預設是現在。
- **防預填**：`--at` 晚於現在，或 `--for` 晚於「今天」（依日界線判斷），一律拒絕。
- `time today`、`time yesterday` 的「今天」也依日界線判斷。

## 排程規則

這是整個系統最容易出錯的地方，**先寫測試再實作**。

### 規則種類

| schedule | 意義 | 預設給 |
|---|---|---|
| `daily` | 每天一次 | dose |
| `none` | 只記錄，不判斷該不該做 | chore |
| `interval:N` | 距離上次完成 N 天 | — |
| `weekly:mon,thu` | 每週固定星期幾 | — |

### `interval:N`

- 下次到期日 = 上次實際完成的 `for_date` + N 天。
- 提前或延後都只影響下一輪，不累積。輸出會標示這次比預定提前或延後幾天。
- 從來沒完成過：狀態是 `never_done`。

### `weekly:...`

- 每個預定日都是一個「場次」，各自有容許窗口：`[預定日 - early, 預定日 + late]`，預設 early=1、late=2，可以用 `--window -1,+2` 調整。
- **配對**：依時間順序處理每一次完成，每次只抵掉一個場次，優先抵**最早**、還沒被抵掉、而且窗口包含這次完成的場次。所以補做會優先於提前做。
- **錯過併入**：一次完成時，所有早於這次完成、但還沒被抵掉的場次，都標成 `merged`（併入這次完成）。
- **不在任何窗口內的完成**：不抵掉未來的場次，只結清之前錯過的場次；如果之前也沒有錯過的場次，就記為 `extra`（額外多做一次），不影響排程。
- **skip**：被 `skip` 指定的場次標成 `skipped`，不參與配對。
- 欠的永遠不會超過「目前這一場」：拖了很多場，做一次就全部結清。

場次狀態：

| 狀態 | 意思 |
|---|---|
| `upcoming` | 還沒到窗口 |
| `due` | 在窗口內、預定日當天或之前，還沒完成 |
| `makeup` | 過了預定日、仍在窗口內，還沒完成 |
| `missed` | 窗口已過、還沒完成，也還沒被後來的完成併入 |
| `done` / `done_early` / `done_late` | 被一次完成抵掉，以及相對預定日的偏差 |
| `merged` | 錯過後被之後的一次完成結清 |
| `skipped` | 刻意跳過 |

範例（`weekly:wed,sat`，窗口 -1/+2）：

| 情境 | 結果 |
|---|---|
| 週二做 | 週三 `done_early` |
| 週六沒做，週一做 | 週六 `done_late`；週三照常 `due` |
| 週六沒做，週二做 | 週六 `merged`；週三 `done_early` |
| 週六沒做，週三做 | 週六 `merged`；週三 `done` |
| 週六 skip，週三做 | 週六 `skipped`；週三 `done` |

### `daily`（dose）

- 某天沒有紀錄就是 `not_done`，有紀錄就是 `done`（附時間）。
- 同一天重複記錄會被拒絕（`error: already_logged`），要用 `--force` 才寫入。chore 允許同一天記錄多次。

### 輸出用詞

只講事實：上次是哪天、隔了幾天、哪一場是什麼狀態。不使用 overdue、late、failed 這類帶壓力的詞，語氣交給 agent 決定。

## CLI

```
routine.py item add  --kind chore|dose --name N [--schedule S] [--window -E,+L] [--slot T] [--alias A ...]
routine.py item edit N [--name] [--schedule] [--window] [--slot] [--alias A ...] [--remove-alias A ...]
routine.py item pause N | item resume N
routine.py item list [--kind chore|dose] [--all]

routine.py done N [--at "YYYY-MM-DD HH:MM"] [--for YYYY-MM-DD] [--note T] [--keep-notes] [--force]
routine.py skip N --for YYYY-MM-DD [--reason T]

routine.py time today | yesterday | YYYY-MM-DD

routine.py log list [--item N] [--from D] [--to D] [--limit K]     # 預設 --limit 50，新到舊
routine.py log edit ID [--at] [--for] [--note]
routine.py log delete ID | log restore ID

routine.py note add N TEXT | note list | note resolve ID

routine.py config show
routine.py config set day-boundary HH:MM | config set timezone Area/City

routine.py data where
routine.py data move --to PATH [--use-existing | --overwrite]

routine.py export [--file F.json]
```

- 全域旗標 `--json`：輸出結構化資料，給腳本使用。
- `--version`：印出版本。

## 輸出契約

跟 weatherwise 一樣，輸出是英文的 `key: value` 行，寫給 agent 讀。

`time` 範例：
```
date: 2026-10-14 (Wed)
now: 2026-10-14 16:20 Asia/Taipei
day_boundary: 05:00

doses:
- Vitamin D [after breakfast]: done 10:42
- Magnesium [bedtime]: not_done

chores:
- Laundry [weekly wed,sat]: due | last done 2026-10-07 (7 days ago)
  note #3: wash the jacket
- Litter box [none]: done 14:10
- Bed sheets [interval 14]: due since 2026-10-03 (11 days) | last done 2026-09-19
```

`done` 範例：
```
ok: logged Laundry for 2026-10-15 (Wed) at 2026-10-15 18:20
schedule: Wed 2026-10-15 done; Sat 2026-10-11 merged
notes_resolved: #3 wash the jacket
```

規則：

- **錯誤**：一律輸出 `error: <code>` 加 `action: <下一步>`，任何例外都不吐 traceback。
  ```
  error: unknown_item
  action: no item named "Vitamin". Existing: Vitamin D, Magnesium. Retry with the exact name, or add an alias.
  ```
- **exit code**：0 成功；1 指令或參數用錯；2 業務錯誤（`unknown_item`、`future_time`、`already_logged`、`name_taken`…）；3 資料位置錯誤（找不到、不能寫入、DB 損毀、版本不符）。
- **確認**：`item add`、`item edit`、`config set`、`data move` 成功後，輸出 `confirm:` 行，用白話列出實際存下的內容，例如 `confirm: Laundry, chore, every Wed and Sat, can be done 1 day early or 2 days late`。SKILL.md 規定 agent **必須把 confirm 的內容告訴使用者並請他確認**，使用者說不對就用 `item edit` 修正。
- **名稱對不上**：不做模糊比對，回 `unknown_item` 並列出現有名稱。
- **提醒**：`done` 預設結清該項目所有未結清的提醒，並用 `notes_resolved:` 列出來，SKILL.md 規定 agent 要順口跟使用者確認那些事有沒有做到。加 `--keep-notes` 就不結清。
- **輸出長度**：`log list` 預設最多 50 筆；`time` 只列 active 的項目。

## `data move`

1. 目標資料夾不存在就建立。
2. 目標已經有 `routine.db` 時：預設回 `error: target_exists`；加 `--use-existing` 就直接切換過去、不複製；加 `--overwrite` 就覆蓋。
3. 用 SQLite backup API 複製，再核對每張表的筆數，不一致就回 exit 3 並保留原狀。
4. 更新 `config.json` 的 `data_dir`。
5. 舊檔不刪，改名成 `routine.db.moved-<YYYYMMDDHHMMSS>`，並在輸出中列出路徑。
6. 輸出 `confirm:`，列出新位置。

## 測試

- 所有「現在時間」都從參數注入（`main(argv, now=..., skill_root=...)`），不讀系統時鐘。
- `test_routine_schedule.py`：排程引擎，至少包含上面範例表的每一列，另外還有：窗口重疊（例如 `weekly:fri,sat`）、跨月、跨年、連續錯過多場後做一次、skip 後補做、interval 提前和延後、`never_done`、更改 schedule 後的重新計算。
- `test_routine_dates.py`：日界線前後、`--for`、時區、防預填。
- `test_routine_cli.py`：完整流程（add → done → time → log edit → delete → restore）、錯誤格式和 exit code、`confirm:` 輸出、`--json`、名稱和別名比對、防重複和 `--force`、提醒結清和 `--keep-notes`。
- `test_routine_storage.py`：預設路徑、`data move` 的三種情境、核對失敗時保留原狀、config 原子寫入、DB 版本不符。
- `test_routine_skills.py`：每個子 skill 的 `description` 不超過 60 字元、`name` 跟資料夾一致、Hermes 版的路徑用 `${HERMES_SKILL_DIR}/../scripts/`、Claude 版用 `${CLAUDE_SKILL_DIR}/scripts/`、SKILL.md 提到的每個子指令都真的存在。
- 沿用現有的 `test_privacy.py`，把 `src/routine-keeper/` 納入掃描範圍。

## 發布流程

1. 在 `routine-keeper` 分支開發，測試全部通過。
2. 在本機組裝 Hermes 版，複製到 `~/.hermes/skills/`，用真實對話測試（記錄、補記、查某天、新增項目並確認、搬資料）。發現問題就回頭修改輸出格式或 SKILL.md。
3. 同樣測一次 Claude Code 版。
4. 更新 README：skill 列表、release zip 安裝方式、升級時不要刪資料夾。
5. PR 合併後打 tag，觸發 release workflow 產生兩個 zip（push 和發 release 之前先問使用者）。

## 後續待辦

- **⚠️ 提醒使用者：weatherwise 要改用同樣的 skill 架構。** 它目前的 `description` 大約 330 字元，在 Hermes 索引裡只剩前 57 字元，後面的中文觸發詞（天氣、帶傘、颱風…）全部被截掉。routine-keeper 完成後，要把 weatherwise 也改成「Hermes 版分類結構加 `DESCRIPTION.md`、Claude 版單一 skill、兩套手寫、release 附兩個 zip」，並決定 `tools/translate.py` 和 `dist/` 是否保留。
