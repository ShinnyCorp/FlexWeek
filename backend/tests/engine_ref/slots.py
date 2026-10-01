from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.tests.engine_ref.models import TimeBlock

SLOT_MIN = 15
DAY_START_MIN = 0
DAY_END_MIN = 24 * 60
SLOTS_PER_DAY = (DAY_END_MIN - DAY_START_MIN) // SLOT_MIN

DAY_NAME_TO_INDEX = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def hhmm_to_minutes(hhmm: str) -> int:
    parts = hhmm.split(":")
    if len(parts) != 2:
        raise ValueError(f"expected HH:MM, got {hhmm!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"invalid time {hhmm!r}")
    return hour * 60 + minute


def clock_to_minutes(hhmm: str) -> int:
    """Minutes from midnight, including 24:00 as the exclusive end of the day."""
    if hhmm == "24:00":
        return DAY_END_MIN
    return hhmm_to_minutes(hhmm)


def minutes_to_hhmm(minutes: int) -> str:
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def start_fits_day(start_min: int) -> bool:
    return DAY_START_MIN <= start_min < DAY_END_MIN


def span_fits_day(start_min: int, duration_min: int) -> bool:
    return duration_min > 0 and start_fits_day(start_min) and start_min + duration_min <= DAY_END_MIN


def on_slot(minutes: int) -> bool:
    """Whether a time or a length is on the planner's quarter hours. A block may be any minute;
    homework estimates and the windows the planner works in may not."""
    return minutes % SLOT_MIN == 0


def minutes_to_slot(minutes: int) -> int:
    # Grid is half-open [00:00, 24:00); 24:00 is the end of the last slot, not a start.
    if minutes < DAY_START_MIN or minutes >= DAY_END_MIN:
        raise ValueError("time is outside 00:00–24:00")
    offset = minutes - DAY_START_MIN
    if offset % SLOT_MIN:
        raise ValueError("time must land on a 15-minute slot")
    return offset // SLOT_MIN


def hhmm_to_slot(hhmm: str) -> int:
    return minutes_to_slot(hhmm_to_minutes(hhmm))


def slot_to_hhmm(slot: int) -> str:
    if slot < 0 or slot >= SLOTS_PER_DAY:
        raise ValueError("slot out of range")
    return minutes_to_hhmm(DAY_START_MIN + slot * SLOT_MIN)


def duration_to_slots(duration_min: int) -> int:
    """The quarter hours a length takes from a quarter-hour start: 50 minutes takes four."""
    if duration_min <= 0:
        raise ValueError("duration must be positive")
    return -(-duration_min // SLOT_MIN)


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def block_interval_on_day(block: TimeBlock, day: int) -> tuple[int, int] | None:
    if day not in block.days or block.start is None:
        return None
    start = hhmm_to_minutes(block.start)
    end = start + block.duration_min
    return start, end


def parse_deadline(latest: str | None, days: list[int]) -> tuple[int, int] | None:
    """Turn a Phase-1 English deadline into (day_index, minutes_from_midnight).

    Accepts "Thursday 21:00", "21:00" (last allowed day), or a leftover
    "YYYY-MM-DDTHH:MM" timestamp (time only; day falls back to last of `days`).
    """
    if latest is None:
        return None
    text = latest.strip()
    if not text:
        return None
    # ISO leftover "YYYY-MM-DDTHH:MM" — do not split weekday names that contain T.
    if text[0].isdigit() and "T" in text:
        text = text.split("T", 1)[1]
    parts = text.replace(",", " ").split()
    time_part = parts[-1]
    day = max(days) if days else 0
    if len(parts) >= 2:
        name = parts[0].lower()
        if name in DAY_NAME_TO_INDEX:
            day = DAY_NAME_TO_INDEX[name]
    return day, hhmm_to_minutes(time_part)


def occupancy_mask(start_slot: int, n_slots: int) -> int:
    if n_slots <= 0 or start_slot < 0 or start_slot + n_slots > SLOTS_PER_DAY:
        raise ValueError("occupancy range is outside the 00:00–24:00 grid")
    return ((1 << n_slots) - 1) << start_slot


def occupancy_between(start_min: int, end_min: int) -> int:
    """Every quarter hour a span touches, cut to the day: 17:37 to 18:22 takes 17:30 to 18:30, so the
    planner never puts homework over the part of a quarter hour a block has."""
    start_min = max(start_min, DAY_START_MIN)
    end_min = min(end_min, DAY_END_MIN)
    if end_min <= start_min:
        return 0
    first = (start_min - DAY_START_MIN) // SLOT_MIN
    last = -(-(end_min - DAY_START_MIN) // SLOT_MIN)
    return occupancy_mask(first, last - first)
