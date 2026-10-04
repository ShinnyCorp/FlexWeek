"""Solve adapter for assignment dues. Bounds and slack minutes are worked from the calendar, not from a recorded run."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import create_app

PASSWORD = "a-long-test-password"
WRITE = {"X-FlexWeek-Request": "1", "Origin": "http://testserver"}
WEEK_ONE = "2026-09-07"
WEEK_TWO = "2026-09-14"


@pytest.fixture()
def app(tmp_path: Path) -> FastAPI:
    return create_app(database=tmp_path / "test.db", origin="http://testserver")


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def alice(client: TestClient) -> TestClient:
    assert (
        client.post(
            "/api/auth/register", json={"username": "alice", "password": PASSWORD}, headers=WRITE
        ).status_code
        == 201
    )
    return client


def assignment(assignment_id: str = "hw-essay", **overrides) -> dict:
    body = {
        "id": assignment_id,
        "title": "Essay",
        "course": None,
        "category": None,
        "priority": 3,
        "energy": "high",
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


def session(block_id: str, assignment_id: str = "hw-essay", **overrides) -> dict:
    block = {
        "id": block_id,
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0],
        "priority": 3,
        "energy": "high",
        "assignment_id": assignment_id,
    }
    block.update(overrides)
    return block


def put_assignment(client: TestClient, body: dict) -> None:
    response = client.put(f"/api/assignments/{body['id']}", json=body, headers=WRITE)
    assert response.status_code == 200, response.text


def solve(client: TestClient, blocks: list[dict], week_start: str | None = WEEK_ONE):
    payload: dict = {"blocks": blocks}
    if week_start is not None:
        payload["week_start"] = week_start
    return client.post("/api/solve", json=payload, headers=WRITE)


def test_week_start_is_required_when_a_block_has_assignment_id(alice: TestClient) -> None:
    put_assignment(alice, assignment())
    response = solve(alice, [session("sun", days=[6])], week_start=None)
    assert response.status_code == 422


def test_solve_rejects_another_accounts_assignment_id(app: FastAPI, alice: TestClient) -> None:
    put_assignment(alice, assignment())
    with TestClient(app) as bob:
        assert (
            bob.post(
                "/api/auth/register", json={"username": "bob", "password": PASSWORD}, headers=WRITE
            ).status_code
            == 201
        )
        response = solve(bob, [session("sun", days=[6])])
        assert response.status_code == 422


def test_next_tuesday_due_places_sunday_this_week_and_monday_next_week(alice: TestClient) -> None:
    put_assignment(alice, assignment(due="2026-09-15T23:59"))
    sunday = solve(alice, [session("sun", days=[6])], WEEK_ONE)
    monday = solve(alice, [session("mon", days=[0])], WEEK_TWO)
    assert sunday.status_code == 200, sunday.text
    assert monday.status_code == 200, monday.text
    sun = sunday.json()
    mon = monday.json()
    assert [block["id"] for block in sun["placed"]] == ["sun"]
    assert sun["placed"][0]["days"] == [6]
    assert sun["placed"][0]["start"] == "06:00"
    assert sun["unplaced"] == []
    slack = next(item for item in sun["explanations"] if item.get("slack_min") is not None)
    assert slack["slack_min"] == 3900
    assert slack["slack_status"] == "ok"
    assert [block["id"] for block in mon["placed"]] == ["mon"]
    assert mon["placed"][0]["days"] == [0]
    assert mon["placed"][0]["start"] == "06:00"
    next_slack = next(item for item in mon["explanations"] if item.get("slack_min") is not None)
    assert next_slack["slack_min"] == 2460


def test_sunday_2359_allows_a_session_that_ends_at_the_grid_end(alice: TestClient) -> None:
    prefs = alice.get("/api/preferences").json()
    windows = [{"days": [0, 1, 2, 3, 4, 5, 6], "start": "06:00", "end": "23:00"}]
    assert (
        alice.put("/api/preferences", json={**prefs, "work_windows": windows}, headers=WRITE).status_code
        == 200
    )
    put_assignment(alice, assignment(due="2026-09-13T23:59"))
    response = solve(alice, [session("sun", days=[6], earliest="Sunday 22:00")], WEEK_ONE)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [block["id"] for block in body["placed"]] == ["sun"]
    assert body["placed"][0]["start"] == "22:00"
    assert body["complete"] is True
    slack = next(item for item in body["explanations"] if item.get("slack_min") is not None)
    assert slack["slack_min"] == 60


def test_monday_0000_next_week_has_no_in_week_bound(alice: TestClient) -> None:
    put_assignment(alice, assignment(due="2026-09-14T00:00"))
    response = solve(alice, [session("sun", days=[6])], WEEK_ONE)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [block["id"] for block in body["placed"]] == ["sun"]
    assert body["placed"][0]["days"] == [6]
    slack = next(item for item in body["explanations"] if item.get("slack_min") is not None)
    assert slack["slack_min"] == 1020


def test_due_before_the_week_is_deadline_miss(alice: TestClient) -> None:
    put_assignment(alice, assignment(due="2026-09-06T23:59"))
    response = solve(alice, [session("mon", days=[0])], WEEK_ONE)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [block["id"] for block in body["unplaced"]] == ["mon"]
    assert body["placed"] == []
    assert {move["reason"] for move in body["moves"]} == {"DEADLINE_PASSED"}
    assert "DEADLINE_PASSED" in body["failed_constraints"]


def test_finished_assignment_keeps_completed_slots_and_drops_open_sessions(alice: TestClient) -> None:
    put_assignment(
        alice,
        assignment(completed=True, completed_at="2026-09-13T07:00", due="2026-09-15T23:59"),
    )
    spent = session("sun", days=[6], start="06:00", completed=True, completed_day=6)
    later = session("mon", days=[0])
    this_week = solve(alice, [spent, later], WEEK_ONE)
    next_week = solve(alice, [later], WEEK_TWO)
    assert this_week.status_code == 200, this_week.text
    assert next_week.status_code == 200, next_week.text
    kept = this_week.json()
    skipped = next_week.json()
    assert [block["id"] for block in kept["placed"]] == ["sun"]
    assert kept["placed"][0]["start"] == "06:00"
    assert kept["placed"][0]["days"] == [6]
    assert [block["id"] for block in kept["unplaced"]] == []
    assert skipped["placed"] == []
    assert skipped["unplaced"] == []
    assert skipped["complete"] is True


def test_date_only_due_saves_loads_and_bounds_the_solver_at_the_end_of_that_day(alice: TestClient) -> None:
    put_assignment(alice, assignment(due="2026-09-13"))
    listed = alice.get(f"/api/assignments?week_start={WEEK_ONE}")
    assert listed.status_code == 200, listed.text
    assert listed.json()["assignments"][0]["due"] == "2026-09-13"
    response = solve(alice, [session("sun", days=[6], earliest="Sunday 22:00")], WEEK_ONE)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [block["id"] for block in body["placed"]] == ["sun"]
    assert body["placed"][0]["start"] == "22:00"
    assert body["complete"] is True
    slack = next(item for item in body["explanations"] if item.get("slack_min") is not None)
    assert slack["slack_min"] == 60


def test_a_due_time_bounds_the_solver_at_that_minute(alice: TestClient) -> None:
    put_assignment(alice, assignment(due="2026-09-07T09:00"))
    late = solve(alice, [session("mon", days=[0], earliest="Monday 09:00")], WEEK_ONE)
    assert late.status_code == 200, late.text
    missed = late.json()
    assert [block["id"] for block in missed["unplaced"]] == ["mon"]
    assert {move["reason"] for move in missed["moves"]} == {"DEADLINE_PASSED"}
    on_time = solve(alice, [session("mon", days=[0], earliest="Monday 08:00")], WEEK_ONE)
    assert on_time.status_code == 200, on_time.text
    placed = on_time.json()
    assert [block["id"] for block in placed["placed"]] == ["mon"]
    assert placed["placed"][0]["start"] == "08:00"
    assert placed["complete"] is True
