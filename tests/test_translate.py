import pytest

import translate
from translate import PLACEHOLDER, TranslateError, build, check

ROOT = translate.ROOT


@pytest.fixture
def src(tmp_path):
    s = tmp_path / "src" / "demo"
    (s / "scripts").mkdir(parents=True)
    (s / "SKILL.md").write_text(f"run {PLACEHOLDER}/scripts/x.py\n")
    (s / "scripts" / "x.py").write_text(f"print('{PLACEHOLDER}')\n")
    (s / "scripts" / "__pycache__").mkdir()
    (s / "scripts" / "__pycache__" / "x.cpython-314.pyc").write_bytes(b"\0")
    return tmp_path / "src"


def test_each_target_gets_its_own_skill_dir(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    assert (out / "hermes/demo/SKILL.md").read_text() == "run ${HERMES_SKILL_DIR}/scripts/x.py\n"
    assert (out / "claude/demo/SKILL.md").read_text() == "run ${CLAUDE_SKILL_DIR}/scripts/x.py\n"


def test_only_markdown_is_rewritten_and_caches_are_skipped(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    assert (out / "claude/demo/scripts/x.py").read_text() == f"print('{PLACEHOLDER}')\n"
    assert not (out / "claude/demo/scripts/__pycache__").exists()


def test_rebuild_removes_deleted_files(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    (src / "demo/scripts/x.py").unlink()
    build(src, out)
    assert not (out / "hermes/demo/scripts/x.py").exists()


def test_unknown_placeholder_fails_without_touching_dist(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    (src / "demo/SKILL.md").write_text("{{SKILL_DIRR}}\n")
    with pytest.raises(TranslateError, match="SKILL_DIRR"):
        build(src, out)
    assert "HERMES_SKILL_DIR" in (out / "hermes/demo/SKILL.md").read_text()


def test_check_reports_drift(src, tmp_path):
    out = tmp_path / "dist"
    build(src, out)
    assert check(src, out) == []
    (src / "demo/SKILL.md").write_text("changed\n")
    assert check(src, out) == ["claude/demo/SKILL.md", "hermes/demo/SKILL.md"]


def test_repo_dist_is_up_to_date():
    assert check(ROOT / "src", ROOT / "dist") == []


def test_folders_without_a_root_skill_md_are_left_alone(src, tmp_path):
    other = src / "bundle"
    (other / "hermes" / "part").mkdir(parents=True)
    (other / "hermes" / "part" / "SKILL.md").write_text("{{NOT_OURS}}\n")
    out = tmp_path / "dist"
    build(src, out)
    assert not (out / "hermes" / "bundle").exists()
    assert check(src, out) == []
