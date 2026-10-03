"""Stage 4 occupancy, lateness and project-spread planning. No HTTP, no database."""

from __future__ import annotations

from datetime import date, timedelta

from backend.tests.engine_ref.assignments import unplanned_minutes
from backend.tests.engine_ref.models import GridWindow, ProtectedWindow, StudyWindow, WorkWindow, parse_due
from backend.tests.engine_ref.slots import DAY_END_MIN, SLOT_MIN, clock_to_minutes, occupancy_between
from backend.tests.engine_ref.weeks import monday_of

DEFAULT_WORK_WINDOWS = [
    WorkWindow(days=[0, 1, 2, 3, 4, 5, 6], start="00:00", end="24:00"),
]
LEGACY_WORK_WINDOWS = [
    WorkWindow(days=[0, 1, 2, 3, 4, 5, 6], start="06:00", end="23:00"),
]

LATE_COPY = "Moved after you ran late so the rest of the day still fits."
CLUSTER_COPY = (
    "Several tasks are short on time. Shorten a session, pick another day, "
    "or free some protected hours. Work that cannot fit stays unplaced."
)


def add_occupancy(occ: list[int], day: int, start_min: int, end_min: int) -> None:
    occ[day] |= occupancy_between(start_min, end_min)


def occupancy_from_windows(
    protected: list[ProtectedWindow] | list[GridWindow],
    day_cutoff: str | None,
) -> list[int]:
    occ = [0] * 7
    for window in protected:
        hour, minute = map(int, window.start.split(":"))
        start = hour * 60 + minute
        for day in window.days:
            add_occupancy(occ, day, start, start + window.duration_min)
    if day_cutoff:
        hour, minute = map(int, day_cutoff.split(":"))
        cutoff = hour * 60 + minute
        for day in range(7):
            add_occupancy(occ, day, cutoff, DAY_END_MIN)
    return occ


def lateness_occupancy(day: int, from_start: str, minutes: int) -> list[int]:
    occ = [0] * 7
    hour, minute = map(int, from_start.split(":"))
    start = hour * 60 + minute
    add_occupancy(occ, day, start, start + minutes)
    return occ


def study_rank(
    windows: list[StudyWindow], course: str | None, day: int, start_min: int, duration_min: int
) -> int:
    """How much a session wants this time: 0 inside a window for its own subject, 1 inside a window for
    any subject, 2 anywhere else. Another subject's window is anywhere else, so Reading does not take
    the time kept for Math."""
    wanted = course.strip().casefold() if course and course.strip() else None
    best = 2
    for window in windows:
        if day not in window.days:
            continue
        hour, minute = map(int, window.start.split(":"))
        begin = hour * 60 + minute
        # The whole session must fit inside the window, not just its start.
        if not (begin <= start_min and start_min + duration_min <= begin + window.duration_min):
            continue
        if window.subject is None:
            best = min(best, 1)
        elif wanted is not None and window.subject.casefold() == wanted:
            return 0
    return best


def resolve_work_windows(windows: list[WorkWindow] | None) -> tuple[list[WorkWindow], bool]:
    if windows:
        return list(windows), False
    return [window.model_copy() for window in DEFAULT_WORK_WINDOWS], True


def _merged_work_spans(
    windows: list[WorkWindow], course: str | None, day: int
) -> list[tuple[int, int]]:
    """One day's applicable windows, merged where they touch or overlap."""
    wanted = course.strip().casefold() if course and course.strip() else None
    spans: list[tuple[int, int]] = []
    for window in windows:
        if day not in window.days:
            continue
        if window.subject is not None and (wanted is None or window.subject.casefold() != wanted):
            continue
        begin = clock_to_minutes(window.start)
        finish = clock_to_minutes(window.end)
        if begin < finish:
            spans.append((begin, finish))
    if not spans:
        return []
    spans.sort()
    merged = [spans[0]]
    for begin, finish in spans[1:]:
        last_begin, last_finish = merged[-1]
        if begin <= last_finish:
            merged[-1] = (last_begin, max(last_finish, finish))
        else:
            merged.append((begin, finish))
    return merged


def session_inside_work_windows(
    windows: list[WorkWindow], course: str | None, day: int, start_min: int, duration_min: int
) -> bool:
    """True when the whole session sits inside the day's merged applicable windows."""
    end_min = start_min + duration_min
    return any(
        begin <= start_min and end_min <= finish
        for begin, finish in _merged_work_spans(windows, course, day)
    )


def merge_occupancy(base: list[int], extra: list[int]) -> list[int]:
    return [left | right for left, right in zip(base, extra, strict=True)]


def spread_sessions(
    *,
    estimate_min: int,
    focus_minutes: int,
    planned_min: int,
    due: str,
    session_min: int,
    from_date: str,
) -> tuple[list[dict[str, object]], int]:
    remaining = unplanned_minutes(estimate_min, focus_minutes, planned_min)
    # Sessions stay on the grid; the sub-15-minute remainder is unschedulable,
    # not zero, and comes back in remaining_min instead of being dropped.
    remainder = remaining % SLOT_MIN
    grid_total = remaining - remainder
    due_day, _ = parse_due(due)
    start = date.fromisoformat(from_date)
    if remaining == 0 or start > due_day:
        return [], remaining
    dates: list[date] = []
    cursor = start
    while cursor <= due_day:
        dates.append(cursor)
        cursor += timedelta(days=1)
    sizes: list[int] = []
    left = grid_total
    while left >= session_min:
        sizes.append(session_min)
        left -= session_min
    if left:
        sizes.append(left)
    sessions: list[dict[str, object]] = []
    for index, duration in enumerate(sizes):
        day = dates[index % len(dates)]
        sessions.append(
            {
                "week_start": monday_of(day.isoformat()),
                "date": day.isoformat(),
                "days": [day.weekday()],
                "duration_min": duration,
            }
        )
    return sessions, remainder
