"""Week-date arithmetic. Imports no framework, like models.py."""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

FIRST_DAY = date(2000, 1, 1)
LAST_DAY = date(2099, 12, 31)
FIRST_WEEK_START = date(1999, 12, 27)
# date.fromisoformat also accepts "20260907" and "2026-W37-1"; a week label is
# always the padded calendar form, so the shape is pinned before parsing.
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# [0-9], not \d: date.fromisoformat guards ISO_DATE against Unicode digits, but
# parse_month feeds int() directly, which would accept them.
ISO_MONTH = re.compile(r"[0-9]{4}-[0-9]{2}")


def _parse(value: str) -> date:
    if not ISO_DATE.fullmatch(value):
        raise ValueError("date must be written YYYY-MM-DD")
    day = date.fromisoformat(value)
    if not FIRST_DAY <= day <= LAST_DAY:
        raise ValueError("date must be between 2000-01-01 and 2099-12-31")
    return day


def monday_of(date_str: str) -> str:
    """The Monday of the week holding date_str. Raises on a malformed or out-of-range date."""
    day = _parse(date_str)
    return (day - timedelta(days=day.weekday())).isoformat()


def current_week_start() -> str:
    """The Monday of the server's local today."""
    return monday_of(date.today().isoformat())


def is_week_start(value: str) -> bool:
    """True for an in-range Monday or the one week containing the lower date edge."""
    try:
        if not ISO_DATE.fullmatch(value):
            return False
        day = date.fromisoformat(value)
        return day.weekday() == 0 and (FIRST_DAY <= day <= LAST_DAY or day == FIRST_WEEK_START)
    except ValueError:
        return False


def is_calendar_date(value: str) -> bool:
    """True when value is a well-formed date in 2000-01-01..2099-12-31."""
    try:
        _parse(value)
        return True
    except ValueError:
        return False


def parse_month(value: str) -> tuple[date, date]:
    """First and last dates of YYYY-MM. Raises on a malformed or out-of-range month."""
    if not ISO_MONTH.fullmatch(value):
        raise ValueError("month must be written YYYY-MM")
    year = int(value[:4])
    month = int(value[5:7])
    if month < 1 or month > 12:
        raise ValueError("month must be written YYYY-MM")
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    if start < FIRST_DAY or start > LAST_DAY:
        raise ValueError("date must be between 2000-01-01 and 2099-12-31")
    return start, end


def is_month_label(value: str) -> bool:
    """True when value is a well-formed YYYY-MM whose first day is in range."""
    try:
        parse_month(value)
        return True
    except ValueError:
        return False


def month_grid(start: date, end: date) -> tuple[date, date]:
    """Monday of start through Sunday of end, clipped to FIRST_DAY..LAST_DAY."""
    grid_start = start - timedelta(days=start.weekday())
    grid_end = end + timedelta(days=6 - end.weekday())
    if grid_start < FIRST_DAY:
        grid_start = FIRST_DAY
    if grid_end > LAST_DAY:
        grid_end = LAST_DAY
    return grid_start, grid_end
