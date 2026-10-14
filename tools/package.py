#!/usr/bin/env python3
"""Release zips for skills that ship hand-written per-agent folders (e.g. routine-keeper).

  uv run tools/package.py routine-keeper [--out build]

src/<skill>/scripts/ is copied into each src/<skill>/<agent>/ folder. The result goes to
build/<agent>/<skill>/ (copy that folder to install locally) and build/<skill>-<agent>.zip.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ("hermes", "claude")
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "config.json", "data", ".config-*")


def assemble(skill_src: Path, agent: str, dest: Path) -> Path:
    out = dest / skill_src.name
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(skill_src / agent, out, ignore=_IGNORE)
    shutil.copytree(skill_src / "scripts", out / "scripts", ignore=_IGNORE)
    return out


def package(skill: str, out: Path, src_root: Path = ROOT / "src") -> list[Path]:
    skill_src = src_root / skill
    out.mkdir(parents=True, exist_ok=True)
    zips = []
    for agent in AGENTS:
        folder = assemble(skill_src, agent, out / agent)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / f"{skill}-{agent}"
            archive = shutil.make_archive(str(base), "zip", root_dir=folder.parent, base_dir=folder.name)
            target = out / f"{skill}-{agent}.zip"
            shutil.move(archive, target)
        zips.append(target)
    return zips


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build release zips for a skill with per-agent folders.")
    p.add_argument("skill")
    p.add_argument("--out", default=str(ROOT / "build"))
    a = p.parse_args(argv)
    if not all((ROOT / "src" / a.skill / x).is_dir() for x in ("scripts", *AGENTS)):
        print(f"error: src/{a.skill} needs scripts/, hermes/, and claude/")
        return 1
    for z in package(a.skill, Path(a.out)):
        print(f"built {z}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
