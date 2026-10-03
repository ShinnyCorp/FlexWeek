"""Place flexible blocks around locked ones. The search runs in the engine."""

from __future__ import annotations

import json
import time

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import SolveTrace, StudyWindow, TimeBlock, WorkWindow

SOLVE_BUDGET_MS = 150


def _clock():
    started = time.perf_counter()

    def elapsed() -> float:
        return (time.perf_counter() - started) * 1000

    return elapsed


def _points(points: dict | None) -> str | None:
    if points is None:
        return None
    return json.dumps(
        {key: None if value is None else [value[0], value[1]] for key, value in points.items()}
    )


def _windows(windows: list | None) -> str | None:
    if windows is None:
        return None
    return json.dumps([window.model_dump() for window in windows])


def _blocks(blocks: list[TimeBlock]) -> str:
    return json.dumps([block.model_dump() for block in blocks])


def solve(
    blocks: list[TimeBlock],
    *,
    deadlines: dict[str, tuple[int, int] | None] | None = None,
    slack_deadlines: dict[str, tuple[int, int]] | None = None,
    extra_occ: list[int] | None = None,
    study_windows: list[StudyWindow] | None = None,
    work_windows: list[WorkWindow] | None = None,
) -> SolveTrace:
    """Place flexible blocks around locked ones. Pure and synchronous."""
    raw = flexweek_engine.solve(
        _blocks(blocks),
        _points(deadlines),
        _points(slack_deadlines),
        extra_occ,
        _windows(study_windows),
        _windows(work_windows),
        _clock(),
    )
    return SolveTrace.model_validate(json.loads(raw))


def reschedule_after_miss(
    blocks: list[TimeBlock],
    missed_block_id: str,
    missed_day: int,
    previous_placed: list[TimeBlock],
    *,
    deadlines: dict[str, tuple[int, int] | None] | None = None,
    slack_deadlines: dict[str, tuple[int, int]] | None = None,
    extra_occ: list[int] | None = None,
    study_windows: list[StudyWindow] | None = None,
    work_windows: list[WorkWindow] | None = None,
) -> SolveTrace:
    """Mark one locked occurrence missed, solve again, and describe changed flexible placements."""
    raw = flexweek_engine.reschedule_after_miss(
        _blocks(blocks),
        missed_block_id,
        missed_day,
        _blocks(previous_placed),
        _points(deadlines),
        _points(slack_deadlines),
        extra_occ,
        _windows(study_windows),
        _windows(work_windows),
        _clock(),
    )
    return SolveTrace.model_validate(json.loads(raw))


def reschedule_running_late(
    blocks: list[TimeBlock],
    day: int,
    minutes: int,
    from_start: str,
    previous_placed: list[TimeBlock],
    *,
    deadlines: dict[str, tuple[int, int] | None] | None = None,
    slack_deadlines: dict[str, tuple[int, int]] | None = None,
    extra_occ: list[int] | None = None,
    study_windows: list[StudyWindow] | None = None,
    work_windows: list[WorkWindow] | None = None,
) -> SolveTrace:
    """Occupy a late window on one day, solve again, and describe changed flexible placements."""
    raw = flexweek_engine.reschedule_running_late(
        _blocks(blocks),
        day,
        minutes,
        from_start,
        _blocks(previous_placed),
        _points(deadlines),
        _points(slack_deadlines),
        extra_occ,
        _windows(study_windows),
        _windows(work_windows),
        _clock(),
    )
    return SolveTrace.model_validate(json.loads(raw))
