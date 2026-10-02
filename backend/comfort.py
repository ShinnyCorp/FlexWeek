"""Stage 5 timer presets, grid rounding and reminder-limit copy. No HTTP, no database."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

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


def snap_minutes(value: int, minimum: int, maximum: int) -> int:
    return flexweek_engine.snap_minutes_wide(value, minimum, maximum)


def split_plan(
    duration_min: int,
    work_min: int,
    break_min: int,
    long_break_min: int,
    cadence: int,
) -> dict[str, object]:
    return json.loads(
        flexweek_engine.split_plan(duration_min, work_min, break_min, long_break_min, cadence)
    )


def preview_split(
    *,
    duration_min: int | None,
    timer_work_min: int,
    timer_break_min: int,
    timer_long_break_min: int,
    timer_long_break_every: int,
) -> dict[str, object]:
    return json.loads(
        flexweek_engine.preview_split(
            duration_min,
            timer_work_min,
            timer_break_min,
            timer_long_break_min,
            timer_long_break_every,
        )
    )
