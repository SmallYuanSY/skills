"""Shared bits for the routine-keeper tests. Import the fixture by name: from rk_helpers import root."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

import routine

TPE = ZoneInfo("Asia/Taipei")
# 2026-10-14 08:20 UTC = 2026-10-14 16:20 Wed in Taipei
NOW = datetime(2026, 10, 14, 8, 20, tzinfo=timezone.utc)


def at_tpe(text: str) -> datetime:
    """'2026-10-14 16:20' in Taipei, as an aware UTC datetime for main(now=...)."""
    return datetime.fromisoformat(text).replace(tzinfo=TPE).astimezone(timezone.utc)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "routine-keeper"
    r.mkdir()
    return r


def run(root, capsys, *argv, now=NOW):
    code = routine.main(list(argv), now=now, root=root, default_tz="Asia/Taipei")
    return code, capsys.readouterr().out.strip()
