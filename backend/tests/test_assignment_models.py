"""Assignment and session-block rules from docs/stage1-contract.md. Expected values are from the contract, not a recorded run."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models import Assignment, TimeBlock

ROOT = Path(__file__).resolve().parents[2]


def assignment(**overrides) -> dict:
    body = {
        "id": "hw-essay",
        "title": "Essay",
        "course": "History",
        "category": None,
        "priority": 3,
        "energy": "medium",
        "spotify_url": None,
        "due": "2026-09-15T23:59",
        "estimate_min": 120,
        "focus_minutes": 0,
        "focus_sessions": 0,
        "completed": False,
        "completed_at": None,
        "revision": 0,
    }
    body.update(overrides)
    return body


def session(**overrides) -> dict:
    body = {
        "id": "sess-1",
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0, 1],
        "priority": 3,
        "energy": "medium",
        "assignment_id": "hw-essay",
    }
    body.update(overrides)
    return body


def test_assignment_accepts_any_minute_due_and_dumps_every_field() -> None:
    saved = Assignment.model_validate(assignment())
    assert saved.model_dump() == assignment()


def test_assignment_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        Assignment.model_validate(assignment(planned_min=30))


def test_assignment_due_accepts_a_date_without_a_time() -> None:
    saved = Assignment.model_validate(assignment(due="2026-09-15"))
    assert saved.due == "2026-09-15"


def test_assignment_due_rejects_seconds_timezone_and_out_of_range_dates() -> None:
    for due in (
        "2026-09-15T23:59:00",
        "2026-09-15T23:59Z",
        "2026-09-15 23:59",
        "2026-09-15T24:00",
        "1999-12-31T23:59",
        "2100-01-01T00:00",
        "20260915T23:59",
        "2026-09-15T",
        "2026-09-15 09:00",
        "15-09-2026",
    ):
        with pytest.raises(ValidationError):
            Assignment.model_validate(assignment(due=due))


def test_assignment_due_accepts_times_off_the_15_minute_grid() -> None:
    for due in ("2026-09-15T23:59", "2026-09-14T00:00", "2026-09-08T05:01", "2026-09-15"):
        assert Assignment.model_validate(assignment(due=due)).due == due


def test_assignment_estimate_must_be_a_positive_multiple_of_15() -> None:
    for estimate_min in (0, 10, 7141, -15):
        with pytest.raises(ValidationError):
            Assignment.model_validate(assignment(estimate_min=estimate_min))


def test_assignment_estimate_is_at_most_a_day() -> None:
    assert Assignment.model_validate(assignment(estimate_min=24 * 60)).estimate_min == 24 * 60
    for estimate_min in (24 * 60 + 15, 99 * 60):
        with pytest.raises(ValidationError):
            Assignment.model_validate(assignment(estimate_min=estimate_min))


def test_completed_assignment_requires_completed_at_and_open_one_forbids_it() -> None:
    with pytest.raises(ValidationError, match="completed_at"):
        Assignment.model_validate(assignment(completed=True, completed_at=None))
    with pytest.raises(ValidationError, match="completed_at"):
        Assignment.model_validate(assignment(completed=False, completed_at="2026-09-13T23:59"))
    done = Assignment.model_validate(assignment(completed=True, completed_at="2026-09-13T16:00", revision=1))
    assert done.model_dump()["completed_at"] == "2026-09-13T16:00"


def test_session_block_forbids_latest_and_nonzero_focus() -> None:
    with pytest.raises(ValidationError, match="latest"):
        TimeBlock.model_validate(session(latest="Thursday 21:00"))
    with pytest.raises(ValidationError, match="focus"):
        TimeBlock.model_validate(session(focus_minutes=15))
    with pytest.raises(ValidationError, match="focus"):
        TimeBlock.model_validate(session(focus_sessions=1))


def test_session_block_does_not_carry_due() -> None:
    block = TimeBlock.model_validate(session(due="2026-09-15T23:59"))
    assert "due" not in block.model_dump()


def test_break_chunk_and_locked_non_pomodoro_cannot_carry_assignment_id() -> None:
    with pytest.raises(ValidationError, match="assignment_id"):
        TimeBlock.model_validate(
            session(
                kind="locked",
                start="16:00",
                duration_min=15,
                pomodoro_parent_id="essay",
                pomodoro_role="break",
                pomodoro_index=1,
            )
        )
    with pytest.raises(ValidationError, match="assignment_id"):
        TimeBlock.model_validate(session(kind="locked", start="08:00", duration_min=60))


def test_flexible_session_and_pomodoro_work_chunk_may_carry_assignment_id() -> None:
    flex = TimeBlock.model_validate(session())
    assert flex.assignment_id == "hw-essay"
    assert flex.focus_minutes == 0
    assert flex.latest is None
    work = TimeBlock.model_validate(
        session(
            kind="locked",
            start="16:00",
            duration_min=30,
            pomodoro_parent_id="essay",
            pomodoro_role="work",
            pomodoro_index=1,
        )
    )
    assert work.assignment_id == "hw-essay"


def test_models_module_does_not_import_fastapi() -> None:
    tree = ast.parse((ROOT / "backend" / "models.py").read_text())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".", 1)[0])
    assert "fastapi" not in imported


def test_a_spotify_link_cannot_be_faked_by_putting_the_host_somewhere_else() -> None:
    """The link is handed to the desktop to open externally, so the host has to be the real host and
    not merely present in the string. Each of these puts open.spotify.com somewhere a substring
    check would accept."""
    from backend.models import valid_spotify_url

    for attack in (
        "https://open.spotify.com@evil.com/track/abc",
        "https://evil.com/open.spotify.com/track/abc",
        "https://evil.com/?x=https://open.spotify.com/track/abc",
        "https://open.spotify.com.evil.com/track/abc",
        "http://open.spotify.com/track/abc",
        "https://open.spotify.com:8080/track/abc",
        "javascript:alert(1)//open.spotify.com/track/abc",
    ):
        with pytest.raises(ValueError):
            valid_spotify_url(attack)


def test_a_real_share_link_still_passes() -> None:
    from backend.models import valid_spotify_url

    assert valid_spotify_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert valid_spotify_url("https://open.spotify.com/track/abc?si=xyz")


def test_parse_due_treats_a_date_and_2359_as_the_end_of_that_day() -> None:
    from datetime import date

    from backend.assignments import due_placement_bound, due_slack_point
    from backend.models import END_OF_DAY_MIN, parse_due

    tuesday = date(2026, 9, 15)
    assert parse_due("2026-09-15") == (tuesday, END_OF_DAY_MIN)
    assert parse_due("2026-09-15T23:59") == (tuesday, END_OF_DAY_MIN)
    assert parse_due("2026-09-15T09:00") == (tuesday, 9 * 60)
    week = "2026-09-14"
    assert due_placement_bound(week, "2026-09-15") == (1, END_OF_DAY_MIN)
    assert due_placement_bound(week, "2026-09-15T23:59") == (1, END_OF_DAY_MIN)
    assert due_placement_bound(week, "2026-09-15T09:00") == (1, 9 * 60)
    assert due_slack_point(week, "2026-09-15") == due_slack_point(week, "2026-09-15T23:59")
