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
- `skip` also works ahead of time ("I'm away Saturday, skip laundry"); the next due day then passes over it.
- "Remember to X next time I do Y": `note add "Y" "X"`.
- `notes_resolved:` after `done`: these were reminders for this task. Ask the user whether they got done. If a reminder shown by `time` is for a later time, pass `--keep-notes` on that `done`. If one was already resolved but the user says it is still for later, add it again with `note add`.

## Reading `time`

- `due`, `makeup`: it should be done now. `makeup` means a scheduled day just passed and there is still time.
- `missed`: a scheduled day passed without it. Doing it once settles every missed day; never tell the user they owe several.
- `still due …` after `done`: one more scheduled day is still open (two scheduled days close together).
- `next …`, `no schedule`, `never done`, `last done … (N days ago)`: facts, not judgments. Choose your own tone.
- `schedule:` lines after `done` say which scheduled day it counted for. How days are matched: `${HERMES_SKILL_DIR}/references/schedule.md`.
- `note #N`: a reminder for that item; mention it.

## Errors

- Do what the `action:` line says.
- `unknown_item`: use the exact name from the list in the error. If none fits, ask the user, then add it with routine-setup.
- `already_logged`: tell the user. Add `--force` only if they confirm it really happened twice.

Changing what is tracked or the settings: routine-setup. Past records, fixing a wrong entry, export: routine-history.
