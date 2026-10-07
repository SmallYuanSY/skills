# skills

Agent skills by [SmallYuan](https://smallyuan.dev), ready to drop into [Hermes](https://github.com/NousResearch/hermes-agent) or [Claude Code](https://claude.com/claude-code).

| Skill | What it does |
|---|---|
| [weatherwise](src/weatherwise/SKILL.md) | Weather, forecast, and rain chance for any place. Free by default (Open-Meteo); Apple WeatherKit optional, which adds official alerts in countries where Apple has them (e.g. the US, not Taiwan or Japan). |

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

## License

[MIT](LICENSE) © 2026 SmallYuan
