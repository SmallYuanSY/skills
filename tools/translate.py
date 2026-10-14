#!/usr/bin/env python3
"""Skill translator: one source skill in src/, one installable copy per agent in dist/.

  uv run tools/translate.py          rebuild dist/ from src/
  uv run tools/translate.py --check  exit 1 if dist/ is out of date
"""
import argparse
import filecmp
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "{{SKILL_DIR}}"
LEFTOVER = re.compile(r"\{\{[A-Z_]+\}\}")
# Add a row here to support another agent
TARGETS = {
    "hermes": "${HERMES_SKILL_DIR}",
    "claude": "${CLAUDE_SKILL_DIR}",
}


class TranslateError(Exception):
    pass


def _skip(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix == ".pyc" or path.name == ".DS_Store"


def _skill_dirs(src: Path) -> list[Path]:
    """Only folders with a SKILL.md at their root are translated; others (e.g. hand-written
    per-agent skills such as routine-keeper) are packaged by tools/package.py instead."""
    return [d for d in sorted(src.iterdir()) if d.is_dir() and (d / "SKILL.md").is_file()]


def _render(src: Path, out: Path) -> None:
    for target, skill_dir in TARGETS.items():
        for skill in _skill_dirs(src):
            for f in sorted(skill.rglob("*")):
                rel = f.relative_to(src)
                if f.is_dir() or _skip(rel):
                    continue
                dest = out / target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if f.suffix == ".md":
                    text = f.read_text(encoding="utf-8").replace(PLACEHOLDER, skill_dir)
                    if m := LEFTOVER.search(text):
                        raise TranslateError(f"{rel}: unknown placeholder {m.group(0)}")
                    dest.write_text(text, encoding="utf-8")
                else:
                    shutil.copy2(f, dest)


def build(src: Path, out: Path) -> None:
    """Render everything into a temp dir first, so a mistake never leaves dist/ half-written."""
    with tempfile.TemporaryDirectory() as tmp:
        _render(src, Path(tmp))
        for target in TARGETS:
            shutil.rmtree(out / target, ignore_errors=True)
            built = Path(tmp) / target
            if built.exists():
                shutil.copytree(built, out / target)


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not _skip(p)} if root.exists() else set()


def check(src: Path, out: Path) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        _render(src, fresh)
        problems = []
        for target in TARGETS:
            a, b = _files(fresh / target), _files(out / target)
            for rel in sorted(a | b):
                pa, pb = fresh / target / rel, out / target / rel
                if rel not in a or rel not in b or not filecmp.cmp(pa, pb, shallow=False):
                    problems.append(f"{target}/{rel}")
        return sorted(problems)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build per-agent copies of the skills in src/.")
    p.add_argument("--check", action="store_true", help="exit 1 if dist/ is out of date")
    a = p.parse_args(argv)
    src, out = ROOT / "src", ROOT / "dist"
    try:
        if a.check:
            problems = check(src, out)
            for rel in problems:
                print(f"out of date: dist/{rel}")
            if problems:
                print("run: uv run tools/translate.py")
                return 1
            print("dist/ is up to date")
            return 0
        build(src, out)
        print(f"built dist/ for: {', '.join(TARGETS)}")
        return 0
    except TranslateError as e:
        print(f"error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
