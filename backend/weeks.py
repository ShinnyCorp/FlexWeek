"""Week-date arithmetic. The engine does the work. These names stay."""

from __future__ import annotations

import re
from datetime import date

from flexweek_engine import (  # type: ignore[import-untyped]
    current_week_start,
    is_calendar_date,
    is_month_label,
    is_week_start,
    monday_of,
    month_grid,
    parse_month,
)

FIRST_DAY = date(2000, 1, 1)
LAST_DAY = date(2099, 12, 31)
FIRST_WEEK_START = date(1999, 12, 27)
# date.fromisoformat also accepts "20260907" and "2026-W37-1"; a week label is
# always the padded calendar form, so the shape is pinned before parsing.
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# [0-9], not \d: date.fromisoformat guards ISO_DATE against Unicode digits, but
# parse_month feeds int() directly, which would accept them.
ISO_MONTH = re.compile(r"[0-9]{4}-[0-9]{2}")

__all__ = [
    "FIRST_DAY",
    "FIRST_WEEK_START",
    "ISO_DATE",
    "ISO_MONTH",
    "LAST_DAY",
    "current_week_start",
    "is_calendar_date",
    "is_month_label",
    "is_week_start",
    "monday_of",
    "month_grid",
    "parse_month",
]
