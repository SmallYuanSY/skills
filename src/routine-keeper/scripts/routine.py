#!/usr/bin/env python3
# routine-keeper · Copyright (c) 2026 SmallYuan · MIT License · https://github.com/SmallYuanSY/skills
"""Chores and supplements for an agent to log and check. Output is written for the agent to read.

  routine.py item add|edit|pause|resume|list
  routine.py done | skip | time
  routine.py log list|edit|delete|restore
  routine.py note add|list|resolve
  routine.py config show|set
  routine.py data where|move
  routine.py export
  global: --json, --version
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def python_problem(version):
    """Checked before routine_core is imported, so an old Python gets error/action lines, not a traceback."""
    if tuple(version[:2]) >= (3, 9):
        return None
    found = f"{version[0]}.{version[1]}"
    return (f"error: python_too_old (Python {found}; routine-keeper needs 3.9 or newer)\n"
            "action: tell the user routine-keeper needs Python 3.9 or newer; nothing was saved")


if __name__ == "__main__" and python_problem(sys.version_info):
    print(python_problem(sys.version_info))
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routine_core import REPO, VERSION, cmd_admin, cmd_items, cmd_logs, cmd_time, storage  # noqa: E402
from routine_core.context import Ctx, Result  # noqa: E402
from routine_core.dates import system_timezone  # noqa: E402
from routine_core.errors import RkError, error_data, render_error  # noqa: E402

VERSION_LINE = f"routine-keeper {VERSION} · by SmallYuan · {REPO}"


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RkError("bad_arguments", message)


def build_parser() -> Parser:
    p = Parser(prog="routine.py")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)

    item = sub.add_parser("item").add_subparsers(dest="sub", required=True, parser_class=Parser)
    add = item.add_parser("add")
    add.add_argument("--kind", required=True, choices=["chore", "dose"])
    add.add_argument("--name", required=True)
    add.add_argument("--schedule")
    add.add_argument("--window")
    add.add_argument("--slot")
    add.add_argument("--alias", action="append", default=[])
    edit = item.add_parser("edit")
    edit.add_argument("item")
    edit.add_argument("--name")
    edit.add_argument("--schedule")
    edit.add_argument("--window")
    edit.add_argument("--slot")
    edit.add_argument("--alias", action="append", default=[])
    edit.add_argument("--remove-alias", action="append", default=[])
    for name in ("pause", "resume"):
        item.add_parser(name).add_argument("item")
    lst = item.add_parser("list")
    lst.add_argument("--kind", choices=["chore", "dose"])
    lst.add_argument("--all", action="store_true")

    d = sub.add_parser("done")
    d.add_argument("item")
    d.add_argument("--at")
    d.add_argument("--for", dest="for_day")
    d.add_argument("--note")
    d.add_argument("--keep-notes", action="store_true")
    d.add_argument("--force", action="store_true")

    s = sub.add_parser("skip")
    s.add_argument("item")
    s.add_argument("--for", dest="for_day", required=True)
    s.add_argument("--reason")
    s.add_argument("--undo", action="store_true")

    sub.add_parser("time").add_argument("day")

    log = sub.add_parser("log").add_subparsers(dest="sub", required=True, parser_class=Parser)
    ll = log.add_parser("list")
    ll.add_argument("--item")
    ll.add_argument("--from", dest="start")
    ll.add_argument("--to", dest="end")
    ll.add_argument("--limit", type=int, default=50)
    le = log.add_parser("edit")
    le.add_argument("id", type=int)
    le.add_argument("--at")
    le.add_argument("--for", dest="for_day")
    le.add_argument("--note")
    le.add_argument("--force", action="store_true")
    log.add_parser("delete").add_argument("id", type=int)
    lr = log.add_parser("restore")
    lr.add_argument("id", type=int)
    lr.add_argument("--force", action="store_true")

    note = sub.add_parser("note").add_subparsers(dest="sub", required=True, parser_class=Parser)
    na = note.add_parser("add")
    na.add_argument("item")
    na.add_argument("text")
    note.add_parser("list")
    note.add_parser("resolve").add_argument("id", type=int)

    config = sub.add_parser("config").add_subparsers(dest="sub", required=True, parser_class=Parser)
    config.add_parser("show")
    cset = config.add_parser("set")
    cset.add_argument("key", choices=["day-boundary", "timezone"])
    cset.add_argument("value")
    data = sub.add_parser("data").add_subparsers(dest="sub", required=True, parser_class=Parser)
    data.add_parser("where")
    move = data.add_parser("move")
    move.add_argument("--to", required=True)
    how = move.add_mutually_exclusive_group()
    how.add_argument("--use-existing", action="store_true")
    how.add_argument("--overwrite", action="store_true")

    sub.add_parser("export").add_argument("--file")
    return p


HANDLERS = {
    ("item", "add"): cmd_items.item_add,
    ("item", "edit"): cmd_items.item_edit,
    ("item", "pause"): cmd_items.item_pause,
    ("item", "resume"): cmd_items.item_resume,
    ("item", "list"): cmd_items.item_list,
    ("done", None): cmd_logs.done,
    ("skip", None): cmd_logs.skip,
    ("log", "list"): cmd_logs.log_list,
    ("log", "edit"): cmd_logs.log_edit,
    ("log", "delete"): cmd_logs.log_delete,
    ("log", "restore"): cmd_logs.log_restore,
    ("note", "add"): cmd_logs.note_add,
    ("note", "list"): cmd_logs.note_list,
    ("note", "resolve"): cmd_logs.note_resolve,
    ("time", None): cmd_time.time_day,
    ("export", None): cmd_admin.export,
    ("config", "show"): cmd_admin.config_show,
    ("config", "set"): cmd_admin.config_set,
}


def _handler(args):
    """Looked up at call time so tests can patch a command module."""
    fn = HANDLERS[(args.cmd, getattr(args, "sub", None))]
    return getattr(sys.modules[fn.__module__], fn.__name__)


def _print(result: Result, as_json: bool) -> None:
    print(json.dumps(result.data, ensure_ascii=False, indent=2) if as_json else "\n".join(result.lines))


def _print_error(err: RkError, as_json: bool) -> None:
    print(json.dumps(error_data(err), ensure_ascii=False, indent=2) if as_json else render_error(err))


def _join_window(argv: list[str]) -> list[str]:
    """argparse reads "-1,+2" as an option; glue it to --window so "--window -1,+2" works."""
    out, i = [], 0
    while i < len(argv):
        if argv[i] == "--window" and i + 1 < len(argv):
            out.append(f"--window={argv[i + 1]}")
            i += 2
        else:
            out.append(argv[i])
            i += 1
    return out


def main(argv=None, *, now=None, root=None, default_tz=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    as_json = "--json" in argv
    argv = _join_window([x for x in argv if x != "--json"])
    root = Path(root) if root else storage.SKILL_ROOT
    now = now or datetime.now(timezone.utc)
    conn = None
    try:
        if argv == ["--version"]:
            result = Result([VERSION_LINE], {"version": VERSION})
        else:
            args = build_parser().parse_args(argv)
            if args.cmd == "data":
                result = cmd_admin.data_command(args, root=root, now=now, default_tz=default_tz or system_timezone())
            else:
                conn = storage.open_db(root, default_tz or system_timezone())
                result = _handler(args)(Ctx.build(conn, root, now), args)
                conn.commit()
    except SystemExit as e:   # --help printed its text
        return e.code if isinstance(e.code, int) else 0
    except RkError as e:
        _print_error(e, as_json)
        return e.exit_code
    except Exception as e:   # never show the agent a traceback
        _print_error(RkError("internal_error", type(e).__name__), as_json)
        return 1
    finally:
        if conn is not None:
            conn.rollback()   # no-op after a commit; drops half-done writes after an error
            conn.close()
    _print(result, as_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
