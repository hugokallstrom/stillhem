"""Pure, I/O-free schedule logic for per-category weekly allow-windows.

The whole feature reduces to one question: is category C inside an allow-window
at instant `now`? `window_active` answers it with no clock and no DB access, so it
is trivially unit-testable with datetime literals.
"""
from datetime import datetime


def window_active(schedule: dict | None, now: datetime) -> bool:
    """True if `now` (local wall-clock datetime) is inside this category's
    allow-window.

    `schedule` is a row dict {days, start_min, end_min} or None. `days` is a CSV
    of `weekday()` ints (Mon=0..Sun=6); `start_min`/`end_min` are minutes since
    local midnight. The interval is half-open [start, end): the end minute is not
    itself allowed, so wrap-around windows never double-count the seam.

    Midnight-crossing windows (e.g. 22:00-02:00) are anchored to their START day:
    "allow Fri 22:00-02:00" covers Fri 22:00 -> Sat 02:00 even though Sat is not
    listed.

    DST: comparison is on naive wall-clock fields (weekday/hour/minute), so DST
    "just works" the intuitive way. A spring-forward gap simply never matches
    inside the skipped hour; a fall-back repeated hour matches across both
    occurrences. The change-detected 1-minute poll means at most one redundant
    recompute, never wrong blocking.
    """
    if schedule is None:
        return False
    days = {int(d) for d in schedule["days"].split(",") if d != ""}
    start, end = schedule["start_min"], schedule["end_min"]
    if start == end:  # zero-length -> never active (also rejected at the API edge)
        return False
    cur = now.hour * 60 + now.minute
    if start < end:  # same-day window, e.g. 09:00-22:00
        return now.weekday() in days and start <= cur < end
    # midnight-crossing, e.g. 22:00-02:00, anchored to its START day:
    return (now.weekday() in days and cur >= start) or \
           ((now.weekday() - 1) % 7 in days and cur < end)


def hhmm_to_min(s: str) -> int | None:
    """Parse "HH:MM" -> minutes since midnight, or None if malformed/out-of-range.

    The single HH:MM<->minutes converter, shared by the admin route and tests, so
    it is part of this module's public interface (no leading underscore).
    """
    parts = s.split(":")
    if len(parts) != 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m
