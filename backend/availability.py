"""Stage 4 occupancy, lateness and project-spread planning. No HTTP, no database."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import GridWindow, ProtectedWindow, StudyWindow, WorkWindow

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
    occ[:] = flexweek_engine.add_occupancy(occ, day, start_min, end_min)


def occupancy_from_windows(
    protected: list[ProtectedWindow] | list[GridWindow],
    day_cutoff: str | None,
) -> list[int]:
    return list(
        flexweek_engine.occupancy_from_windows(
            json.dumps([window.model_dump() for window in protected]),
            day_cutoff,
        )
    )


def lateness_occupancy(day: int, from_start: str, minutes: int) -> list[int]:
    return list(flexweek_engine.lateness_occupancy(day, from_start, minutes))


def study_rank(
    windows: list[WorkWindow], course: str | None, day: int, start_min: int, duration_min: int
) -> int:
    """How much a session wants this time in its Study hours: 0 inside a window for its own subject, 1
    inside a window for any subject, 2 anywhere else. Another subject's window is anywhere else, so
    Reading does not take the time kept for Math."""
    return flexweek_engine.study_rank(
        json.dumps([window.model_dump() for window in windows]),
        course,
        day,
        start_min,
        duration_min,
    )


def fold_study_windows(work: list[WorkWindow], study: list[StudyWindow]) -> list[dict]:
    """Preferred study hours from before the one list, joined to Study hours (J7)."""
    return json.loads(
        flexweek_engine.fold_study_windows(
            json.dumps([window.model_dump() for window in work]),
            json.dumps([window.model_dump() for window in study]),
        )
    )


def resolve_work_windows(windows: list[WorkWindow] | None) -> tuple[list[WorkWindow], bool]:
    raw, defaulted = flexweek_engine.resolve_work_windows(
        None if windows is None else json.dumps([window.model_dump() for window in windows])
    )
    return [WorkWindow.model_validate(item) for item in json.loads(raw)], defaulted


def session_inside_work_windows(
    windows: list[WorkWindow], course: str | None, day: int, start_min: int, duration_min: int
) -> bool:
    """True when the whole session sits inside the day's merged applicable windows."""
    return flexweek_engine.session_inside_work_windows(
        json.dumps([window.model_dump() for window in windows]),
        course,
        day,
        start_min,
        duration_min,
    )


def merge_occupancy(base: list[int], extra: list[int]) -> list[int]:
    return list(flexweek_engine.merge_occupancy(base, extra))


def spread_sessions(
    *,
    estimate_min: int,
    focus_minutes: int,
    planned_min: int,
    due: str,
    session_min: int,
    from_date: str,
) -> tuple[list[dict[str, object]], int]:
    sessions, remaining = flexweek_engine.spread_sessions(
        estimate_min,
        focus_minutes,
        planned_min,
        due,
        session_min,
        from_date,
    )
    return json.loads(sessions), remaining
