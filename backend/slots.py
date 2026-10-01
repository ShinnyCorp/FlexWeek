"""Quarter-hour grid. The engine does the work. These names stay."""

from __future__ import annotations

from flexweek_engine import (  # type: ignore[import-untyped]
    DAY_END_MIN,
    DAY_NAME_TO_INDEX,
    DAY_START_MIN,
    SLOT_MIN,
    SLOTS_PER_DAY,
    block_interval_on_day,
    clock_to_minutes,
    duration_to_slots,
    hhmm_to_minutes,
    hhmm_to_slot,
    minutes_to_hhmm,
    minutes_to_slot,
    occupancy_between,
    occupancy_mask,
    on_slot,
    overlaps,
    parse_deadline,
    slot_to_hhmm,
    span_fits_day,
    start_fits_day,
)

__all__ = [
    "DAY_END_MIN",
    "DAY_NAME_TO_INDEX",
    "DAY_START_MIN",
    "SLOT_MIN",
    "SLOTS_PER_DAY",
    "block_interval_on_day",
    "clock_to_minutes",
    "duration_to_slots",
    "hhmm_to_minutes",
    "hhmm_to_slot",
    "minutes_to_hhmm",
    "minutes_to_slot",
    "occupancy_between",
    "occupancy_mask",
    "on_slot",
    "overlaps",
    "parse_deadline",
    "slot_to_hhmm",
    "span_fits_day",
    "start_fits_day",
]
