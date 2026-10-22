---
name: weatherwise
description: Current weather, forecast, rain chance, official weather warnings, and typhoon track for the user's location, a destination, or any place (Taiwan, Japan, US, Canada, Hong Kong, Europe; typhoons worldwide). Use when the user asks about weather, temperature, rain, an umbrella, typhoons, warnings, what to wear, or the weather where they are going. 天氣、氣溫、會不會下雨、要不要帶傘、颱風、颱風路徑、特報、警報、豪雨、明天／這週天氣、出門前看天氣、要去某地的天氣。
version: 2.0.0
author: SmallYuan
license: MIT
homepage: https://github.com/SmallYuanSY/skills
platforms: [macos, linux]
metadata:
  hermes:
    tags: [weather, 天氣, forecast, rain, typhoon, alerts, GDACS, WeatherKit, Open-Meteo]
prerequisites:
  commands: [uv]
---

# weatherwise

Run the command, then answer from its output. The output is written for you, not for the user: read it and answer in the user's own language.

## Commands

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py                 # default location
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py 板橋             # a place in Taiwan (searched first)
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py 板橋 礁溪        # several places in one run, 5 at most
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py Tokyo --global  # a place outside Taiwan
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py 24.15,120.67    # coordinates
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py --days 7        # forecast days, 1-10 (default 3; several places: today only unless set)
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py 礁溪 --detail    # full alert text, and the alerts hidden by "+N more"
```

## Trips

If the user is going somewhere ("我今天要去礁溪"), pass the destination, and the start too if it helps. Don't add places along the route. Road closures and traffic are not covered: tell them to check their navigation app. More than 5 places gives `error: too_many_places`: keep the most important ones.

## Reading the output

- `local_time` is the current time at that place. Use it to work out "today", "tomorrow", and weekdays.
- `location` (or `[1] ...`, `[2] ...` for several places) must be the place the user meant. If not, retry with a fuller name, `--global`, or coordinates. Places abroad are named in the local language (千代田区, 東京都; Mitte, Berlin): still answer in the user's language.
- `now`, `next_hour`, `daily`: answer with conditions, temperature, and rain chance. `next_hour` says whether rain is expected in the next hour (or `unavailable here`): pass it on when the user is about to go out.
- Alerts are current only, not a forecast for later days. The block header shows `as of <time>`: for "tomorrow" or "this weekend", say that an alert is active now and may change.
- `alerts (as of …)` followed by items: always mention every one. Each item is `[severity] title: summary, until <time>`.
  - `[1][2]` tags show which places an item applies to. `超大豪雨 [2] / 大豪雨 [1]` means a different level at each place.
  - `+N more (run again with --detail)`: more alerts exist. Run again with `--detail` if they matter.
- `alerts: none`: the official source was checked and nothing is active.
- `alerts: unsupported`: there is no official source for this place, or its area could not be matched (also a quiet place in a name-only European feed). Never say there are no alerts. If the weather looks severe, or they ask about typhoons or heavy rain, tell them to check the local weather agency.
- `alerts: unavailable (reason)`: the source failed this time. Never say there are no alerts. Suggest checking the local weather agency, or trying again later.
- `cyclones (track data, not a local official warning):` is track data only, not an official warning. Tell the user to check the local weather agency. If an official alert for the same storm is listed, use the alert for the warning level and times.
- `cyclones: unavailable (reason; …)`: typhoon track data could not be read this time. Never say there is no typhoon. If they ask about typhoons, tell them to check the local weather agency.
- Cyclone lines give the current distance and direction and the forecast closest distance, but no closest-approach time. Only give a time if an official alert's text gives one.
- Turn compass letters and km into plain words. Don't read out "SE 470 km". Say "颱風在台灣東南方海面，明天傍晚最接近，大約在宜蘭外海 120 公里" (the time part only when known). People don't know which way "southeast" points.
- `notice:` always pass it on to the user.
- `[1] error: ...` with `action:` (or a top-level `error:`): do what the `action:` line says. One failed place doesn't stop the others.
- Don't mention data sources in the answer.

## Settings

Change settings only with these commands. Never edit the config file by hand.

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py config show
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py config set-default <place> [--global]
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py config set-lang <lang>
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py config weatherkit --team-id <id> --service-id <id> --key-file <path to .p8>
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py config weatherkit --key-file <path to new .p8>   # new key, keeps the saved IDs
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py config weatherkit --remove
```

- After `set-default`, tell the user the place that was saved and ask them to confirm it.
- `lang` only sets the language of place names and alert text (a BCP 47 tag such as `zh-TW`, `en`, `ja`). It does not change the language you answer in.
- WeatherKit is optional: it improves the forecast and next-hour rain in some countries. Alerts never depend on it. It needs a paid Apple Developer membership. If the user wants it, walk them through `${CLAUDE_SKILL_DIR}/references/weatherkit-setup.md` one step at a time. Only the user can do the steps on Apple's website. The Key ID is read from the key's file name.
- `config show` shortens IDs on purpose. Never fill in, guess, or retype an ID: take it from the user, or leave it out so the saved one is kept.
- If the user would rather not paste their IDs into the chat, give them the full command to run in their own terminal (in Claude Code, they can type it after `!`).
- Never open, print, or paste the contents of a `.p8` key file. Only ever handle its path.
