"""Nothing on the local deny-list may appear in any file that could be published."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / "tests" / "private-terms.local.txt"
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache"}
SKIP_FILES = {LOCAL.name, "private-terms.example.txt"}


def terms() -> list[str]:
    lines = LOCAL.read_text(encoding="utf-8").splitlines()
    return [t.strip().lower() for t in lines if t.strip() and not t.startswith("#")]


def publishable_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not SKIP_DIRS & set(p.relative_to(ROOT).parts) and p.name not in SKIP_FILES:
            yield p


@pytest.mark.skipif(not LOCAL.exists(), reason="no local deny-list (e.g. in CI)")
def test_no_private_terms_anywhere():
    banned = terms()
    assert banned, "the deny-list is empty"
    hits = []
    for p in publishable_files():
        try:
            text = p.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError:
            continue
        hits += [f"{p.relative_to(ROOT)} (term #{i + 1})" for i, t in enumerate(banned) if t in text]
    assert not hits, f"private terms found in: {hits}"
