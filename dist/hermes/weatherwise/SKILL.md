---
name: weatherwise
description: Current weather, multi-day forecast, and rain chance for the user's location or any place, plus official alerts where Apple WeatherKit has them (if set up). Use when the user asks about weather, temperature, rain, an umbrella, typhoons, or what to wear. 天氣、氣溫、會不會下雨、要不要帶傘、颱風、明天／這週天氣、出門前看天氣。
version: 2.0.0
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
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py                 # default location
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py 板橋             # a place in Taiwan (searched first)
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py Tokyo --global  # a place outside Taiwan
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py 24.15,120.67    # coordinates
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py --days 7        # forecast days, 1-10 (default 3)
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
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py config show
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py config set-default <place> [--global]
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py config set-lang <lang>
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py config weatherkit --team-id <id> --service-id <id> --key-file <path to .p8>
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py config weatherkit --key-file <path to new .p8>   # new key, keeps the saved IDs
uv run ${HERMES_SKILL_DIR}/scripts/weatherwise.py config weatherkit --remove
```

- After `set-default`, tell the user the place that was saved and ask them to confirm it.
- `lang` only sets the language of place names and alert text (a BCP 47 tag such as `zh-TW`, `en`, `ja`). It does not change the language you answer in.
- WeatherKit is optional and needs a paid Apple Developer membership. If the user wants it, walk them through `${HERMES_SKILL_DIR}/references/weatherkit-setup.md` one step at a time. Only the user can do the steps on Apple's website. The Key ID is read from the key's file name.
- `config show` shortens IDs on purpose. Never fill in, guess, or retype an ID: take it from the user, or leave it out so the saved one is kept.
- If the user would rather not paste their IDs into the chat, give them the full command to run in their own terminal (in Claude Code, they can type it after `!`).
- Never open, print, or paste the contents of a `.p8` key file. Only ever handle its path.
