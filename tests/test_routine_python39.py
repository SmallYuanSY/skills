"""routine-keeper runs on Python 3.9, the python3 that ships with macOS."""
import ast
import shutil
import subprocess
from pathlib import Path

import pytest

import routine

SCRIPTS = Path(__file__).resolve().parent.parent / "src" / "routine-keeper" / "scripts"


def _uses_union_annotations(tree) -> bool:
    annotations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs + [node.args.vararg, node.args.kwarg]
            annotations += [a.annotation for a in args if a is not None and a.annotation is not None]
            annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
    return any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)
               for a in annotations if a is not None for n in ast.walk(a))


def _has_future_annotations(tree) -> bool:
    return any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and
               any(alias.name == "annotations" for alias in n.names) for n in tree.body)


@pytest.mark.parametrize("path", sorted(SCRIPTS.rglob("*.py")), ids=lambda p: p.name)
def test_union_annotations_are_postponed(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if _uses_union_annotations(tree):
        assert _has_future_annotations(tree), f"{path.name}: add `from __future__ import annotations` for Python 3.9"


def _python39():
    for cand in ("python3.9", "/usr/bin/python3"):
        exe = shutil.which(cand)
        if exe and subprocess.run([exe, "-c", "import sys; sys.exit(sys.version_info[:2] != (3, 9))"]).returncode == 0:
            return exe
    return None


@pytest.mark.skipif(_python39() is None, reason="no Python 3.9 on this machine")
def test_cli_runs_on_python39(tmp_path):
    skill = tmp_path / "routine-keeper"
    shutil.copytree(SCRIPTS, skill / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    cli = [_python39(), "-B", str(skill / "scripts" / "routine.py")]
    out = subprocess.run(cli + ["item", "add", "--kind", "dose", "--name", "Vitamin D"],
                         capture_output=True, text=True)
    assert (out.returncode, out.stderr) == (0, "")
    assert out.stdout.startswith("ok: added Vitamin D (dose)")
    out = subprocess.run(cli + ["time", "today"], capture_output=True, text=True)
    assert out.returncode == 0 and "- Vitamin D [daily]: not_done" in out.stdout


def test_older_python_gets_an_error_not_a_traceback():
    assert routine.python_problem((3, 8)) == (
        "error: python_too_old (Python 3.8; routine-keeper needs 3.9 or newer)\n"
        "action: tell the user routine-keeper needs Python 3.9 or newer; nothing was saved")
    assert routine.python_problem((3, 9)) is None
