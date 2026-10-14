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
