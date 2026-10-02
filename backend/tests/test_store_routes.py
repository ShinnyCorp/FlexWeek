"""Routes whose SQL moved into the Rust store, driven as scripted sequences with two accounts.

Each test registers two accounts that hold rows under the same ids, acts as one of them, and checks
that the other's rows are exactly as they were and that no read shows rows of the other. Expected
values are worked out from the original routes (a1e7753), not from what the store returns.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.recovery import hash_recovery_code
from backend.storage import connect

PASSWORD_A = "alice-long-password"
PASSWORD_B = "bobby-long-password"
PASSWORD_NEW = "replacement-long-password"
WRITE = {"X-FlexWeek-Request": "1", "Origin": "http://testserver"}
WEEK_1 = "2026-09-14"
WEEK_2 = "2026-09-21"
SIGN_IN = {"detail": "Please sign in"}
WRONG_PASSWORD = {"detail": "Incorrect password"}
WRONG_CODE = {"detail": "Incorrect username or recovery code"}
WRONG_LOGIN = {"detail": "Incorrect username or password"}


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    return tmp_path / "routes.db"


@pytest.fixture()
def app(database: Path) -> FastAPI:
    return create_app(database=database, origin="http://testserver")


@pytest.fixture()
def clients(app: FastAPI) -> Iterator[ExitStack]:
    with ExitStack() as stack:
        yield stack


def browser(app: FastAPI, clients: ExitStack) -> TestClient:
    return clients.enter_context(TestClient(app))


def register(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password}, headers=WRITE
    )
    assert response.status_code == 201, response.text
    return response.json()


def sign_in(client: TestClient, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password}, headers=WRITE)


def recover(client: TestClient, username: str, code: str, password: str = PASSWORD_NEW):
    return client.post(
        "/api/auth/recover", json={"username": username, "code": code, "password": password}, headers=WRITE
    )


def assignment(title: str, estimate: int, due: str, revision: int = 0) -> dict:
    return {
        "id": "hw",
        "title": title,
        "course": None,
        "category": "Homework",
        "priority": 3,
        "energy": "medium",
        "spotify_url": None,
        "due": due,
        "estimate_min": estimate,
        "focus_minutes": 0,
        "focus_sessions": 0,
        "completed": False,
        "completed_at": None,
        "revision": revision,
    }


def school(title: str) -> dict:
    return {
        "id": "school",
        "title": title,
        "kind": "locked",
        "duration_min": 390,
        "days": [0],
        "priority": 1,
        "energy": "medium",
        "start": "08:00",
        "category": "School",
    }


def save_week(client: TestClient, title: str, week_start: str, revision: int):
    return client.put(
        "/api/week",
        json={"week_start": week_start, "blocks": [school(title)], "revision": revision},
        headers=WRITE,
    )


def test_recovery_status_counts_the_codes_of_the_signed_in_account(app: FastAPI, clients: ExitStack) -> None:
    anonymous = browser(app, clients)
    assert anonymous.get("/api/auth/recovery-status").status_code == 401
    assert anonymous.get("/api/auth/recovery-status").json() == SIGN_IN
    alice, bob = browser(app, clients), browser(app, clients)
    codes = register(alice, "alice", PASSWORD_A)["recovery_codes"]
    register(bob, "bob", PASSWORD_B)
    assert len(codes) == 8
    assert alice.get("/api/auth/recovery-status").json() == {"remaining": 8}
    assert bob.get("/api/auth/recovery-status").json() == {"remaining": 8}
    # One account spends a code: only its own count drops.
    assert recover(browser(app, clients), "alice", codes[0]).status_code == 200
    assert alice.get("/api/auth/recovery-status").status_code == 401
    refreshed = sign_in(alice, "alice", PASSWORD_NEW)
    assert refreshed.status_code == 200
    assert alice.get("/api/auth/recovery-status").json() == {"remaining": 7}
    assert bob.get("/api/auth/recovery-status").json() == {"remaining": 8}


def test_recovering_spends_one_code_and_signs_out_only_that_account(
    app: FastAPI, database: Path, clients: ExitStack
) -> None:
    alice, alice_phone, bob = (browser(app, clients) for _ in range(3))
    alice_id = register(alice, "alice", PASSWORD_A)
    codes = alice_id["recovery_codes"]
    bob_id = register(bob, "bob", PASSWORD_B)
    assert sign_in(alice_phone, "alice", PASSWORD_A).status_code == 200
    # Bob holds a row with the same code hash as Alice's first code.
    with connect(database) as db:
        db.execute(
            "INSERT INTO recovery_codes(user_id, code_hash) VALUES (?, ?)",
            (bob_id["id"], hash_recovery_code(codes[0])),
        )
    stranger = browser(app, clients)
    for username, code in (
        ("alice", "WRONG-CODE-0000"),
        ("nobody", codes[0]),
        ("alice", bob_id["recovery_codes"][0]),
    ):
        failed = recover(stranger, username, code)
        assert failed.status_code == 401
        assert failed.json() == WRONG_CODE
    recovered = recover(stranger, "alice", codes[0])
    assert recovered.status_code == 200
    assert recovered.json() == {"id": alice_id["id"], "username": "alice"}
    assert stranger.get("/api/auth/me").json() == {"id": alice_id["id"], "username": "alice"}
    # Alice's other sessions are gone; Bob's is not.
    assert alice.get("/api/auth/me").status_code == 401
    assert alice_phone.get("/api/auth/me").status_code == 401
    assert bob.get("/api/auth/me").json() == {"id": bob_id["id"], "username": "bob"}
    # The code is spent for Alice, and Bob's own row with that hash is still his.
    assert stranger.get("/api/auth/recovery-status").json() == {"remaining": 7}
    assert bob.get("/api/auth/recovery-status").json() == {"remaining": 9}
    again = recover(browser(app, clients), "alice", codes[0])
    assert again.status_code == 401
    assert again.json() == WRONG_CODE
    # Alice's password changed and Bob's did not.
    assert sign_in(browser(app, clients), "alice", PASSWORD_A).json() == WRONG_LOGIN
    assert sign_in(browser(app, clients), "alice", PASSWORD_NEW).status_code == 200
    assert sign_in(browser(app, clients), "bob", PASSWORD_B).status_code == 200
    assert sign_in(browser(app, clients), "bob", PASSWORD_NEW).status_code == 401


def test_a_password_check_reads_the_signed_in_accounts_hash(app: FastAPI, clients: ExitStack) -> None:
    anonymous = browser(app, clients)
    alice, bob, bob_phone = (browser(app, clients) for _ in range(3))
    register(alice, "alice", PASSWORD_A)
    first = register(bob, "bob", PASSWORD_B)["recovery_codes"]
    assert sign_in(bob_phone, "bob", PASSWORD_B).status_code == 200
    assert (
        anonymous.post("/api/auth/recovery-codes", json={"password": PASSWORD_B}, headers=WRITE).status_code
        == 401
    )
    # Alice's password does not open Bob's account.
    wrong = bob.post("/api/auth/recovery-codes", json={"password": PASSWORD_A}, headers=WRITE)
    assert wrong.status_code == 401
    assert wrong.json() == WRONG_PASSWORD
    fresh = bob.post("/api/auth/recovery-codes", json={"password": PASSWORD_B}, headers=WRITE)
    assert fresh.status_code == 200
    assert fresh.json()["remaining"] == 8
    assert len(fresh.json()["recovery_codes"]) == 8
    assert set(fresh.json()["recovery_codes"]).isdisjoint(first)
    assert bob.get("/api/auth/recovery-status").json() == {"remaining": 8}
    assert alice.get("/api/auth/recovery-status").json() == {"remaining": 8}
    # The old codes no longer work; Alice's were not touched.
    assert recover(anonymous, "bob", first[0]).json() == WRONG_CODE

    wrong = bob.post(
        "/api/auth/password",
        json={"current_password": PASSWORD_A, "new_password": PASSWORD_NEW},
        headers=WRITE,
    )
    assert (wrong.status_code, wrong.json()) == (401, WRONG_PASSWORD)
    same = bob.post(
        "/api/auth/password",
        json={"current_password": PASSWORD_B, "new_password": PASSWORD_B},
        headers=WRITE,
    )
    assert (same.status_code, same.json()) == (422, {"detail": "New password must be different"})
    changed = bob.post(
        "/api/auth/password",
        json={"current_password": PASSWORD_B, "new_password": PASSWORD_NEW},
        headers=WRITE,
    )
    assert changed.status_code == 200
    assert bob.get("/api/auth/me").json() == changed.json()
    assert bob_phone.get("/api/auth/me").status_code == 401
    assert alice.get("/api/auth/me").json()["username"] == "alice"
    assert sign_in(browser(app, clients), "bob", PASSWORD_B).status_code == 401
    assert sign_in(browser(app, clients), "bob", PASSWORD_NEW).status_code == 200
    assert sign_in(browser(app, clients), "alice", PASSWORD_A).status_code == 200


def test_deleting_an_account_asks_for_its_password_and_leaves_the_other(
    app: FastAPI, clients: ExitStack
) -> None:
    alice, bob = browser(app, clients), browser(app, clients)
    register(alice, "alice", PASSWORD_A)
    register(bob, "bob", PASSWORD_B)
    for client, title in ((alice, "Alice school"), (bob, "Bob school")):
        assert (
            client.put(
                "/api/assignments/hw", json=assignment(title, 60, "2026-09-15T23:59"), headers=WRITE
            ).status_code
            == 200
        )
        assert save_week(client, title, WEEK_1, 0).status_code == 200
    wrong = bob.request("DELETE", "/api/auth/account", json={"password": PASSWORD_A}, headers=WRITE)
    assert (wrong.status_code, wrong.json()) == (401, WRONG_PASSWORD)
    assert bob.get("/api/auth/me").status_code == 200
    removed = bob.request("DELETE", "/api/auth/account", json={"password": PASSWORD_B}, headers=WRITE)
    assert removed.status_code == 204
    assert bob.get("/api/auth/me").status_code == 401
    assert sign_in(browser(app, clients), "bob", PASSWORD_B).json() == WRONG_LOGIN
    assert alice.get("/api/auth/me").status_code == 200
    assert alice.get(f"/api/week?week_start={WEEK_1}").json()["blocks"][0]["title"] == "Alice school"
    assert [
        item["title"] for item in alice.get(f"/api/assignments?week_start={WEEK_1}").json()["assignments"]
    ] == ["Alice school"]
    # The name is free again, and the new account starts empty.
    again = browser(app, clients)
    register(again, "bob", PASSWORD_B)
    assert again.get(f"/api/week?week_start={WEEK_1}").json() == {
        "week_start": WEEK_1,
        "blocks": [],
        "revision": 0,
    }
    assert again.get(f"/api/assignments?week_start={WEEK_1}").json() == {"assignments": []}


def test_weeks_assignments_day_and_month_reads_stay_with_their_account(
    app: FastAPI, clients: ExitStack
) -> None:
    alice, bob = browser(app, clients), browser(app, clients)
    register(alice, "alice", PASSWORD_A)
    register(bob, "bob", PASSWORD_B)
    # Same ids and the same week in both accounts; revisions and contents differ.
    assert save_week(alice, "Alice school", WEEK_1, 0).status_code == 200
    assert save_week(alice, "Alice school, later", WEEK_1, 1).json()["revision"] == 2
    assert save_week(alice, "Alice again", WEEK_2, 0).status_code == 200
    assert save_week(bob, "Bob school", WEEK_1, 0).json()["revision"] == 1
    assert (
        alice.put(
            "/api/assignments/hw", json=assignment("Alice essay", 120, "2026-09-15T23:59"), headers=WRITE
        ).status_code
        == 200
    )
    assert (
        bob.put(
            "/api/assignments/hw", json=assignment("Bob lab", 60, "2026-09-22T12:00"), headers=WRITE
        ).status_code
        == 200
    )

    week_a = alice.get(f"/api/week?week_start={WEEK_1}").json()
    week_b = bob.get(f"/api/week?week_start={WEEK_1}").json()
    assert (week_a["revision"], [b["title"] for b in week_a["blocks"]]) == (2, ["Alice school, later"])
    assert (week_b["revision"], [b["title"] for b in week_b["blocks"]]) == (1, ["Bob school"])
    assert bob.get(f"/api/week?week_start={WEEK_2}").json() == {
        "week_start": WEEK_2,
        "blocks": [],
        "revision": 0,
    }
    assert alice.get("/api/weeks").json() == {"weeks": [WEEK_1, WEEK_2]}
    assert bob.get("/api/weeks").json() == {"weeks": [WEEK_1]}
    assert browser(app, clients).get("/api/weeks").json() == SIGN_IN

    listed_a = alice.get(f"/api/assignments?week_start={WEEK_1}").json()["assignments"]
    listed_b = bob.get(f"/api/assignments?week_start={WEEK_1}").json()["assignments"]
    assert [(item["title"], item["estimate_min"]) for item in listed_a] == [("Alice essay", 120)]
    assert [(item["title"], item["estimate_min"]) for item in listed_b] == [("Bob lab", 60)]

    # Monday 14 September: Alice's essay is due the next day, Bob's lab a week later.
    day_a = alice.get("/api/day?date=2026-09-14").json()
    day_b = bob.get("/api/day?date=2026-09-14").json()
    assert [item["title"] for item in day_a["due_soon"]] == ["Alice essay"]
    assert day_b["due_soon"] == []
    assert [block["title"] for block in day_a["locked"]] == ["Alice school, later"]
    assert [block["title"] for block in day_b["locked"]] == ["Bob school"]
    assert day_a["next_action"] == {"kind": "plan", "assignment_id": "hw"}
    assert day_b["next_action"] == {"kind": "add"}
    # Tuesday has no school block of Bob's, and Bob's week 2 is empty.
    assert bob.get("/api/day?date=2026-09-21").json()["locked"] == []
    assert [block["title"] for block in alice.get("/api/day?date=2026-09-21").json()["locked"]] == [
        "Alice again"
    ]

    month_a = alice.get("/api/month?month=2026-09").json()
    month_b = bob.get("/api/month?month=2026-09").json()
    assert [day["date"] for day in month_a["days"] if day["due_ids"]] == ["2026-09-15"]
    assert [day["date"] for day in month_b["days"] if day["due_ids"]] == ["2026-09-22"]
    assert [item["title"] for item in month_a["deadlines"]] == ["Alice essay"]
    assert [item["title"] for item in month_b["deadlines"]] == ["Bob lab"]
    locked_a = {day["date"]: day["locked_count"] for day in month_a["days"] if day["locked_count"]}
    locked_b = {day["date"]: day["locked_count"] for day in month_b["days"] if day["locked_count"]}
    assert locked_a == {"2026-09-14": 1, "2026-09-21": 1}
    assert locked_b == {"2026-09-14": 1}

    # Spreading reads the caller's own assignment: 120 minutes in two hours for Alice, one for Bob.
    spread = {"session_min": 60, "from_date": "2026-09-14"}
    spread_a = alice.post("/api/assignments/hw/spread", json=spread, headers=WRITE).json()
    spread_b = bob.post("/api/assignments/hw/spread", json=spread, headers=WRITE).json()
    assert [session["duration_min"] for session in spread_a["sessions"]] == [60, 60]
    assert [session["duration_min"] for session in spread_b["sessions"]] == [60]
    assert (spread_a["remaining_min"], spread_b["remaining_min"]) == (0, 0)
    assert (
        browser(app, clients).post("/api/assignments/hw/spread", json=spread, headers=WRITE).status_code
        == 401
    )
    ghost = alice.post("/api/assignments/nothing/spread", json=spread, headers=WRITE)
    assert (ghost.status_code, ghost.json()) == (404, {"detail": "Assignment not found"})
    done = assignment("Alice essay", 120, "2026-09-15T23:59", revision=1)
    done.update(completed=True, completed_at="2026-09-14T16:00")
    assert alice.put("/api/assignments/hw", json=done, headers=WRITE).status_code == 200
    closed = alice.post("/api/assignments/hw/spread", json=spread, headers=WRITE)
    assert (closed.status_code, closed.json()) == (422, {"detail": "completed assignments cannot be spread"})
    assert bob.post("/api/assignments/hw/spread", json=spread, headers=WRITE).status_code == 200


def test_the_planner_uses_the_callers_availability_and_not_anothers(app: FastAPI, clients: ExitStack) -> None:
    alice, bob = browser(app, clients), browser(app, clients)
    register(alice, "alice", PASSWORD_A)
    register(bob, "bob", PASSWORD_B)
    prefs = alice.get("/api/preferences").json()
    # Alice's day ends at 06:15; Bob has no cutoff.
    assert (
        alice.put("/api/preferences", json={**prefs, "day_cutoff": "06:15"}, headers=WRITE).status_code == 200
    )
    homework = {
        "id": "hw",
        "title": "Homework",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0],
        "priority": 3,
        "energy": "high",
    }

    def end_minute(client: TestClient) -> int:
        solved = client.post("/api/solve", json={"blocks": [homework]}, headers=WRITE)
        assert solved.status_code == 200, solved.text
        placed = next(block for block in solved.json()["placed"] if block["id"] == "hw")
        hour, minute = map(int, placed["start"].split(":"))
        return hour * 60 + minute + int(placed["duration_min"])

    assert end_minute(alice) <= 6 * 60 + 15
    assert end_minute(bob) > 6 * 60 + 15
    assert bob.get("/api/preferences").json().get("day_cutoff") is None
    assert (
        browser(app, clients).post("/api/solve", json={"blocks": [homework]}, headers=WRITE).status_code
        == 401
    )


def test_restore_points_with_the_same_id_stay_with_their_account(
    app: FastAPI, database: Path, clients: ExitStack
) -> None:
    alice, bob = browser(app, clients), browser(app, clients)
    register(alice, "alice", PASSWORD_A)
    bob_id = register(bob, "bob", PASSWORD_B)["id"]
    assert save_week(alice, "Alice school", WEEK_1, 0).status_code == 200
    assert save_week(bob, "Bob school", WEEK_1, 0).status_code == 200
    point_a = alice.post(
        "/api/restore-points", json={"label": "Alice", "operation_id": "op-1"}, headers=WRITE
    ).json()
    # Bob's point has the same id as Alice's but a different label, and it holds no weeks at all.
    with connect(database) as db:
        db.execute(
            "INSERT INTO restore_points(user_id, id, label, created_at, weeks_count, assignments_count, body)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bob_id, point_a["id"], "Bob", "2026-09-14T08:00", 0, 0, '{"weeks":[],"assignments":[]}'),
        )
    listed_a = alice.get("/api/restore-points").json()["restore_points"]
    listed_b = bob.get("/api/restore-points").json()["restore_points"]
    assert [(item["id"], item["label"]) for item in listed_a] == [(point_a["id"], "Alice")]
    assert listed_b == [
        {"id": point_a["id"], "label": "Bob", "created_at": "2026-09-14T08:00", "weeks": 0, "assignments": 0}
    ]
    preview = bob.get(f"/api/restore-points/{point_a['id']}/preview").json()
    assert preview["id"] == point_a["id"]
    # Bob's point holds no weeks, so his one week would go; Alice's point would only change hers.
    assert preview["changes"] == {
        "weeks": {"added": [], "changed": [], "removed": [WEEK_1]},
        "assignments": {"added": [], "changed": [], "removed": []},
    }
    state = preview["state_token"]
    restored = bob.post(
        f"/api/restore-points/{point_a['id']}/restore",
        json={"state_token": state, "operation_id": "op-bob"},
        headers=WRITE,
    )
    assert restored.status_code == 200, restored.text
    assert bob.get(f"/api/week?week_start={WEEK_1}").json() == {
        "week_start": WEEK_1,
        "blocks": [],
        "revision": 0,
    }
    assert alice.get(f"/api/week?week_start={WEEK_1}").json()["blocks"][0]["title"] == "Alice school"
    missing = alice.get("/api/restore-points/rp-nothing/preview")
    assert (missing.status_code, missing.json()) == (404, {"detail": "Restore point not found"})
