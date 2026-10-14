# skills

Agent skills by [SmallYuan](https://smallyuan.dev), ready to drop into [Hermes](https://github.com/NousResearch/hermes-agent) or [Claude Code](https://claude.com/claude-code).

| Skill | What it does |
|---|---|
| [weatherwise](src/weatherwise/SKILL.md) | Weather, forecast, and rain chance for any place. Free by default (Open-Meteo); Apple WeatherKit optional, which adds official alerts in countries where Apple has them (e.g. the US, not Taiwan or Japan). |
| [routine-keeper](src/routine-keeper/claude/SKILL.md) | Chores and supplements/medication: log what was done, check any day, weekly or every-N-days schedules that forgive doing it early or late, and reminders for next time. Hermes gets a category of three small skills; Claude Code gets one. |

## Install

Each skill comes pre-built for each agent in `dist/`. Copy the folder for your agent:

```bash
git clone https://github.com/SmallYuanSY/skills.git

# Hermes
cp -R skills/dist/hermes/weatherwise ~/.hermes/skills/

# Claude Code
cp -R skills/dist/claude/weatherwise ~/.claude/skills/
```

weatherwise needs [uv](https://docs.astral.sh/uv/). Its Python dependencies install themselves on first run.

### routine-keeper

routine-keeper ships as release zips instead of `dist/`: download the one for your agent from the [releases](https://github.com/SmallYuanSY/skills/releases) page.

```bash
# Hermes
unzip routine-keeper-hermes.zip -d ~/.hermes/skills/

# Claude Code
unzip routine-keeper-claude.zip -d ~/.claude/skills/
```

It needs Python 3.9+ (the `python3` that ships with macOS works) and nothing else. Its settings (`config.json`) and records (`data/`) live inside the skill folder, so **to upgrade, unzip over the existing folder; never delete it first.** Ask your agent to move the data elsewhere (`data move`) if you'd rather keep it outside.

## Setup

Just ask your agent, e.g. "set my default location to Taipei". It runs the right `config` command for you. For Apple WeatherKit, ask it to walk you through [the setup guide](src/weatherwise/references/weatherkit-setup.md).

The command's output is written for the agent to read (plain English `key: value` lines). Your agent answers in your own language.

## Development

Edit skills only in `src/`. `dist/` is generated:

```bash
uv run tools/translate.py   # rebuild dist/ from src/
uv run pytest               # tests (no network)
```

The translator replaces `{{SKILL_DIR}}` in Markdown files with each agent's skill-folder variable (`${HERMES_SKILL_DIR}`, `${CLAUDE_SKILL_DIR}`). To support another agent, add a row to `TARGETS` in `tools/translate.py`.

routine-keeper keeps one `scripts/` and two hand-written skill folders (`hermes/`, `claude/`); the translator skips it. Build its zips with:

```bash
uv run tools/package.py routine-keeper   # build/<agent>/routine-keeper/ and build/routine-keeper-<agent>.zip
```

Pushing a `routine-keeper-v*` tag publishes them as a GitHub release.

## License

[MIT](LICENSE) © 2026 SmallYuan
