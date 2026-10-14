import subprocess
import sys
import zipfile

import package

ROOT = package.ROOT


def test_zips_hold_each_agents_layout(tmp_path):
    zips = package.package("routine-keeper", tmp_path)
    assert sorted(z.name for z in zips) == ["routine-keeper-claude.zip", "routine-keeper-hermes.zip"]
    hermes = set(zipfile.ZipFile(tmp_path / "routine-keeper-hermes.zip").namelist())
    assert {"routine-keeper/DESCRIPTION.md", "routine-keeper/routine-log/SKILL.md",
            "routine-keeper/routine-setup/SKILL.md", "routine-keeper/routine-history/SKILL.md",
            "routine-keeper/scripts/routine.py", "routine-keeper/scripts/routine_core/schedule.py"} <= hermes
    claude = set(zipfile.ZipFile(tmp_path / "routine-keeper-claude.zip").namelist())
    assert {"routine-keeper/SKILL.md", "routine-keeper/references/setup.md",
            "routine-keeper/references/schedule.md", "routine-keeper/scripts/routine.py"} <= claude
    assert "routine-keeper/routine-log/references/schedule.md" in hermes
    for names in (hermes, claude):
        assert not [n for n in names if "__pycache__" in n or n.endswith((".pyc", "config.json"))
                    or "/data/" in n or ".DS_Store" in n]


def test_local_config_and_data_never_ship(tmp_path):
    src = tmp_path / "src" / "demo"
    for agent in ("hermes", "claude"):
        (src / agent).mkdir(parents=True)
        (src / agent / "SKILL.md").write_text("x\n")
    (src / "scripts" / "data").mkdir(parents=True)
    (src / "scripts" / "run.py").write_text("print(1)\n")
    (src / "scripts" / "data" / "routine.db").write_bytes(b"\0")
    (src / "scripts" / "config.json").write_text("{}")
    package.package("demo", tmp_path / "out", src_root=tmp_path / "src")
    names = [n for n in zipfile.ZipFile(tmp_path / "out" / "demo-hermes.zip").namelist() if not n.endswith("/")]
    assert sorted(names) == ["demo/SKILL.md", "demo/scripts/run.py"]


def test_assembled_hermes_copy_runs_and_keeps_data_inside(tmp_path):
    package.package("routine-keeper", tmp_path)
    skill = tmp_path / "hermes" / "routine-keeper"
    r = subprocess.run([sys.executable, str(skill / "scripts" / "routine.py"), "time", "today"],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.startswith("date: ")
    assert (skill / "data" / "routine.db").exists()
    assert r.stderr == ""
