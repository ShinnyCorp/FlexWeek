"""Plan functions in the engine match the original Python on the cases the modules own."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

from backend.tests.engine_ref import assignments as py_assignments
from backend.tests.engine_ref import comfort as py_comfort
from backend.tests.engine_ref import day as py_day
from backend.tests.engine_ref import month as py_month


def test_comfort_split_matches():
    assert json.loads(flexweek_engine.split_plan(50, 25, 5, 15, 4)) == py_comfort.split_plan(50, 25, 5, 15, 4)
    assert flexweek_engine.snap_minutes(22, 1, 180) == py_comfort.snap_minutes(22, 1, 180)


def test_assignment_helpers_match():
    assert flexweek_engine.migrated_assignment_id("2026-09-07", "hw") == py_assignments.migrated_assignment_id(
        "2026-09-07", "hw"
    )
    assert flexweek_engine.unplanned_minutes(90, 15, 30) == py_assignments.unplanned_minutes(90, 15, 30)
    block = {"id": "hw", "days": [0], "latest": "Friday 21:00", "duration_min": 45, "completed": False}
    assert flexweek_engine.due_from_latest("2026-09-07", "Friday 21:00", [0, 4]) == py_assignments.due_from_latest(
        "2026-09-07", "Friday 21:00", [0, 4]
    )
    assert flexweek_engine.completed_at_for_block(
        "2026-09-07", json.dumps({**block, "completed": True, "completed_day": 0, "start": "10:00"})
    ) == py_assignments.completed_at_for_block(
        "2026-09-07", {**block, "completed": True, "completed_day": 0, "start": "10:00"}
    )


def test_prepare_solve_matches():
    from backend.models import TimeBlock

    block = TimeBlock(
        id="hw",
        title="Essay",
        kind="flexible",
        duration_min=45,
        days=[0],
        assignment_id="a",
    )
    assignments = {"a": {"id": "a", "due": "2026-09-07T18:00", "completed": False, "course": "English"}}
    raw = json.loads(
        flexweek_engine.prepare_solve(
            json.dumps([block.model_dump()]),
            "2026-09-07",
            json.dumps(assignments),
        )
    )
    keep, deadlines, slack = py_assignments.prepare_solve([block], "2026-09-07", assignments)
    assert raw["keep"][0]["id"] == keep[0].id
    assert raw["keep"][0]["course"] == keep[0].course
    assert raw["deadlines"]["hw"] == list(deadlines["hw"])
    assert raw["slack"]["hw"] == list(slack["hw"])
    day = json.loads(flexweek_engine.build_day("2026-09-09", "2026-09-07", "[]", "[]", "[]"))
    assert day == py_day.build_day("2026-09-09", "2026-09-07", [], [], [])
    month = json.loads(flexweek_engine.build_month("2026-09", "[]", "[]"))
    assert month == py_month.build_month("2026-09", [], [])
