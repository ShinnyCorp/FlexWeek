"""The standing week (fix-specs item 1): School and activities from Setup are in every week from Setup's
week on, in Week, Day and Month alike; a change reaches the open week on and leaves earlier weeks as they
were; an export carries it; an account from 0.18 gets one built from its weeks."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app

PASSWORD = "a-long-test-password"
WRITE = {"X-FlexWeek-Request": "1", "Origin": "http://testserver"}
SETUP_WEEK = "2026-10-05"
WEEK_BEFORE = "2026-09-28"
NEXT_WEEK = "2026-10-12"
WEEK_AFTER = "2026-10-19"

SCHOOL = {"id": "school", "title": "School", "kind": "locked", "category": "class", "start": "08:30",
          "duration_min": 405, "days": [0, 1, 2, 3, 4]}
SOCCER = {"id": "activity-1", "title": "Soccer", "kind": "locked", "category": "extra", "start": "16:00",
          "duration_min": 90, "days": [1, 3]}
GYM = {"id": "gym", "title": "Gym", "kind": "locked", "start": "18:00", "duration_min": 60, "days": [2]}


def client_for(database: Path) -> TestClient:
    return TestClient(create_app(database=database, origin="http://testserver"))


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    return tmp_path / "standing.db"


@pytest.fixture()
def alice(database: Path) -> Iterator[TestClient]:
    with client_for(database) as client:
        made = client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD}, headers=WRITE)
        assert made.status_code == 201, made.text
        yield client


def stand_request(client: TestClient, week_start: str, blocks: list[dict]):
    """The save Setup and School hours send: the open week's own blocks go in `weeks` (none here)."""
    return client.post(
        "/api/changes", json={"weeks": [], "standing": {"week_start": week_start, "blocks": blocks}}, headers=WRITE
    )


def stand(client: TestClient, week_start: str, blocks: list[dict]) -> dict:
    response = stand_request(client, week_start, blocks)
    assert response.status_code == 200, response.text
    return response.json()


def week(client: TestClient, week_start: str) -> dict:
    response = client.get(f"/api/week?week_start={week_start}")
    assert response.status_code == 200, response.text
    return response.json()


def save(client: TestClient, week_start: str, blocks: list[dict], revision: int = 0) -> dict:
    response = client.put(
        "/api/week", json={"week_start": week_start, "blocks": blocks, "revision": revision}, headers=WRITE
    )
    assert response.status_code == 200, response.text
    return response.json()


def times(blocks: list[dict]) -> dict[str, tuple]:
    return {b["id"]: (b["start"], b["duration_min"], b["days"], b.get("missed_days") or []) for b in blocks}


def test_every_week_from_setups_week_on_has_school_and_soccer(alice: TestClient) -> None:
    stand(alice, SETUP_WEEK, [SCHOOL, SOCCER])
    for later in (SETUP_WEEK, NEXT_WEEK, "2026-11-02"):
        got = week(alice, later)
        assert [b["id"] for b in got["blocks"]] == ["school", "activity-1"], later
        assert got["revision"] == 0
    assert week(alice, WEEK_BEFORE)["blocks"] == []


def test_day_and_month_see_the_standing_week(alice: TestClient) -> None:
    stand(alice, SETUP_WEEK, [SCHOOL, SOCCER])
    tuesday = alice.get("/api/day?date=2026-10-13").json()
    assert {b["id"] for b in tuesday["locked"]} == {"school", "activity-1"}
    month = alice.get("/api/month?month=2026-11").json()
    by_date = {day["date"]: [chip["id"] for chip in day["blocks"]] for day in month["days"]}
    assert by_date["2026-11-04"] == ["school"]  # a Wednesday
    assert by_date["2026-11-05"] == ["school", "activity-1"]  # a Thursday
    assert by_date["2026-11-07"] == []  # a Saturday
    assert alice.get("/api/month?month=2026-09").json()["days"][0]["blocks"] == []


def test_a_weeks_own_missed_day_stays_in_that_week_only(alice: TestClient) -> None:
    stand(alice, SETUP_WEEK, [SCHOOL])
    missed = {**SCHOOL, "missed_days": [2]}
    save(alice, NEXT_WEEK, [missed])
    assert times(week(alice, NEXT_WEEK)["blocks"])["school"][3] == [2]
    assert times(week(alice, WEEK_AFTER)["blocks"])["school"][3] == []


def test_a_change_reaches_the_open_week_on_and_keeps_missed_days_still_school_days(alice: TestClient) -> None:
    stand(alice, SETUP_WEEK, [SCHOOL, SOCCER])
    save(alice, WEEK_AFTER, [{**SCHOOL, "missed_days": [2, 4]}, SOCCER, GYM])
    later = {**SCHOOL, "start": "09:00", "duration_min": 360, "days": [0, 1, 2, 3]}
    answer = stand(alice, NEXT_WEEK, [later, SOCCER])
    assert answer["standing_changed_weeks"] == [WEEK_AFTER]
    assert times(week(alice, SETUP_WEEK)["blocks"])["school"][:2] == ("08:30", 405)
    assert times(week(alice, NEXT_WEEK)["blocks"])["school"][:2] == ("09:00", 360)
    after = week(alice, WEEK_AFTER)
    assert times(after["blocks"])["school"] == ("09:00", 360, [0, 1, 2, 3], [2])
    assert "gym" in times(after["blocks"])
    assert after["revision"] == 2


def test_only_setups_locked_blocks_with_a_start_can_stand(alice: TestClient) -> None:
    for blocks in ([GYM], [{**SCHOOL, "kind": "flexible", "start": None}], [SCHOOL, SCHOOL]):
        assert stand_request(alice, SETUP_WEEK, blocks).status_code == 422, blocks
    assert stand_request(alice, "2026-10-06", []).status_code == 422
    assert week(alice, NEXT_WEEK)["blocks"] == []


def test_the_open_weeks_save_and_the_standing_week_land_together(alice: TestClient) -> None:
    """Setup's save: the open week holds School with Wednesday missed; School stands from it on, and
    the answer shows the open week as Week would."""
    response = alice.post(
        "/api/changes",
        json={
            "weeks": [{"week_start": SETUP_WEEK, "blocks": [{**SCHOOL, "missed_days": [2]}, GYM], "revision": 0}],
            "standing": {"week_start": SETUP_WEEK, "blocks": [{**SCHOOL, "missed_days": [2]}, SOCCER]},
        },
        headers=WRITE,
    )
    assert response.status_code == 200, response.text
    saved = response.json()["weeks"][0]
    assert [b["id"] for b in saved["blocks"]] == ["school", "gym", "activity-1"]
    assert times(week(alice, NEXT_WEEK)["blocks"])["school"][3] == []


def test_an_export_carries_the_standing_week_to_another_account(database: Path, alice: TestClient) -> None:
    stand(alice, SETUP_WEEK, [SCHOOL, SOCCER])
    stand(alice, WEEK_AFTER, [SCHOOL])
    snapshot = alice.post("/api/account-export", json={"password": PASSWORD}, headers=WRITE).json()
    assert len(snapshot["standing"]) == 3
    alice.post("/api/auth/logout", headers=WRITE)
    alice.post("/api/auth/register", json={"username": "bea", "password": PASSWORD}, headers=WRITE)
    imported = import_snapshot(alice, snapshot)
    assert imported.status_code == 200, imported.text
    assert [b["id"] for b in week(alice, NEXT_WEEK)["blocks"]] == ["school", "activity-1"]
    assert [b["id"] for b in week(alice, WEEK_AFTER)["blocks"]] == ["school"]


def test_an_export_from_before_the_standing_week_builds_one_on_import(alice: TestClient) -> None:
    save(alice, SETUP_WEEK, [SCHOOL, SOCCER, GYM])
    snapshot = alice.post("/api/account-export", json={"password": PASSWORD}, headers=WRITE).json()
    del snapshot["standing"]
    alice.post("/api/auth/logout", headers=WRITE)
    alice.post("/api/auth/register", json={"username": "bea", "password": PASSWORD}, headers=WRITE)
    imported = import_snapshot(alice, snapshot)
    assert imported.status_code == 200, imported.text
    assert [b["id"] for b in week(alice, NEXT_WEEK)["blocks"]] == ["school", "activity-1"]


def import_snapshot(client: TestClient, snapshot: dict):
    preview = client.post("/api/account-import/preview", json={"snapshot": snapshot}, headers=WRITE)
    assert preview.status_code == 200, preview.text
    return client.post(
        "/api/account-import",
        json={"snapshot": snapshot, "state_token": preview.json()["state_token"], "operation_id": "import-1"},
        headers=WRITE,
    )


def test_an_account_from_0_18_gets_its_standing_week_from_the_week_setup_ran_in(database: Path) -> None:
    with client_for(database) as client:
        client.post("/api/auth/register", json={"username": "ada", "password": PASSWORD}, headers=WRITE)
        save(client, WEEK_BEFORE, [GYM])
        save(client, SETUP_WEEK, [SCHOOL, SOCCER])
    # As 0.18.5 left it: no standing table, preferences at version 2.
    with sqlite3.connect(database) as db:
        db.execute("DROP TABLE standing_blocks")
        db.execute("UPDATE preferences SET prefs_version = 2")
    with client_for(database) as client:
        login = client.post("/api/auth/login", json={"username": "ada", "password": PASSWORD}, headers=WRITE)
        assert login.status_code == 200, login.text
        assert [b["id"] for b in week(client, "2026-11-16")["blocks"]] == ["school", "activity-1"]
        assert [b["id"] for b in week(client, WEEK_BEFORE)["blocks"]] == ["gym"]
        assert week(client, SETUP_WEEK)["revision"] == 1
