"""Stage 4 authenticated API: running late, spread, notes and availability prefs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import Preferences, create_app

PASSWORD = "a-long-test-password"
WRITE = {"X-FlexWeek-Request": "1", "Origin": "http://testserver"}
WEEK = "2026-09-14"
LATE_MESSAGE = "Moved after you ran late so the rest of the day still fits."


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def app(database: Path) -> FastAPI:
    return create_app(database=database, origin="http://testserver")


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def alice(client: TestClient) -> TestClient:
    response = client.post(
        "/api/auth/register", json={"username": "alice", "password": PASSWORD}, headers=WRITE
    )
    assert response.status_code == 201, response.text
    return client


def register(client: TestClient, username: str) -> None:
    assert (
        client.post(
            "/api/auth/register", json={"username": username, "password": PASSWORD}, headers=WRITE
        ).status_code
        == 201
    )


def assignment(**overrides) -> dict:
    body = {
        "id": "hw-essay",
        "title": "Essay",
        "course": "History",
        "category": None,
        "priority": 2,
        "energy": "low",
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


def defaults(client: TestClient) -> dict:
    return client.get("/api/preferences").json()


def test_running_late_preview_does_not_write_the_week(alice: TestClient) -> None:
    prefs = defaults(alice)
    windows = [{"days": [0, 1, 2, 3, 4, 5, 6], "start": "06:00", "end": "23:00"}]
    assert (
        alice.put("/api/preferences", json={**prefs, "work_windows": windows}, headers=WRITE).status_code
        == 200
    )
    wind = {
        "id": "wind",
        "title": "Wind-down",
        "kind": "locked",
        "duration_min": 960,
        "days": [0],
        "priority": 1,
        "energy": "medium",
        "start": "07:00",
    }
    homework = {
        "id": "hw",
        "title": "Homework",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0],
        "priority": 3,
        "energy": "high",
    }
    before = alice.post("/api/solve", json={"blocks": [wind, homework]}, headers=WRITE)
    assert before.status_code == 200, before.text
    assert {block["id"] for block in before.json()["placed"]} >= {"wind", "hw"}
    late = alice.post(
        "/api/solve",
        json={
            "blocks": [wind, homework],
            "running_late": {
                "day": 0,
                "minutes": 60,
                "from_start": "06:00",
                "previous_placed": before.json()["placed"],
            },
        },
        headers=WRITE,
    )
    assert late.status_code == 200, late.text
    body = late.json()
    assert [block["id"] for block in body["unplaced"]] == ["hw"]
    assert next(block for block in body["placed"] if block["id"] == "wind")["start"] == "07:00"
    stored = alice.get(f"/api/week?week_start={WEEK}")
    assert stored.status_code == 200
    assert stored.json() == {"week_start": WEEK, "blocks": [], "revision": 0}


def test_running_late_rejects_recover_together_and_illegal_minutes(alice: TestClient) -> None:
    homework = {
        "id": "hw",
        "title": "Homework",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0],
        "priority": 3,
        "energy": "medium",
    }
    school = {
        "id": "school",
        "title": "School",
        "kind": "locked",
        "duration_min": 60,
        "days": [0],
        "start": "08:00",
    }
    both = alice.post(
        "/api/solve",
        json={
            "blocks": [school, homework],
            "recover": {"missed_block_id": "school", "missed_day": 0, "previous_placed": []},
            "running_late": {"day": 0, "minutes": 30, "from_start": "14:30", "previous_placed": []},
        },
        headers=WRITE,
    )
    assert both.status_code == 422
    bad_minutes = alice.post(
        "/api/solve",
        json={
            "blocks": [homework],
            "running_late": {"day": 0, "minutes": 45, "from_start": "14:30", "previous_placed": []},
        },
        headers=WRITE,
    )
    assert bad_minutes.status_code == 422


def test_running_late_explanation_uses_the_late_sentence(alice: TestClient) -> None:
    prefs = defaults(alice)
    windows = [{"days": [0, 1, 2, 3, 4, 5, 6], "start": "06:00", "end": "23:00"}]
    assert (
        alice.put("/api/preferences", json={**prefs, "work_windows": windows}, headers=WRITE).status_code
        == 200
    )
    school = {
        "id": "school",
        "title": "School",
        "kind": "locked",
        "duration_min": 390,
        "days": [0],
        "priority": 1,
        "energy": "medium",
        "start": "08:00",
    }
    homework = {
        "id": "hw",
        "title": "Homework",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0, 1],
        "priority": 3,
        "energy": "high",
    }
    before = alice.post("/api/solve", json={"blocks": [school, homework]}, headers=WRITE)
    assert before.status_code == 200, before.text
    late = alice.post(
        "/api/solve",
        json={
            "blocks": [school, homework],
            "running_late": {
                "day": 0,
                "minutes": 30,
                "from_start": "06:00",
                "previous_placed": before.json()["placed"],
            },
        },
        headers=WRITE,
    )
    assert late.status_code == 200, late.text
    move = next(item for item in late.json()["moves"] if item["reason"] == "RESHUFFLE_AFTER_MISS")
    assert move["block_id"] == "hw"
    assert move["from_start"] == "06:00"
    assert move["to_start"] == "06:30"
    message = next(
        item["message"]
        for item in late.json()["explanations"]
        if item["block_id"] == "hw" and item["reason"] == "RESHUFFLE_AFTER_MISS"
    )
    assert message == LATE_MESSAGE


def test_spread_preview_does_not_write_and_stays_on_one_assignment(alice: TestClient) -> None:
    saved = alice.put("/api/assignments/hw-essay", json=assignment(), headers=WRITE)
    assert saved.status_code == 200, saved.text
    preview = alice.post(
        "/api/assignments/hw-essay/spread",
        json={"session_min": 60, "from_date": "2026-09-14"},
        headers=WRITE,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "assignment_id": "hw-essay",
        "session_min": 60,
        "remaining_min": 0,
        "sessions": [
            {"week_start": "2026-09-14", "date": "2026-09-14", "days": [0], "duration_min": 60},
            {"week_start": "2026-09-14", "date": "2026-09-15", "days": [1], "duration_min": 60},
        ],
    }
    listed = alice.get(f"/api/assignments?week_start={WEEK}").json()["assignments"]
    assert listed[0]["id"] == "hw-essay"
    assert "pomodoro_parent_id" not in listed[0]
    week = alice.get(f"/api/week?week_start={WEEK}").json()
    assert week == {"week_start": WEEK, "blocks": [], "revision": 0}


def test_spread_on_another_account_is_404(app: FastAPI, alice: TestClient) -> None:
    assert alice.put("/api/assignments/hw-essay", json=assignment(), headers=WRITE).status_code == 200
    with TestClient(app) as bob:
        register(bob, "bob")
        stolen = bob.post(
            "/api/assignments/hw-essay/spread",
            json={"session_min": 60, "from_date": "2026-09-14"},
            headers=WRITE,
        )
        assert stolen.status_code == 404


def test_spread_rejects_a_completed_assignment(alice: TestClient) -> None:
    body = assignment(completed=True, completed_at="2026-09-14T16:00")
    assert alice.put("/api/assignments/hw-essay", json=body, headers=WRITE).status_code == 200
    response = alice.post(
        "/api/assignments/hw-essay/spread",
        json={"session_min": 60, "from_date": "2026-09-14"},
        headers=WRITE,
    )
    assert response.status_code == 422


def test_assignment_notes_round_trip_over_http(alice: TestClient) -> None:
    payload = assignment(
        notes="Bring the outline.",
        links=[{"label": "Prompt", "url": "https://example.edu/essay"}],
        checklist=[{"id": "draft", "text": "First draft", "done": True}],
    )
    saved = alice.put("/api/assignments/hw-essay", json=payload, headers=WRITE)
    assert saved.status_code == 200, saved.text
    assert saved.json()["notes"] == "Bring the outline."
    assert saved.json()["links"] == [{"label": "Prompt", "url": "https://example.edu/essay"}]
    assert saved.json()["checklist"] == [{"id": "draft", "text": "First draft", "done": True}]
    loaded = alice.get(f"/api/assignments?week_start={WEEK}").json()["assignments"][0]
    assert loaded["notes"] == "Bring the outline."
    assert loaded["links"] == [{"label": "Prompt", "url": "https://example.edu/essay"}]
    assert loaded["checklist"] == [{"id": "draft", "text": "First draft", "done": True}]
    rejected = alice.put(
        "/api/assignments/hw-essay",
        json=assignment(revision=1, links=[{"label": "Bad", "url": "javascript:alert(1)"}]),
        headers=WRITE,
    )
    assert rejected.status_code == 422


def test_preferences_reject_off_grid_windows_and_solve_honors_cutoff(alice: TestClient) -> None:
    prefs = defaults(alice)
    bad = alice.put(
        "/api/preferences",
        json={
            **prefs,
            "protected": [{"kind": "downtime", "days": [0], "start": "06:07", "duration_min": 60}],
        },
        headers=WRITE,
    )
    assert bad.status_code == 422
    saved = alice.put(
        "/api/preferences",
        json={**prefs, "day_cutoff": "06:15"},
        headers=WRITE,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["day_cutoff"] == "06:15"
    assert alice.get("/api/preferences").json()["day_cutoff"] == "06:15"
    homework = {
        "id": "hw",
        "title": "Homework",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0],
        "priority": 3,
        "energy": "high",
    }
    solved = alice.post("/api/solve", json={"blocks": [homework]}, headers=WRITE)
    assert solved.status_code == 200, solved.text
    placed = next(block for block in solved.json()["placed"] if block["id"] == "hw")
    hour, minute = map(int, placed["start"].split(":"))
    assert hour * 60 + minute + int(placed["duration_min"]) <= 6 * 60 + 15


def test_estimates_and_the_planners_windows_stay_on_the_quarter_hour(alice: TestClient) -> None:
    """Blocks take any minute; what the planner works in does not. Each of these is one minute or
    five off a quarter hour, and each is refused."""
    assert alice.put("/api/assignments/hw-essay", json=assignment(estimate_min=50), headers=WRITE).status_code == 422
    prefs = defaults(alice)
    off: list[dict] = [
        {"work_windows": [{"days": [0], "start": "17:05", "end": "19:00"}]},
        {"work_windows": [{"days": [0], "start": "17:00", "end": "19:10"}]},
        {"study_windows": [{"days": [0], "start": "17:05", "duration_min": 60}]},
        {"study_windows": [{"days": [0], "start": "17:00", "duration_min": 50}]},
        {"protected": [{"kind": "meal", "days": [0], "start": "18:05", "duration_min": 30}]},
        {"day_cutoff": "21:05"},
        {"auto_split_pomodoro": True, "timer_work_min": 25},
    ]
    for change in off:
        assert alice.put("/api/preferences", json={**prefs, **change}, headers=WRITE).status_code == 422, change
    assert alice.put("/api/assignments/hw-essay", json=assignment(), headers=WRITE).status_code == 200
    spread = alice.post(
        "/api/assignments/hw-essay/spread",
        json={"session_min": 50, "from_date": "2026-09-14"},
        headers=WRITE,
    )
    assert spread.status_code == 422


def test_preferred_study_hours_saved_by_an_older_build_open_as_study_hours(
    alice: TestClient, database: Path
) -> None:
    """J7: a preferences row as 0.18.2 saved it, with planning hours and preferred study hours apart,
    opens as one Study hours list, the planner reads that list, and the next save writes it alone."""
    old = {
        "work_windows": [{"days": [0, 1, 2, 3, 4], "start": "16:00", "end": "21:00"}],
        "study_windows": [{"days": [5, 6], "start": "10:00", "duration_min": 120}],
    }
    with sqlite3.connect(database) as db:
        db.execute("UPDATE preferences SET availability_json = ?", (json.dumps(old),))
    prefs = alice.get("/api/preferences").json()
    assert "study_windows" not in prefs
    hours = [
        {"days": [0, 1, 2, 3, 4], "start": "16:00", "end": "21:00"},
        {"days": [5, 6], "start": "10:00", "end": "12:00"},
    ]
    assert prefs["work_windows"] == hours
    # Saturday has no other hours, so homework there goes in the carried window or nowhere.
    homework = {
        "id": "hw",
        "title": "Homework",
        "kind": "flexible",
        "duration_min": 60,
        "days": [5],
        "priority": 3,
        "energy": "low",
    }
    solved = alice.post("/api/solve", json={"blocks": [homework]}, headers=WRITE)
    assert solved.status_code == 200, solved.text
    assert next(block for block in solved.json()["placed"] if block["id"] == "hw")["start"] == "10:00"
    assert alice.put("/api/preferences", json=prefs, headers=WRITE).status_code == 200
    with sqlite3.connect(database) as db:
        (stored,) = db.execute("SELECT availability_json FROM preferences").fetchone()
    assert json.loads(stored)["work_windows"] == hours
    assert "study_windows" not in json.loads(stored)


def test_an_older_client_sending_preferred_study_hours_saves_them_as_study_hours(
    alice: TestClient,
) -> None:
    prefs = defaults(alice)
    preferred = [{"days": [2], "start": "19:00", "duration_min": 90, "subject": "Math"}]
    saved = alice.put("/api/preferences", json={**prefs, "study_windows": preferred}, headers=WRITE)
    assert saved.status_code == 200, saved.text
    assert "study_windows" not in saved.json()
    assert saved.json()["work_windows"] == [
        {"days": [2], "start": "19:00", "end": "20:30", "subject": "Math"}
    ]
    assert alice.get("/api/preferences").json()["work_windows"] == saved.json()["work_windows"]


def test_protected_time_keeps_an_optional_name(alice: TestClient, database: Path) -> None:
    prefs = defaults(alice)
    piano = {"kind": "downtime", "days": [1, 3], "start": "17:00", "duration_min": 90}
    saved = alice.put(
        "/api/preferences",
        json={**prefs, "protected": [{**piano, "title": "  Piano "}, {**piano, "days": [5], "title": " "}]},
        headers=WRITE,
    )
    assert saved.status_code == 200, saved.text
    named, blank = saved.json()["protected"]
    assert named["title"] == "Piano", "trimmed"
    assert "title" not in blank, "a blank name is no name"
    assert alice.get("/api/preferences").json()["protected"] == saved.json()["protected"]
    too_long = {**piano, "title": "x" * 41}
    assert alice.put("/api/preferences", json={**prefs, "protected": [too_long]}, headers=WRITE).status_code == 422
    # A row saved before names existed still opens, without one.
    with sqlite3.connect(database) as db:
        db.execute("UPDATE preferences SET availability_json = ?", (json.dumps({"protected": [piano]}),))
    assert alice.get("/api/preferences").json()["protected"] == [piano]


def test_preferences_reject_overlapping_protected_windows_and_accept_adjacent_ones(
    alice: TestClient,
) -> None:
    prefs = defaults(alice)
    overlapping = alice.put(
        "/api/preferences",
        json={
            **prefs,
            "protected": [
                {"kind": "downtime", "days": [0], "start": "18:00", "duration_min": 60},
                {"kind": "meal", "days": [0], "start": "18:30", "duration_min": 60},
            ],
        },
        headers=WRITE,
    )
    assert overlapping.status_code == 422
    adjacent = alice.put(
        "/api/preferences",
        json={
            **prefs,
            "protected": [
                {"kind": "downtime", "days": [0], "start": "18:00", "duration_min": 60},
                {"kind": "meal", "days": [0], "start": "19:00", "duration_min": 60},
            ],
        },
        headers=WRITE,
    )
    assert adjacent.status_code == 200, adjacent.text
    same_time_other_day = alice.put(
        "/api/preferences",
        json={
            **prefs,
            "protected": [
                {"kind": "downtime", "days": [0], "start": "18:00", "duration_min": 120},
                {"kind": "meal", "days": [1], "start": "19:00", "duration_min": 60},
            ],
        },
        headers=WRITE,
    )
    assert same_time_other_day.status_code == 200, same_time_other_day.text


def test_protected_window_model_rejects_overlap_and_accepts_adjacency() -> None:
    base = {"theme": "system"}
    with pytest.raises(ValidationError):
        Preferences.model_validate(
            {
                **base,
                "protected": [
                    {"kind": "downtime", "days": [0], "start": "18:00", "duration_min": 60},
                    {"kind": "meal", "days": [0], "start": "18:30", "duration_min": 60},
                ],
            }
        )
    adjacent = Preferences.model_validate(
        {
            **base,
            "protected": [
                {"kind": "downtime", "days": [0], "start": "18:00", "duration_min": 60},
                {"kind": "meal", "days": [0], "start": "19:00", "duration_min": 60},
            ],
        }
    )
    assert len(adjacent.protected) == 2
