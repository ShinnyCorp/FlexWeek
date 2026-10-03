"""The store helpers against the Python helpers they replaced.

Each group runs one sequence of calls through the shipped helper (Rust store, on the app's
connection) and through the original Python helper (backend/tests/engine_ref/app_helpers.py, on
Python's own sqlite3 connection) on two databases started the same way. Return values, raised
errors and every row of every table must match. The rest are the HTTP and rollback cases the
move could have broken.
"""

from __future__ import annotations

import functools
import itertools
import json
import secrets
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend import app, storage
from backend.app import (
    AlarmPreference,
    Preferences,
    TransferSnapshot,
    create_app,
    replace_account,
)
from backend.models import AssignmentContent, Routine, TimeBlock
from backend.storage import connect, initialize
from backend.tests.engine_ref import app_helpers
from backend.tests.engine_ref import storage as ref_storage

PASSWORD = "a-long-test-password"
WRITE = {"X-FlexWeek-Request": "1", "Origin": "http://testserver"}
WEEK_A = "2026-09-07"
WEEK_B = "2026-09-14"
WEEK_C = "2026-09-21"
NOW = 1_000_000
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

Step = Callable[["Kit", Any], object]


class Kit:
    """One side of a comparison: a connection opener and the helpers that run on it."""

    def __init__(
        self,
        label: str,
        opener: Callable[[Path], Any],
        modules: tuple[ModuleType, ...],
        shims: dict[str, Callable[..., object]] | None = None,
    ) -> None:
        self.label = label
        self.opener = opener
        self.modules = modules
        self.shims = shims or {}

    def __getattr__(self, name: str) -> Any:
        if name in self.shims:
            return self.shims[name]
        for module in self.modules:
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(name)


# The store prunes through the connection; the app no longer wraps it, so the shipped side calls
# the connection method with the limit the app passes.
NEW = Kit(
    "new",
    connect,
    (app, storage),
    shims={
        "prune_restore_points": lambda db, user_id, keep_ids: db.prune_restore_points(
            user_id, list(keep_ids), app.MAX_RESTORE_POINTS
        ),
        "prune_operations": lambda db, user_id: db.prune_operations(user_id, app.MAX_OPERATIONS),
    },
)
REF = Kit("ref", ref_storage.connect, (app_helpers, ref_storage))


class Pins:
    """Tokens, the wall-clock stamp and the clock, restarted for each side so both draw the same values.

    The stamp only moves when a step ticks it: the shipped helper reads it a little earlier than the
    original did, which a free-running counter would show as a difference.
    """

    def __init__(self) -> None:
        self.tokens = itertools.count(1)
        self.minute = 0

    def reset(self) -> None:
        self.tokens = itertools.count(1)
        self.minute = 0


@pytest.fixture()
def pins(monkeypatch: pytest.MonkeyPatch) -> Pins:
    pinned = Pins()

    def stamp() -> str:
        return f"2026-09-14T10:{pinned.minute:02d}"

    monkeypatch.setattr(secrets, "token_hex", lambda nbytes=32: f"{next(pinned.tokens):0{2 * nbytes}x}")
    monkeypatch.setattr(secrets, "token_urlsafe", lambda nbytes=32: f"token-{next(pinned.tokens):06d}")
    monkeypatch.setattr(app, "naive_now", stamp)
    monkeypatch.setattr(app_helpers, "naive_now", stamp)
    clock = SimpleNamespace(time=lambda: NOW)
    monkeypatch.setattr(storage, "time", clock)
    monkeypatch.setattr(ref_storage, "time", clock)
    return pinned


def limit(monkeypatch: pytest.MonkeyPatch, **values: int) -> None:
    for name, value in values.items():
        monkeypatch.setattr(app, name, value)
        monkeypatch.setattr(app_helpers, name, value)


def call(name: str, *args: object) -> Step:
    return lambda kit, db: getattr(kit, name)(db, *args)


def outcome(step: Callable[[], object]) -> tuple[Any, ...]:
    try:
        value = step()
    except HTTPException as error:
        return ("http", error.status_code, error.detail)
    except Exception as error:
        return ("raised", type(error), str(error))
    return ("ok", value, json.dumps(value, default=repr))


def seed_users(db: Any) -> None:
    for user_id, name in ((1, "ada"), (2, "bob"), (3, "cy")):
        db.execute("INSERT INTO users(id, username, password_hash) VALUES (?, ?, 'x')", (user_id, name))
    for user_id in (1, 2):
        db.execute(
            "INSERT INTO preferences(user_id, reminders_enabled, prefs_version) VALUES (?, 1, 1)", (user_id,)
        )


def dump(path: Path) -> dict[str, list[tuple]]:
    plain = sqlite3.connect(path)
    try:
        return {table: plain.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in TABLES}
    finally:
        plain.close()


def replay(
    tmp_path: Path,
    pins: Pins,
    kit: Kit,
    seed: Callable[[Any], None],
    steps: list[Step],
    rollback_on_error: bool,
) -> tuple[list[tuple[Any, ...]], dict[str, list[tuple]]]:
    pins.reset()
    path = tmp_path / f"{kit.label}.sqlite"
    initialize(path)
    results: list[tuple[Any, ...]] = []
    with kit.opener(path) as db:
        seed(db)
        for step in steps:
            result = outcome(functools.partial(step, kit, db))
            if rollback_on_error and result[0] != "ok":
                db.rollback()
            results.append(result)
    return results, dump(path)


def compare(
    tmp_path: Path,
    pins: Pins,
    steps: list[Step],
    *,
    seed: Callable[[Any], None] = seed_users,
    allowed: tuple[type[Exception], ...] = (),
    rollback_on_error: bool = False,
) -> list[tuple[Any, ...]]:
    """Run the steps on both sides and require the same results and the same rows. Returns the
    original's results so a test can also pin what they must be."""
    new_results, new_rows = replay(tmp_path, pins, NEW, seed, steps, rollback_on_error)
    ref_results, ref_rows = replay(tmp_path, pins, REF, seed, steps, rollback_on_error)
    assert new_results == ref_results
    assert new_rows == ref_rows
    surprises = [item for item in ref_results if item[0] == "raised" and not issubclass(item[1], allowed)]
    assert surprises == [], "a step failed for a reason the test did not expect"
    return ref_results


def essay(assignment_id: str = "hw-essay", title: str = "Essay") -> AssignmentContent:
    return AssignmentContent(
        id=assignment_id,
        title=title,
        priority=2,
        energy="low",
        due="2026-09-15T23:59",
        estimate_min=120,
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


def session_block(block_id: str, assignment_id: str) -> dict:
    return {"id": block_id, "assignment_id": assignment_id, "title": "Café", "days": [0]}


def tick(pins: Pins) -> Step:
    def run(_kit: Kit, _db: Any) -> None:
        pins.minute += 1

    return run


def commit(_kit: Kit, db: Any) -> None:
    db.commit()


def sql(statement: str, *rows: tuple) -> Step:
    def run(_kit: Kit, db: Any) -> None:
        for row in rows or ((),):
            db.execute(statement, row)

    return run


def test_weeks_save_list_and_capture_like_the_original(tmp_path: Path, pins: Pins) -> None:
    blocks = [{"id": "b1", "title": "Café ☕", "days": [0, 2], "estimate": 1.5}]
    other = [{"id": "b2", "title": "Gym", "days": [4]}]
    results = compare(
        tmp_path,
        pins,
        [
            call("save_week_row", 1, WEEK_A, blocks, 0),
            call("save_week_row", 1, WEEK_A, blocks, 0),
            call("save_week_row", 1, WEEK_A, other, 0),
            call("save_week_row", 1, WEEK_A, other, 1),
            call("save_week_row", 1, WEEK_B, other, 3),
            call("save_week_row", 2, WEEK_A, blocks, 0),
            call("save_week_row", 1, WEEK_C, [], 0),
            call("list_account_weeks", 1),
            call("list_account_weeks", 2),
            call("list_account_weeks", 3),
            call("capture_account", 1),
        ],
    )
    assert ("http", 409, "This week changed in another window. Reload before saving.") in results
    assert results[0][1] == (blocks, 1)
    assert results[3][1] == (other, 2)


def test_assignments_upsert_delete_and_adopt_like_the_original(
    tmp_path: Path, pins: Pins, monkeypatch: pytest.MonkeyPatch
) -> None:
    limit(monkeypatch, MAX_ASSIGNMENTS=3)
    legacy = TimeBlock.model_validate(
        {
            "id": "essay",
            "title": "Draft",
            "kind": "flexible",
            "duration_min": 90,
            "days": [0, 1],
            "priority": 2,
            "energy": "low",
            "course": "History",
            "latest": "Thursday 21:00",
        }
    )
    results = compare(
        tmp_path,
        pins,
        [
            call("upsert_assignment", 1, essay(), 0),
            call("upsert_assignment", 1, essay(), 5),
            call("upsert_assignment", 1, essay(title="Renamed"), 0),
            call("upsert_assignment", 1, essay(title="Renamed"), 1),
            call("upsert_assignment", 1, essay("hw-new"), 2),
            call("load_assignment_rows", 1, {"hw-essay", "missing"}),
            call("load_assignment_rows", 1, set()),
            call("adopt_legacy_deadlines", 1, WEEK_A, [legacy]),
            call("adopt_legacy_deadlines", 1, WEEK_A, [legacy]),
            call("upsert_assignment", 1, essay("hw-b"), 0),
            call("upsert_assignment", 1, essay("hw-c"), 0),
            call("save_week_row", 1, WEEK_A, [session_block("w1", "hw-essay"), {"id": "keep"}], 0),
            call("save_week_row", 1, WEEK_B, [session_block("w2", "hw-essay")], 0),
            call("delete_assignment", 1, "missing", 1),
            call("delete_assignment", 1, "hw-essay", 1),
            call("delete_assignment", 1, "hw-essay", 2),
            call("delete_assignment", 2, "hw-b", 1),
        ],
        allowed=(),
    )
    assert ("http", 409, CONFLICT) in results
    assert ("http", 422, "An account holds at most 1000 assignments") in results
    assert ("http", 404, "Assignment not found") in results


@pytest.mark.parametrize(
    "stored",
    [
        "{}",
        '""',
        '{"a":1}',
        '"abc"',
        "5",
        "1.5",
        "null",
        "true",
        "[1]",
        '["x"]',
        "[null]",
        "[[1]]",
        '[{"assignment_id":"hw"},"x"]',
        "not json",
        "",
    ],
)
def test_deleting_an_assignment_fails_on_a_corrupt_week_with_the_original_error_type(
    tmp_path: Path, pins: Pins, stored: str
) -> None:
    results = compare(
        tmp_path,
        pins,
        [
            call("upsert_assignment", 1, essay("hw"), 0),
            sql(
                "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?, ?, ?, ?)",
                (1, WEEK_A, '[{"assignment_id":"hw","id":"w1"}]', 1),
                (1, WEEK_B, stored, 1),
            ),
            call("delete_assignment", 1, "hw", 1),
        ],
        allowed=(AttributeError, TypeError, ValueError),
    )
    skipped = stored in ("{}", '""')
    assert (results[-1][0] == "ok") is skipped


def test_routines_upsert_delete_and_limit_like_the_original(
    tmp_path: Path, pins: Pins, monkeypatch: pytest.MonkeyPatch
) -> None:
    limit(monkeypatch, MAX_ROUTINES=3)
    results = compare(
        tmp_path,
        pins,
        [
            call("upsert_routine", 1, routine("r1", "Morning")),
            tick(pins),
            call("upsert_routine", 1, routine("r1", "Morning", revision=7)),
            call("upsert_routine", 1, routine("r1", "Evening")),
            call("upsert_routine", 1, routine("r1", "Evening", revision=1)),
            tick(pins),
            call("upsert_routine", 1, routine("r2", "Evening", title="Other")),
            call("upsert_routine", 2, routine("r1", "Bob's")),
            call("upsert_routine", 1, routine("r3", "Café")),
            call("upsert_routine", 1, routine("r4", "Fourth")),
            call("delete_routine", 1, "r9", 1),
            call("delete_routine", 1, "r1", 1),
            call("delete_routine", 1, "r1", 2),
            call("delete_routine", 1, "r1", 2),
            call("capture_transfer", 1),
        ],
        allowed=(AssertionError,),
    )
    assert ("http", 409, "This routine changed in another window. Reload before saving.") in results
    assert ("http", 422, "An account holds at most 50 routines") in results
    assert ("http", 404, "Routine not found") in results


def test_preferences_and_transfer_like_the_original(tmp_path: Path, pins: Pins) -> None:
    chosen = Preferences(
        theme="nocturne",
        reminders_enabled=False,
        reminder_lead_min=15,
        timer_work_min=45,
        default_spotify_url="https://open.spotify.com/track/abc123",
        alarms=[AlarmPreference(id="a1", name="Wake ☀", time="07:30", days=[0, 1])],
        alert_volume=40,
        accent="gold",
    )
    snapshot = TransferSnapshot.model_validate(
        {
            "format": 3,
            "exported_at": "2026-09-14T10:00",
            "username": "ada",
            "weeks": [{"week_start": WEEK_A, "revision": 4, "blocks": [session("w1")]}],
            "assignments": [
                {"id": "hw-essay", "revision": 2, "body": essay().model_dump()},
            ],
            "preferences": Preferences(theme="slate").model_dump(),
            "routines": [
                {
                    **routine("r-b", "Zed", revision=3).model_dump(),
                    "created_at": "2026-09-01T09:00",
                    "updated_at": "2026-09-02T09:00",
                },
                {
                    **routine("r-a", "Zed", revision=1).model_dump(),
                    "created_at": "2026-09-01T09:00",
                    "updated_at": "2026-09-02T09:00",
                },
            ],
        }
    )
    results = compare(
        tmp_path,
        pins,
        [
            call("new_preferences", 3),
            call("write_preferences", 1, chosen),
            call("write_preferences", 3, Preferences(theme="system")),
            call("write_preferences", 99, chosen),
            call("upsert_routine", 1, routine("r-c", "Amy")),
            call("capture_transfer", 1),
            call("apply_transfer", 1, snapshot),
            call("capture_transfer", 1),
            call("capture_transfer", 99),
        ],
        allowed=(AssertionError,),
    )
    assert results[-1] == ("raised", AssertionError, "")
    assert results[6][0] == "ok"


def test_restore_points_insert_and_prune_like_the_original(
    tmp_path: Path, pins: Pins, monkeypatch: pytest.MonkeyPatch
) -> None:
    limit(monkeypatch, MAX_RESTORE_POINTS=3)
    first = "rp-0000000000000001"
    old_rows = tuple(
        (1, f"old-{index}", f"Old {index}", "2026-09-01T09:00", 0, 0, "{}") for index in range(6)
    )
    results = compare(
        tmp_path,
        pins,
        [
            call("save_week_row", 1, WEEK_A, [{"id": "b1"}], 0),
            call("upsert_assignment", 1, essay(), 0),
            call("insert_restore_point", 1, "One", set()),
            call("insert_restore_point", 2, "Bob one", set()),
            call("insert_restore_point", 1, "Two", set()),
            call("insert_restore_point", 1, "Three", {first}),
            call("insert_restore_point", 1, "Four", {first}),
            call("insert_restore_point", 1, "Five", set()),
            call("insert_restore_point", 1, "Café", {first, "unknown"}),
            sql(
                "INSERT INTO restore_points(user_id, id, label, created_at, weeks_count,"
                " assignments_count, body) VALUES (?, ?, ?, ?, ?, ?, ?)",
                *old_rows,
            ),
            call("prune_restore_points", 1, {"old-0", "old-1"}),
            call("prune_restore_points", 1, set()),
            call("prune_restore_points", 3, set()),
        ],
    )
    assert results[2][1]["id"] == first
    assert results[2][1]["label"] == "One"


def test_operations_remember_recall_and_prune_like_the_original(
    tmp_path: Path, pins: Pins, monkeypatch: pytest.MonkeyPatch
) -> None:
    limit(monkeypatch, MAX_OPERATIONS=3)
    old_rows = tuple((1, f"old-{index}", "h", "{}") for index in range(5))
    results = compare(
        tmp_path,
        pins,
        [
            call("recall_operation", 1, "op1", "d1"),
            call("remember_operation", 1, "op1", "d1", {"b": 1, "a": "é"}),
            call("recall_operation", 1, "op1", "d1"),
            call("recall_operation", 1, "op1", "other"),
            call("recall_operation", 2, "op1", "d1"),
            call("remember_operation", 1, "op1", "d1", {"again": True}),
            call("remember_operation", 2, "op1", "d2", {"bob": 1}),
            call("remember_operation", 1, "op2", "d2", {"n": 2}),
            call("remember_operation", 1, "op3", "d3", {"n": 3}),
            call("remember_operation", 1, "op4", "d4", {"n": 4}),
            call("remember_operation", 1, "op5", "d5", {"n": 5}),
            call("recall_operation", 1, "op1", "d1"),
            call("recall_operation", 1, "op5", "d5"),
            sql(
                "INSERT INTO operations(user_id, operation_id, payload_hash, response) VALUES (?, ?, ?, ?)",
                *old_rows,
            ),
            call("prune_operations", 1),
            call("prune_operations", 3),
        ],
        allowed=(sqlite3.IntegrityError,),
    )
    assert ("http", 409, "This operation was already used with different data.") in results
    assert (
        "raised",
        sqlite3.IntegrityError,
        "UNIQUE constraint failed: operations.user_id, operations.operation_id",
    ) in results
    assert results[2][1] == {"a": "é", "b": 1}


def test_replace_account_matches_the_original_including_a_failure_after_the_deletes(
    tmp_path: Path, pins: Pins
) -> None:
    def week(start: str, revision: int) -> dict:
        return {"week_start": start, "blocks": [session_block("w1", "hw-a")], "revision": revision}

    def item(item_id: str, revision: int) -> dict:
        return {"id": item_id, "body": essay(item_id).model_dump(), "revision": revision}

    results = compare(
        tmp_path,
        pins,
        [
            call("save_week_row", 1, WEEK_C, [{"id": "old"}], 0),
            call("upsert_assignment", 1, essay("old"), 0),
            call("save_week_row", 2, WEEK_C, [{"id": "bob"}], 0),
            call("replace_account", 1, {"weeks": [week(WEEK_A, 4)], "assignments": [item("hw-a", 2)]}),
            call("replace_account", 1, {"weeks": [week(WEEK_A, 1), week(WEEK_A, 2)], "assignments": []}),
            call("replace_account", 1, {"weeks": [], "assignments": [item("x", 1), item("x", 2)]}),
            call("replace_account", 1, {"weeks": [week(WEEK_B, 9)], "assignments": [item("hw-b", 8)]}),
            call("replace_account", 1, {"weeks": [], "assignments": []}),
        ],
        allowed=(sqlite3.IntegrityError,),
    )
    assert results[3][1] == {
        "weeks": [{"week_start": WEEK_A, "revision": 4}],
        "assignments": [{"id": "hw-a", "revision": 2}],
    }
    assert [item[0] for item in results].count("raised") == 2


def test_replace_account_with_a_missing_field_fails_the_same_way_and_leaves_the_account(
    tmp_path: Path, pins: Pins
) -> None:
    broken = {"weeks": [{"week_start": WEEK_A, "blocks": []}], "assignments": []}
    results = compare(
        tmp_path,
        pins,
        [
            call("save_week_row", 1, WEEK_C, [{"id": "old"}], 0),
            commit,
            call("replace_account", 1, broken),
            call("list_account_weeks", 1),
        ],
        allowed=(KeyError,),
        rollback_on_error=True,
    )
    assert results[2] == ("raised", KeyError, "'revision'")
    assert results[3][1] == [(WEEK_C, [{"id": "old"}])]


def test_recovery_codes_replace_like_the_original(tmp_path: Path, pins: Pins) -> None:
    results = compare(
        tmp_path,
        pins,
        [
            sql("INSERT INTO recovery_codes(user_id, code_hash) VALUES (?, ?)", (2, "bobs")),
            call("replace_recovery_codes", 1, ["abcd-efgh", "ijkl-mnop"]),
            call("replace_recovery_codes", 1, ["qrst-uvwx"]),
            call("replace_recovery_codes", 1, ["ABCD-EFGH", "abcdefgh"]),
            call("replace_recovery_codes", 1, []),
            call("replace_recovery_codes", 1, ["one", "two", "three"]),
            call("replace_recovery_codes", 2, ["x"]),
        ],
        allowed=(sqlite3.IntegrityError,),
    )
    assert (
        "raised",
        sqlite3.IntegrityError,
        "UNIQUE constraint failed: recovery_codes.user_id, recovery_codes.code_hash",
    ) in results


def test_sessions_are_created_and_expired_ones_swept_like_the_original(tmp_path: Path, pins: Pins) -> None:
    results = compare(
        tmp_path,
        pins,
        [
            sql(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                ("expired", 1, NOW - 1),
                ("boundary", 2, NOW),
                ("live", 2, NOW + 10),
            ),
            call("create_session", 1),
            call("create_session", 2),
            call("create_session", 99),
        ],
        allowed=(sqlite3.IntegrityError,),
    )
    assert results[1][1] == "token-000001"
    assert results[-1] == ("raised", sqlite3.IntegrityError, "FOREIGN KEY constraint failed")


def test_delete_account_removes_every_table_of_that_account_only(tmp_path: Path, pins: Pins) -> None:
    def fill(_kit: Kit, db: Any) -> None:
        for user_id in (1, 2):
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (f"s{user_id}", user_id, NOW + 5))
            db.execute(
                "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?, ?, '[]', 1)",
                (user_id, WEEK_A),
            )
            db.execute(
                "INSERT INTO assignments(user_id, id, body, revision) VALUES (?, 'a', '{}', 1)", (user_id,)
            )
            db.execute(
                "INSERT INTO routines(user_id, id, name, body, revision, created_at, updated_at)"
                " VALUES (?, 'r', 'n', '[]', 1, 'c', 'u')",
                (user_id,),
            )
            db.execute(
                "INSERT INTO restore_points(user_id, id, label, created_at, weeks_count,"
                " assignments_count, body) VALUES (?, 'p', 'l', 'c', 0, 0, '{}')",
                (user_id,),
            )
            db.execute(
                "INSERT INTO operations(user_id, operation_id, payload_hash, response)"
                " VALUES (?, 'o', 'h', '{}')",
                (user_id,),
            )
            db.execute("INSERT INTO recovery_codes(user_id, code_hash) VALUES (?, 'c')", (user_id,))

    compare(
        tmp_path,
        pins,
        [fill, call("delete_account", 1), call("delete_account", 99), call("delete_account", 2)],
    )
    path = tmp_path / "new.sqlite"
    rows = dump(path)
    assert [row[0] for row in rows["users"]] == [3]
    assert all(rows[table] == [] for table in TABLES if table != "users")


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
