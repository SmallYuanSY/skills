import re
from pathlib import Path

import pytest

import routine

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "routine-keeper"
HERMES = SRC / "hermes"
CLAUDE = SRC / "claude"
HERMES_SKILLS = ["routine-log", "routine-setup", "routine-history"]
HERMES_CMD = "${HERMES_SKILL_DIR}/../scripts/routine.py"
CLAUDE_CMD = "${CLAUDE_SKILL_DIR}/scripts/routine.py"
GROUPS = {"item", "log", "note", "config", "data"}


def frontmatter(path: Path) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    raw = text.split("---\n", 2)[1]
    fields = {}
    for line in raw.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            fields[m[1]] = m[2].strip().strip("'\"")
    return raw, fields


def all_md(base: Path):
    return sorted(base.rglob("*.md"))


@pytest.mark.parametrize("name", HERMES_SKILLS)
def test_hermes_sub_skills_fit_the_index(name):
    raw, fm = frontmatter(HERMES / name / "SKILL.md")
    assert fm["name"] == name
    assert 0 < len(fm["description"]) <= 60, fm["description"]
    for key in ("version", "author", "license"):
        assert fm.get(key), key
    assert len(raw) < 4000


def test_hermes_category_description():
    _, fm = frontmatter(HERMES / "DESCRIPTION.md")
    assert "家事" in fm["description"] and "chores" in fm["description"]


def test_schedule_reference_is_shared_and_linked():
    hermes_ref = HERMES / "routine-log" / "references" / "schedule.md"
    claude_ref = CLAUDE / "references" / "schedule.md"
    assert hermes_ref.read_text() == claude_ref.read_text()
    assert "${HERMES_SKILL_DIR}/references/schedule.md" in (HERMES / "routine-log" / "SKILL.md").read_text()
    assert "${CLAUDE_SKILL_DIR}/references/schedule.md" in (CLAUDE / "SKILL.md").read_text()
    for path in (HERMES / "routine-log" / "SKILL.md", CLAUDE / "SKILL.md"):
        assert "--keep-notes" in path.read_text()


def test_claude_skill_frontmatter():
    _, fm = frontmatter(CLAUDE / "SKILL.md")
    assert fm["name"] == "routine-keeper"
    assert 0 < len(fm["description"]) <= 1024


def test_command_paths_match_each_agent():
    for path in all_md(HERMES):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "routine.py" in line and "scripts/routine.py" in line:
                assert HERMES_CMD in line, f"{path}: {line}"
    for path in all_md(CLAUDE):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "scripts/routine.py" in line:
                assert CLAUDE_CMD in line, f"{path}: {line}"
    for path in all_md(SRC):
        assert "{{" not in path.read_text(encoding="utf-8"), path


def documented_commands():
    found = set()
    for path in all_md(SRC):
        for m in re.finditer(r"routine\.py ([a-z]+)(?: ([a-z]+))?", path.read_text(encoding="utf-8")):
            cmd, sub = m[1], m[2]
            found.add((cmd, sub if cmd in GROUPS else None))
    return sorted(found, key=str)


def test_every_documented_command_exists(capsys):
    cmds = documented_commands()
    assert ("done", None) in cmds and ("item", "add") in cmds
    for cmd, sub in cmds:
        argv = [cmd] + ([sub] if sub else []) + ["--help"]
        assert routine.main(argv) == 0, argv
    capsys.readouterr()
