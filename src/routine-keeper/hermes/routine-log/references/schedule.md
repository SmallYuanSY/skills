# How scheduled days are matched

Read this when a `schedule:` line or a `time` status needs explaining.

- `daily`: done or not done each day. A dose can be logged once per day.
- `none`: nothing is due; only the last time is shown.
- `interval:N`: due N days after the last time it was done. Doing it early or late only moves the next due date; nothing piles up. `done` says how many days before or after the plan it was.
- `weekly:wed,sat`: each scheduled day has a window (default 1 day early, 2 days late).
  - A completion counts for the earliest open scheduled day whose window holds it, so making up a past day comes before doing the next one early.
  - It also settles every other open scheduled day before it ("merged"): doing it once clears what was missed.
  - Outside every window, it only settles earlier missed days; with none it is "extra" and changes nothing.
  - Days the user skipped on purpose (`skip`) are never counted as missed or merged.
- The day a record counts for comes from the day boundary (default 05:00) unless `--for` names the day.
- Changing an item's schedule or window judges the new rule from that day on.
