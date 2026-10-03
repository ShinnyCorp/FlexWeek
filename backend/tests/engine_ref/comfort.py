"""Stage 5 timer presets, grid rounding and reminder-limit copy. No HTTP, no database."""

from __future__ import annotations

from typing import TypedDict

from backend.tests.engine_ref.slots import SLOT_MIN

TIMER_PRESETS = (
    {
        "id": "short",
        "label": "Short",
        "timer_work_min": 15,
        "timer_break_min": 15,
        "timer_long_break_min": 30,
        "timer_long_break_every": 4,
    },
    {
        "id": "standard",
        "label": "Standard",
        "timer_work_min": 30,
        "timer_break_min": 15,
        "timer_long_break_min": 30,
        "timer_long_break_every": 4,
    },
    {
        "id": "long",
        "label": "Long",
        "timer_work_min": 45,
        "timer_break_min": 15,
        "timer_long_break_min": 30,
        "timer_long_break_every": 4,
    },
)

REMINDER_LIMITS = {
    "web_open": "Reminders fire in this browser only while FlexWeek is open in a tab.",
    "desktop_background": "The desktop app can still alert from the tray after the window is closed.",
    "spotify": "A Spotify link is best-effort. FlexWeek plays a built-in sound if the track does not play.",
    "duplicate": "The same block start fires at most one reminder until it is handled or the day changes.",
}

_FIELD_LABEL = {
    "timer_work_min": "Work length",
    "timer_break_min": "Break length",
    "timer_long_break_min": "Long break",
}


class Segment(TypedDict):
    role: str
    duration_min: int
    index: int


def snap_minutes(value: int, minimum: int, maximum: int) -> int:
    snapped = int(round(value / SLOT_MIN) * SLOT_MIN)
    if snapped < minimum:
        snapped = minimum + ((SLOT_MIN - minimum % SLOT_MIN) % SLOT_MIN)
    if snapped > maximum:
        snapped = maximum - (maximum % SLOT_MIN)
    if snapped < SLOT_MIN:
        snapped = SLOT_MIN
    return snapped


def split_plan(
    duration_min: int,
    work_min: int,
    break_min: int,
    long_break_min: int,
    cadence: int,
) -> dict[str, object]:
    remaining = duration_min
    work_index = 0
    segments: list[Segment] = []
    while remaining > 0:
        work_index += 1
        length = min(work_min, remaining)
        segments.append({"role": "work", "duration_min": length, "index": work_index})
        remaining -= length
        if remaining > 0:
            long = work_index % cadence == 0
            segments.append(
                {
                    "role": "break",
                    "duration_min": long_break_min if long else break_min,
                    "index": work_index,
                }
            )
    return {
        "segments": segments,
        "total_min": sum(item["duration_min"] for item in segments),
    }


def preview_split(
    *,
    duration_min: int | None,
    timer_work_min: int,
    timer_break_min: int,
    timer_long_break_min: int,
    timer_long_break_every: int,
) -> dict[str, object]:
    snapped = {
        "timer_work_min": snap_minutes(timer_work_min, 1, 180),
        "timer_break_min": snap_minutes(timer_break_min, 1, 60),
        "timer_long_break_min": snap_minutes(timer_long_break_min, 1, 120),
        "timer_long_break_every": timer_long_break_every,
    }
    original = {
        "timer_work_min": timer_work_min,
        "timer_break_min": timer_break_min,
        "timer_long_break_min": timer_long_break_min,
    }
    parts = [
        f"{_FIELD_LABEL[key]} {original[key]} minutes becomes {snapped[key]} on the 15-minute grid."
        for key in original
        if original[key] != snapped[key]
    ]
    plan: dict[str, object] = {"segments": [], "total_min": 0}
    if duration_min is not None:
        plan = split_plan(
            duration_min,
            int(snapped["timer_work_min"]),
            int(snapped["timer_break_min"]),
            int(snapped["timer_long_break_min"]),
            timer_long_break_every,
        )
    return {
        **snapped,
        "rounded": bool(parts),
        "message": " ".join(parts) if parts else "",
        **plan,
    }
