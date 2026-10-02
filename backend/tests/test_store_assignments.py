"""Assignment rows are written by the Rust store on the caller's connection.

A failed insert in the same `connect()` must undo the earlier one: the Python
connection begins a transaction on the first write and rolls it back when the
block raises.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app import delete_assignment, upsert_assignment
from backend.models import AssignmentContent
from backend.storage import connect, initialize

CONFLICT = "This assignment changed in another window. Reload before saving."


def essay(title: str = "Essay") -> AssignmentContent:
    return AssignmentContent(
        id="hw-essay",
        title=title,
        priority=2,
        energy="low",
        due="2026-09-15T23:59",
        estimate_min=120,
    )


def account(tmp_path: Path) -> tuple[Path, int]:
    path = tmp_path / "week.sqlite"
    initialize(path)
    with connect(path) as db:
        db.execute("INSERT INTO users(username, password_hash) VALUES (?, ?)", ("ada", "x"))
        user_id = db.execute("SELECT id FROM users WHERE username = ?", ("ada",)).fetchone()["id"]
    return path, int(user_id)


def test_same_body_keeps_its_revision_and_a_stale_edit_writes_nothing(tmp_path: Path) -> None:
    path, user_id = account(tmp_path)
    with connect(path) as db:
        assert upsert_assignment(db, user_id, essay(), 0)["revision"] == 1
        assert upsert_assignment(db, user_id, essay(), 4)["revision"] == 1
        with pytest.raises(HTTPException) as caught:
            upsert_assignment(db, user_id, essay("Renamed"), 0)
        assert caught.value.status_code == 409
        assert caught.value.detail == CONFLICT
        row = db.execute(
            "SELECT body, revision FROM assignments WHERE user_id = ? AND id = ?",
            (user_id, "hw-essay"),
        ).fetchone()
        assert row["revision"] == 1
        assert "Renamed" not in row["body"]


def test_delete_drops_the_assignment_and_its_sessions(tmp_path: Path) -> None:
    path, user_id = account(tmp_path)
    with connect(path) as db:
        upsert_assignment(db, user_id, essay(), 0)
        db.execute(
            "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?, ?, ?, ?)",
            (
                user_id,
                "2026-09-14",
                '[{"assignment_id":"hw-essay","id":"w1"},{"id":"keep"}]',
                3,
            ),
        )
        deleted = delete_assignment(db, user_id, "hw-essay", 1)
        assert deleted["changed_weeks"] == [{"week_start": "2026-09-14", "revision": 4}]
        assert deleted["removed_sessions"]["2026-09-14"] == [
            {"assignment_id": "hw-essay", "id": "w1"}
        ]
        left = db.execute(
            "SELECT blocks, revision FROM weeks WHERE user_id = ? AND week_start = ?",
            (user_id, "2026-09-14"),
        ).fetchone()
        assert left["blocks"] == '[{"id":"keep"}]'
        assert left["revision"] == 4
        assert db.execute(
            "SELECT 1 FROM assignments WHERE user_id = ? AND id = ?",
            (user_id, "hw-essay"),
        ).fetchone() is None


def test_the_cap_counts_rows_already_stored(tmp_path: Path) -> None:
    path, user_id = account(tmp_path)
    with connect(path) as db:
        db.insert_assignment(user_id, "hw-essay", '{"id":"hw-essay"}')
        status, _revision = db.save_assignment(user_id, "hw-two", '{"id":"hw-two"}', 0, 1)
        assert status == "limit"
        assert db.assignment_exists(user_id, "hw-two") is False


def test_a_failed_insert_rolls_the_first_one_back(tmp_path: Path) -> None:
    path, user_id = account(tmp_path)
    with pytest.raises(sqlite3.IntegrityError), connect(path) as db:
        db.insert_assignment(user_id, "hw-essay", '{"id":"hw-essay"}')
        db.insert_assignment(user_id, "hw-essay", '{"id":"hw-essay"}')
    with connect(path) as db:
        assert db.count_assignments(user_id) == 0
