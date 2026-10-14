"""Errors the agent reads. Every code comes with an exit code and the next step to take."""

USAGE, BUSINESS, STORAGE = 1, 2, 3

ACTIONS: dict[str, tuple[int, str]] = {
    "bad_arguments": (USAGE, "fix the command using the usage in SKILL.md"),
    "bad_date": (USAGE, "use YYYY-MM-DD, today, or yesterday"),
    "bad_time": (USAGE, 'use "YYYY-MM-DD HH:MM" in the configured timezone'),
    "bad_schedule": (USAGE, "use daily, none, interval:N (1-365), or weekly: plus days such as weekly:wed,sat"),
    "bad_window": (USAGE, "use --window -E,+L with whole days from 0 to 6, e.g. -1,+2"),
    "bad_setting": (USAGE, "day-boundary takes HH:MM; timezone takes an IANA name such as Asia/Taipei or America/New_York"),
    "internal_error": (USAGE, "tell the user routine-keeper hit an unexpected problem and nothing was saved; if it keeps happening, report it at https://github.com/SmallYuanSY/skills/issues"),
    "unknown_item": (BUSINESS, "retry with an exact name from the list above; if none fits, ask the user, then add the item or an alias (see routine-setup)"),
    "unknown_alias": (BUSINESS, "check the item's aliases with: item list"),
    "name_taken": (BUSINESS, "pick another name, or edit the item that already uses it"),
    "item_paused": (BUSINESS, "the item is paused; ask the user whether to resume it with: item resume <name>"),
    "future_time": (BUSINESS, "only log what the user says already happened; never log ahead of time"),
    "already_logged": (BUSINESS, "tell the user it is already logged for that day; add --force only if they confirm it really happened twice"),
    "skip_not_applicable": (BUSINESS, "skip only works for daily and weekly items"),
    "not_scheduled": (BUSINESS, "skip a day the item is scheduled on; check with: time <date>"),
    "unknown_log": (BUSINESS, "find the id with: log list"),
    "unknown_note": (BUSINESS, "find the id with: note list"),
    "target_exists": (BUSINESS, "ask the user whether to switch to the data already there (--use-existing) or replace it (--overwrite)"),
    "data_unavailable": (STORAGE, "nothing was saved; tell the user the data folder cannot be used and show them the path from: data where"),
    "data_version_newer": (STORAGE, "this data was written by a newer routine-keeper; ask the user to update the skill"),
    "move_verify_failed": (STORAGE, "nothing changed and the data stays where it was; tell the user the move failed"),
}


class RkError(Exception):
    def __init__(self, code: str, detail: str = ""):
        if code not in ACTIONS:
            raise ValueError(f"unknown error code: {code}")
        super().__init__(code)
        self.code = code
        self.detail = detail

    @property
    def exit_code(self) -> int:
        return ACTIONS[self.code][0]


def render_error(err: RkError) -> str:
    head = f"error: {err.code}" + (f" ({err.detail})" if err.detail else "")
    return f"{head}\naction: {ACTIONS[err.code][1]}"


def error_data(err: RkError) -> dict:
    return {"error": err.code, "detail": err.detail, "action": ACTIONS[err.code][1]}
