"""The engine matches the original Python on the cases these modules own.

The oracle is ``backend.tests.engine_ref``, which does not call the live modules.
"""

from __future__ import annotations

import json
import time

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import SolveTrace, WorkWindow
from backend.tests.engine_ref import availability as py_availability
from backend.tests.engine_ref import day as py_day
from backend.tests.engine_ref import month as py_month
from backend.tests.engine_ref import solver as py_solver
from backend.tests.engine_ref import storage as py_storage
from backend.tests.engine_ref.models import ProtectedWindow, StudyWindow, TimeBlock


def _clock():
    started = time.perf_counter()

    def elapsed() -> float:
        return (time.perf_counter() - started) * 1000

    return elapsed


def _trace(raw: str) -> dict:
    body = SolveTrace.model_validate(json.loads(raw)).model_dump()
    body.pop("solve_ms")
    return body


def test_day_lesson_and_due_soon_match():
    lesson = {
        "id": "lesson",
        "title": "Lesson",
        "kind": "locked",
        "start": "17:37",
        "duration_min": 45,
        "days": [1],
    }
    homework = {
        "id": "hw-essay",
        "title": "Essay",
        "due": "2026-09-09T12:00",
        "estimate_min": 60,
        "focus_minutes": 0,
        "completed": False,
        "course": "English",
    }
    rows = json.dumps([[homework, 1]])
    got = json.loads(flexweek_engine.build_day("2026-09-09", "2026-09-07", json.dumps([lesson]), rows, "[]"))
    want = py_day.build_day("2026-09-09", "2026-09-07", [lesson], [(homework, 1)], [])
    assert got["workload"] == want["workload"]
    assert got["next_action"] == want["next_action"]
    assert got["due_soon"] == want["due_soon"]
    assert [TimeBlock.model_validate(block).model_dump() for block in got["locked"]] == want["locked"]


def test_month_deadline_matches():
    homework = {
        "id": "hw-essay",
        "title": "Essay",
        "due": "2026-09-15T18:00",
        "estimate_min": 60,
        "focus_minutes": 0,
        "completed": False,
    }
    got = json.loads(flexweek_engine.build_month("2026-09", json.dumps([[homework, 2]]), "[]"))
    want = py_month.build_month("2026-09", [(homework, 2)], [])
    assert got == want


def test_spread_and_occupancy_match():
    protected = [ProtectedWindow(kind="meal", days=[0], start="18:00", duration_min=60)]
    dumped = json.dumps([window.model_dump() for window in protected])
    assert flexweek_engine.occupancy_from_windows(dumped, "21:00") == py_availability.occupancy_from_windows(
        protected, "21:00"
    )
    assert flexweek_engine.study_rank(
        json.dumps([StudyWindow(days=[0], start="15:00", duration_min=120, subject="Math").model_dump()]),
        "math",
        0,
        15 * 60,
        60,
    ) == py_availability.study_rank(
        [StudyWindow(days=[0], start="15:00", duration_min=120, subject="Math")],
        "math",
        0,
        15 * 60,
        60,
    )
    sessions, remaining = flexweek_engine.spread_sessions(120, 0, 0, "2026-09-15T23:59", 60, "2026-09-14")
    assert (json.loads(sessions), remaining) == py_availability.spread_sessions(
        estimate_min=120,
        focus_minutes=0,
        planned_min=0,
        due="2026-09-15T23:59",
        session_min=60,
        from_date="2026-09-14",
    )
    resolved, defaulted = flexweek_engine.resolve_work_windows(None)
    want_windows, want_defaulted = py_availability.resolve_work_windows(None)
    assert defaulted is want_defaulted
    assert [item.model_dump() for item in want_windows] == [WorkWindow.model_validate(item).model_dump() for item in json.loads(resolved)]


def test_one_homework_matches_the_original_solver():
    school = TimeBlock(
        id="school",
        title="School",
        kind="locked",
        duration_min=390,
        days=[0],
        start="08:00",
        priority=1,
    )
    homework = TimeBlock(
        id="hw", title="Math homework", kind="flexible", duration_min=60, days=[0], energy="high"
    )
    windows = json.dumps([window.model_dump() for window in py_availability.LEGACY_WORK_WINDOWS])
    blocks = json.dumps([school.model_dump(), homework.model_dump()])
    raw = flexweek_engine.solve(blocks, None, None, None, None, windows, _clock())
    want = py_solver.solve(
        [school, homework],
        work_windows=py_availability.LEGACY_WORK_WINDOWS,
    )
    assert _trace(raw) == want.model_dump(exclude={"solve_ms"})


def test_store_hash_vectors():
    assert flexweek_engine.digest("flexweek") == py_storage.digest("flexweek")
    encoded = "scrypt$32768$8$3$00112233445566778899aabbccddeeff$acfa1ad8d5c639d068e6988715f03dd7b1acdb99c998707b1632762596fd2b16"
    assert flexweek_engine.password_hash("secret", "00112233445566778899aabbccddeeff") == encoded
    assert flexweek_engine.password_matches("secret", encoded) is True
    assert flexweek_engine.password_matches("other", encoded) is False


def test_assignment_edges_match():
    from backend.tests.engine_ref import assignments as py_assignments
    from backend.tests.engine_ref.models import TimeBlock as RefBlock

    assert flexweek_engine.due_placement_bound("2026-09-07", "2026-09-09T18:00") == py_assignments.due_placement_bound(
        "2026-09-07", "2026-09-09T18:00"
    )
    assert flexweek_engine.due_slack_point("2026-09-07", "2026-09-09T18:00") == py_assignments.due_slack_point(
        "2026-09-07", "2026-09-09T18:00"
    )
    weeks = [["2026-09-07", [{"assignment_id": "a", "duration_min": 30, "completed": False}]]]
    assert json.loads(flexweek_engine.planned_minutes_by_id(json.dumps(weeks), "2026-09-07")) == py_assignments.planned_minutes_by_id(
        [("2026-09-07", [{"assignment_id": "a", "duration_min": 30, "completed": False}])],
        "2026-09-07",
    )
    block = RefBlock(id="hw", title="Essay", kind="flexible", duration_min=45, days=[0], latest="Friday 21:00")
    raw = json.loads(flexweek_engine.legacy_session("2026-09-07", json.dumps(block.model_dump())))
    session, body = py_assignments.legacy_session("2026-09-07", block)
    assert raw[1] == body
    assert RefBlock.model_validate(raw[0]).model_dump() == session.model_dump()
    base = [0] * 7
    assert list(flexweek_engine.merge_occupancy(base, base)) == py_availability.merge_occupancy(base, base)
    assert flexweek_engine.session_inside_work_windows(
        json.dumps([window.model_dump() for window in py_availability.LEGACY_WORK_WINDOWS]),
        None,
        0,
        8 * 60,
        60,
    ) is py_availability.session_inside_work_windows(py_availability.LEGACY_WORK_WINDOWS, None, 0, 8 * 60, 60)
