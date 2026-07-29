from datetime import datetime

import pytest

from stillhem.schedule import window_active, hhmm_to_min


# Reference dates (2026):
#   2026-07-27 is a Monday (weekday 0)
#   2026-07-31 is a Friday (weekday 4)
#   2026-08-01 is a Saturday (weekday 5)
#   2026-08-02 is a Sunday (weekday 6)

def _sched(days, start_min, end_min):
    return {"days": ",".join(str(d) for d in days), "start_min": start_min, "end_min": end_min}


# ── None / degenerate ────────────────────────────────────────────────────────

def test_none_schedule_never_active():
    assert window_active(None, datetime(2026, 7, 27, 12, 0)) is False


def test_start_equals_end_never_active():
    s = _sched([0], 600, 600)
    assert window_active(s, datetime(2026, 7, 27, 10, 0)) is False


def test_empty_days_never_active():
    s = _sched([], 540, 1320)
    assert window_active(s, datetime(2026, 7, 27, 12, 0)) is False


# ── same-day window (09:00-22:00) ─────────────────────────────────────────────

def test_same_day_inside_window():
    s = _sched([0], 540, 1320)  # Mon 09:00-22:00
    assert window_active(s, datetime(2026, 7, 27, 12, 0)) is True


def test_same_day_before_window():
    s = _sched([0], 540, 1320)
    assert window_active(s, datetime(2026, 7, 27, 8, 59)) is False


def test_same_day_after_window():
    s = _sched([0], 540, 1320)
    assert window_active(s, datetime(2026, 7, 27, 22, 0)) is False  # end excluded


def test_same_day_wrong_weekday():
    s = _sched([5, 6], 540, 1320)  # Sat/Sun only
    assert window_active(s, datetime(2026, 7, 27, 12, 0)) is False  # Monday


def test_same_day_at_start_boundary_inclusive():
    s = _sched([0], 540, 1320)
    assert window_active(s, datetime(2026, 7, 27, 9, 0)) is True


def test_same_day_end_minute_excluded():
    s = _sched([0], 540, 1320)
    assert window_active(s, datetime(2026, 7, 27, 21, 59)) is True
    assert window_active(s, datetime(2026, 7, 27, 22, 0)) is False


# ── midnight-crossing window (Fri 22:00 - 02:00), anchored to start day ────────

def test_midnight_cross_evening_portion_on_start_day():
    s = _sched([4], 1320, 120)  # Fri 22:00 - 02:00
    assert window_active(s, datetime(2026, 7, 31, 23, 0)) is True  # Fri 23:00


def test_midnight_cross_morning_portion_next_day():
    s = _sched([4], 1320, 120)  # Fri 22:00 - 02:00
    assert window_active(s, datetime(2026, 8, 1, 1, 0)) is True  # Sat 01:00


def test_midnight_cross_morning_portion_end_excluded():
    s = _sched([4], 1320, 120)
    assert window_active(s, datetime(2026, 8, 1, 2, 0)) is False  # Sat 02:00 excluded


def test_midnight_cross_saturday_evening_not_active():
    # Sat is not a listed start day, and Sat evening is not the morning-tail of Fri.
    s = _sched([4], 1320, 120)
    assert window_active(s, datetime(2026, 8, 1, 23, 0)) is False


def test_midnight_cross_start_day_before_start_not_active():
    s = _sched([4], 1320, 120)
    assert window_active(s, datetime(2026, 7, 31, 21, 59)) is False


# ── hhmm_to_min ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("s,expected", [
    ("00:00", 0),
    ("09:00", 540),
    ("22:00", 1320),
    ("23:59", 1439),
])
def testhhmm_to_min_valid(s, expected):
    assert hhmm_to_min(s) == expected


@pytest.mark.parametrize("s", ["", "9", "9:00:00", "24:00", "12:60", "ab:cd", "-1:00"])
def testhhmm_to_min_invalid(s):
    assert hhmm_to_min(s) is None
