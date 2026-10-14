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
