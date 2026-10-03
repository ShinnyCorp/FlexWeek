"""The Rust connection: a rolled-back register, the error classes, and plain file names."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend import storage as live


def test_a_register_that_fails_part_way_leaves_no_account(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import backend.app as app_module

    path = tmp_path / "accounts.db"
    app = app_module.create_app(database=path, origin="http://testserver")

    def boom(*args, **kwargs):
        raise RuntimeError("recovery codes failed")

    monkeypatch.setattr(app_module, "replace_recovery_codes", boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/auth/register",
            json={"username": "ada", "password": "a-long-test-password"},
            headers={"Origin": "http://testserver", "X-FlexWeek-Request": "1"},
        )
    assert response.status_code == 500, response.text
    check = sqlite3.connect(path)
    assert check.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0, "a user row was left behind"
    assert check.execute("SELECT COUNT(*) FROM preferences").fetchone()[0] == 0
    check.close()


def garbage(path: Path) -> None:
    path.write_bytes(b"this is not a database\n" * 400)


def users_table(path: Path) -> None:
    check = sqlite3.connect(path)
    check.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT UNIQUE)")
    check.execute("INSERT INTO users(username) VALUES ('ada')")
    check.commit()
    check.close()


def damaged(path: Path) -> None:
    check = sqlite3.connect(path)
    check.execute("CREATE TABLE t(a INTEGER PRIMARY KEY, b TEXT)")
    check.executemany("INSERT INTO t(b) VALUES (?)", [("x" * 100,)] * 200)
    check.commit()
    check.close()
    data = bytearray(path.read_bytes())
    data[4096 : 4096 + 64] = b"\xff" * 64
    path.write_bytes(bytes(data))


def outcome(path: Path, sql: str):
    try:
        with live.connect(path) as db:
            db.execute(sql).fetchall()
    except Exception as error:  # noqa: BLE001
        return [type(error).__module__ + "." + type(error).__name__, str(error)]
    return ["ok"]


@pytest.mark.parametrize(
    ("prepare", "sql", "kind"),
    [
        (garbage, "SELECT * FROM sqlite_master", "sqlite3.DatabaseError"),
        (garbage, "CREATE TABLE t(a)", "sqlite3.DatabaseError"),
        (users_table, "INSERT INTO users(username) VALUES ('ada')", "sqlite3.IntegrityError"),
        (users_table, "INSERT INTO users(id) VALUES ('not a number')", "sqlite3.IntegrityError"),
        (users_table, "SELECT zeroblob(2000000000)", "sqlite3.DataError"),
        (damaged, "SELECT * FROM t", "sqlite3.DatabaseError"),
        (users_table, "SELECT * FROM nowhere", "sqlite3.OperationalError"),
    ],
    ids=[
        "not-a-database",
        "not-a-database-write",
        "duplicate-key",
        "datatype-mismatch",
        "too-big",
        "corrupt",
        "no-table",
    ],
)
def test_errors_map_to_the_classes_sqlite3_raises(tmp_path, prepare, sql, kind):
    prepare(tmp_path / "live.db")
    got = outcome(tmp_path / "live.db", sql)
    assert got[0] == kind, got


def test_a_path_that_starts_with_file_colon_is_a_plain_file_name(tmp_path, monkeypatch):
    name = "file:planner.db?mode=memory"
    monkeypatch.chdir(tmp_path)
    with live.connect(Path(name)) as db:
        db.execute("CREATE TABLE t(a)")
        db.execute("INSERT INTO t VALUES (1)")
    with live.connect(Path(name)) as db:
        rows = [list(row) for row in db.execute("SELECT a FROM t")]
    # The store always opens a plain file, whatever the name looks like.
    assert sorted(path.name for path in tmp_path.iterdir()) == [name]
    assert rows == [[1]]
