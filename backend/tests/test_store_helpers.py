"""The store helpers through the app's HTTP routes, and the rollback cases the move could have broken."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import app
from backend.app import create_app, replace_account
from backend.models import Routine
from backend.storage import connect, initialize

PASSWORD = "a-long-test-password"
WRITE = {"X-FlexWeek-Request": "1", "Origin": "http://testserver"}
WEEK_A = "2026-09-07"
WEEK_B = "2026-09-14"
WEEK_C = "2026-09-21"
TABLES = (
    "users",
    "sessions",
    "weeks",
    "assignments",
    "routines",
    "restore_points",
    "operations",
    "preferences",
    "recovery_codes",
)
CONFLICT = "This assignment changed in another window. Reload before saving."


def limit(monkeypatch: pytest.MonkeyPatch, **values: int) -> None:
    for name, value in values.items():
        monkeypatch.setattr(app, name, value)


def seed_users(db: Any) -> None:
    for user_id, name in ((1, "ada"), (2, "bob"), (3, "cy")):
        db.execute("INSERT INTO users(id, username, password_hash) VALUES (?, ?, 'x')", (user_id, name))
    for user_id in (1, 2):
        db.execute(
            "INSERT INTO preferences(user_id, reminders_enabled, prefs_version) VALUES (?, 1, 1)", (user_id,)
        )


def routine(routine_id: str, name: str, revision: int = 0, title: str = "Block") -> Routine:
    return Routine.model_validate(
        {
            "id": routine_id,
            "name": name,
            "revision": revision,
            "blocks": [
                {
                    "template_id": "t1",
                    "title": title,
                    "days": [0, 1],
                    "start": "08:00",
                    "duration_min": 60,
                }
            ],
        }
    )


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def server(database: Path) -> FastAPI:
    return create_app(database=database, origin="http://testserver")


@pytest.fixture()
def client(server: FastAPI) -> Iterator[TestClient]:
    with TestClient(server) as test_client:
        yield test_client


@pytest.fixture()
def alice(client: TestClient) -> TestClient:
    registered = client.post(
        "/api/auth/register", json={"username": "alice", "password": PASSWORD}, headers=WRITE
    )
    assert registered.status_code == 201, registered.text
    return client


def assignment_body(**overrides: Any) -> dict:
    body = {
        "id": "hw-essay",
        "title": "Essay",
        "course": None,
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


def routine_body() -> dict:
    return {**routine("r1", "Morning").model_dump(), "revision": 0}


def locked_block() -> dict:
    return {
        "id": "school",
        "title": "School",
        "kind": "locked",
        "duration_min": 390,
        "days": [0, 1, 2, 3, 4],
        "priority": 1,
        "energy": "medium",
        "start": "08:00",
        "category": "School",
    }


def put_week(client: TestClient, week_start: str, blocks: list[dict], revision: int) -> None:
    response = client.put(
        "/api/week",
        json={"week_start": week_start, "blocks": blocks, "revision": revision},
        headers=WRITE,
    )
    assert response.status_code == 200, response.text


def session(block_id: str) -> dict:
    return {
        "id": block_id,
        "title": "stale title",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0],
        "priority": 3,
        "energy": "medium",
        "assignment_id": "hw-essay",
    }


HUGE = [2**63, -(2**63) - 1, 2**200]


@pytest.mark.parametrize("revision", HUGE)
def test_deleting_an_assignment_with_a_revision_beyond_64_bits_answers_409_or_404(
    alice: TestClient, revision: int
) -> None:
    missing = alice.delete(f"/api/assignments/hw-essay?revision={revision}", headers=WRITE)
    assert (missing.status_code, missing.json()) == (404, {"detail": "Assignment not found"})
    assert alice.put("/api/assignments/hw-essay", json=assignment_body(), headers=WRITE).status_code == 200
    stale = alice.delete(f"/api/assignments/hw-essay?revision={revision}", headers=WRITE)
    assert (stale.status_code, stale.json()) == (409, {"detail": CONFLICT})
    assert alice.delete("/api/assignments/hw-essay?revision=1", headers=WRITE).status_code == 200


@pytest.mark.parametrize("revision", HUGE)
def test_deleting_a_routine_with_a_revision_beyond_64_bits_answers_409_or_404(
    alice: TestClient, revision: int
) -> None:
    missing = alice.delete(f"/api/routines/r1?revision={revision}", headers=WRITE)
    assert (missing.status_code, missing.json()) == (404, {"detail": "Routine not found"})
    assert alice.put("/api/routines/r1", json=routine_body(), headers=WRITE).status_code == 200
    stale = alice.delete(f"/api/routines/r1?revision={revision}&operation_id=op-1", headers=WRITE)
    assert (stale.status_code, stale.json()) == (
        409,
        {"detail": "This routine changed in another window. Reload before saving."},
    )
    assert alice.delete("/api/routines/r1?revision=1", headers=WRITE).status_code == 200


def stored_session_week(client: TestClient) -> None:
    assert client.put("/api/assignments/hw-essay", json=assignment_body(), headers=WRITE).status_code == 200
    put_week(client, WEEK_B, [session("w1")], 0)


def test_changed_weeks_list_the_week_before_its_revision_in_the_delete_response_text(
    alice: TestClient,
) -> None:
    stored_session_week(alice)
    deleted = alice.delete("/api/assignments/hw-essay?revision=1", headers=WRITE)
    assert deleted.status_code == 200, deleted.text
    assert f'"changed_weeks":[{{"week_start":"{WEEK_B}","revision":2}}]' in deleted.text


def test_changed_weeks_list_the_week_before_its_revision_in_the_changes_response_text(
    alice: TestClient,
) -> None:
    stored_session_week(alice)
    batch = alice.post(
        "/api/changes",
        json={"weeks": [], "assignments": [{"id": "hw-essay", "assignment": None, "revision": 1}]},
        headers=WRITE,
    )
    assert batch.status_code == 200, batch.text
    assert f'"changed_weeks":[{{"week_start":"{WEEK_B}","revision":2}}]' in batch.text


def test_the_two_get_routes_read_through_the_store(
    alice: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert alice.put("/api/routines/r1", json=routine_body(), headers=WRITE).status_code == 200
    calls: list[tuple[str, tuple]] = []

    class Spy:
        def __init__(self, db: Any) -> None:
            self.db = db

        def __getattr__(self, name: str) -> Any:
            member = getattr(self.db, name)

            def recorded(*args: Any) -> Any:
                calls.append((name, args))
                return member(*args)

            return recorded

    @contextmanager
    def spied(path: Path) -> Iterator[Spy]:
        with connect(path) as db:
            yield Spy(db)

    monkeypatch.setattr(app, "connect", spied)
    routines = alice.get("/api/routines")
    preferences = alice.get("/api/preferences")
    assert routines.status_code == preferences.status_code == 200
    assert [item["id"] for item in routines.json()["routines"]] == ["r1"]
    assert preferences.json()["theme"] == "system"
    names = [name for name, _args in calls]
    assert "list_routines" in names
    assert "preference_row" in names
    statements = [args[0] for name, args in calls if name == "execute"]
    assert not [text for text in statements if "routines" in text or "preferences" in text]


def test_a_python_write_is_undone_when_a_later_store_write_fails(tmp_path: Path) -> None:
    path = tmp_path / "week.sqlite"
    initialize(path)
    with connect(path) as db:
        seed_users(db)
        db.insert_assignment(1, "hw-essay", '{"id":"hw-essay"}')
    with pytest.raises(sqlite3.IntegrityError), connect(path) as db:
        db.execute(
            "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (1, ?, '[]', 1)", (WEEK_A,)
        )
        db.insert_assignment(1, "hw-essay", '{"id":"hw-essay"}')
    with connect(path) as db:
        assert db.execute("SELECT COUNT(*) AS n FROM weeks").fetchone()["n"] == 0
        assert db.count_assignments(1) == 1


def test_a_changes_batch_with_an_upsert_then_a_stale_week_leaves_no_assignment(alice: TestClient) -> None:
    put_week(alice, WEEK_A, [], 0)
    fresh = assignment_body()
    fresh.pop("revision")
    stale = alice.post(
        "/api/changes",
        json={
            "weeks": [{"week_start": WEEK_A, "blocks": [locked_block()], "revision": 7}],
            "assignments": [{"id": "hw-essay", "assignment": fresh, "revision": 0}],
        },
        headers=WRITE,
    )
    assert stale.status_code == 409, stale.text
    listed = alice.get(f"/api/assignments?week_start={WEEK_A}")
    assert listed.json() == {"assignments": []}


def test_replace_account_failing_after_its_deletes_leaves_the_account_as_it_was(tmp_path: Path) -> None:
    path = tmp_path / "week.sqlite"
    initialize(path)
    with connect(path) as db:
        seed_users(db)
        db.execute(
            'INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (1, ?, \'[{"id":"old"}]\', 3)',
            (WEEK_A,),
        )
        db.insert_assignment(1, "old", '{"id":"old"}')
    twice = {"week_start": WEEK_B, "blocks": [], "revision": 1}
    with pytest.raises(sqlite3.IntegrityError), connect(path) as db:
        replace_account(db, 1, {"weeks": [twice, twice], "assignments": []})
    with connect(path) as db:
        weeks = db.execute("SELECT week_start, blocks, revision FROM weeks WHERE user_id = 1").fetchall()
        assert [(row["week_start"], row["blocks"], row["revision"]) for row in weeks] == [
            (WEEK_A, '[{"id":"old"}]', 3)
        ]
        assert db.count_assignments(1) == 1


OWNED = tuple(table for table in TABLES if table not in ("users", "sessions"))


@pytest.fixture()
def bob(server: FastAPI) -> Iterator[TestClient]:
    with TestClient(server) as test_client:
        registered = test_client.post(
            "/api/auth/register", json={"username": "bob", "password": PASSWORD}, headers=WRITE
        )
        assert registered.status_code == 201, registered.text
        yield test_client


def account_rows(path: Path, username: str) -> dict[str, list[tuple]]:
    """Every row one account owns, as stored, to compare before and after the other one acts."""
    plain = sqlite3.connect(path)
    try:
        found = plain.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        return {
            table: plain.execute(
                f"SELECT * FROM {table} WHERE user_id = ? ORDER BY rowid", (found[0],)
            ).fetchall()
            for table in OWNED
        }
    finally:
        plain.close()


def put_assignment(client: TestClient, **overrides: Any) -> Any:
    body = assignment_body(**overrides)
    return client.put(f"/api/assignments/{body['id']}", json=body, headers=WRITE)


def test_deleting_an_assignment_leaves_the_other_accounts_same_id_rows_alone(
    alice: TestClient, bob: TestClient, database: Path
) -> None:
    assert put_assignment(alice).status_code == 200
    assert put_assignment(bob, title="Bob's essay").status_code == 200
    put_week(alice, WEEK_B, [session("a1"), locked_block()], 0)
    put_week(bob, WEEK_B, [session("b1"), {**locked_block(), "id": "bob-keep"}], 0)
    put_week(bob, WEEK_C, [session("b2")], 0)
    before = account_rows(database, "bob")

    deleted = alice.delete("/api/assignments/hw-essay?revision=1", headers=WRITE)

    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert body["changed_weeks"] == [{"week_start": WEEK_B, "revision": 2}]
    assert [block["id"] for block in body["removed_sessions"][WEEK_B]] == ["a1"]
    assert list(body["removed_sessions"]) == [WEEK_B]
    assert [block["id"] for block in alice.get(f"/api/week?week_start={WEEK_B}").json()["blocks"]] == [
        "school"
    ]
    assert account_rows(database, "bob") == before


def test_one_accounts_assignment_writes_leave_the_other_accounts_same_id_alone(
    alice: TestClient, bob: TestClient, database: Path
) -> None:
    assert put_assignment(bob, title="Bob's essay").status_code == 200
    before = account_rows(database, "bob")

    created = put_assignment(alice)
    assert (created.status_code, created.json()["revision"]) == (200, 1)
    edited = put_assignment(alice, title="Renamed", revision=1)
    assert (edited.status_code, edited.json()["revision"]) == (200, 2)

    assert account_rows(database, "bob") == before
    bobs = bob.get(f"/api/assignments?week_start={WEEK_A}").json()["assignments"]
    assert [(item["id"], item["title"], item["revision"]) for item in bobs] == [
        ("hw-essay", "Bob's essay", 1)
    ]


def test_another_accounts_assignments_do_not_count_toward_the_limit(
    alice: TestClient, bob: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    limit(monkeypatch, MAX_ASSIGNMENTS=2)
    assert put_assignment(bob, id="b1").status_code == 200
    assert put_assignment(bob, id="b2").status_code == 200
    assert put_assignment(bob, id="b3").status_code == 422
    assert put_assignment(alice, id="a1").status_code == 200


def test_a_legacy_deadline_adopted_by_one_account_is_still_created_for_the_other(
    alice: TestClient, bob: TestClient
) -> None:
    legacy = {
        "id": "essay",
        "title": "Draft title",
        "kind": "flexible",
        "duration_min": 90,
        "days": [0, 1, 2, 3, 4],
        "priority": 2,
        "energy": "low",
        "course": "History",
        "latest": "Thursday 21:00",
    }
    for client in (bob, alice):
        saved = client.put(
            "/api/week", json={"week_start": WEEK_A, "blocks": [legacy], "revision": 0}, headers=WRITE
        )
        assert saved.status_code == 200, saved.text
    mine = alice.get(f"/api/assignments?week_start={WEEK_A}").json()["assignments"]
    assert len(mine) == 1
    assert mine[0]["id"] == alice.get(f"/api/week?week_start={WEEK_A}").json()["blocks"][0]["assignment_id"]


def test_updating_a_routine_leaves_the_other_accounts_same_id_routine_alone(
    alice: TestClient, bob: TestClient, database: Path
) -> None:
    morning = routine_body()
    assert alice.put("/api/routines/r1", json=morning, headers=WRITE).status_code == 200
    assert bob.put("/api/routines/r1", json={**morning, "name": "Bob's"}, headers=WRITE).status_code == 200
    before = account_rows(database, "bob")

    renamed = alice.put("/api/routines/r1", json={**morning, "name": "Evening", "revision": 1}, headers=WRITE)

    assert (renamed.status_code, renamed.json()["name"], renamed.json()["revision"]) == (200, "Evening", 2)
    assert account_rows(database, "bob") == before
    assert [item["name"] for item in bob.get("/api/routines").json()["routines"]] == ["Bob's"]


def test_importing_into_one_account_leaves_the_other_accounts_rows_alone(
    alice: TestClient, bob: TestClient, database: Path
) -> None:
    morning = routine_body()
    assert alice.put("/api/routines/r1", json=morning, headers=WRITE).status_code == 200
    assert bob.put("/api/routines/r1", json={**morning, "name": "Bob's"}, headers=WRITE).status_code == 200
    assert put_assignment(alice).status_code == 200
    assert put_assignment(bob, title="Bob's essay").status_code == 200
    put_week(bob, WEEK_B, [session("b1")], 0)
    before = account_rows(database, "bob")

    exported = alice.post("/api/account-export", json={"password": PASSWORD}, headers=WRITE)
    assert exported.status_code == 200, exported.text
    snapshot = exported.json()
    snapshot["routines"][0]["name"] = "Evening"
    snapshot["assignments"][0]["body"]["title"] = "Renamed"
    preview = alice.post("/api/account-import/preview", json={"snapshot": snapshot}, headers=WRITE)
    assert preview.status_code == 200, preview.text
    applied = alice.post(
        "/api/account-import",
        json={
            "snapshot": snapshot,
            "state_token": preview.json()["state_token"],
            "operation_id": "op-import",
        },
        headers=WRITE,
    )

    assert applied.status_code == 200, applied.text
    assert [item["name"] for item in alice.get("/api/routines").json()["routines"]] == ["Evening"]
    assert account_rows(database, "bob") == before
