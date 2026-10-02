"""The Rust connection against Python's sqlite3, on the same statements."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import flexweek_engine  # type: ignore[import-untyped]
import pytest

from backend.storage import connect, initialize, throttle


def _script(db, statements: list[tuple[str, tuple]]) -> list[tuple[bool, object]]:
    seen: list[tuple[bool, object]] = []
    for sql, params in statements:
        try:
            cursor = db.execute(sql, params) if params else db.execute(sql)
            try:
                row = cursor.fetchone()
            except Exception:
                row = None
            seen.append((db.in_transaction, None if row is None else tuple(row)))
        except Exception as error:
            seen.append((db.in_transaction, f"{type(error).__name__}:{error}"))
    return seen


def test_statement_kinds_start_a_transaction_only_for_writes(tmp_path: Path) -> None:
    statements = [
        ("CREATE TABLE t(id INTEGER PRIMARY KEY, name TEXT)", ()),
        ("SELECT 1", ()),
        ("PRAGMA user_version", ()),
        ("INSERT INTO t(name) VALUES ('a')", ()),
        ("UPDATE t SET name = 'b'", ()),
        ("DELETE FROM t", ()),
    ]
    py = sqlite3.connect(tmp_path / "py.db")
    rust = flexweek_engine.open_connection(str(tmp_path / "rust.db"))
    try:
        assert _script(py, statements) == _script(rust, statements)
    finally:
        py.close()
        rust.close()


def test_a_failed_later_write_rolls_the_earlier_ones_back(tmp_path: Path) -> None:
    path = tmp_path / "reg.db"
    with connect(path) as db:
        db.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
    with pytest.raises(sqlite3.IntegrityError), connect(path) as db:
        db.execute("INSERT INTO users(name) VALUES ('a')")
        db.execute("INSERT INTO users(name) VALUES ('b')")
        db.execute("INSERT INTO users(name) VALUES ('a')")
    with connect(path) as db:
        assert db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0


def test_begin_immediate_commits_or_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "tx.db"
    with connect(path) as db:
        db.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, name TEXT)")
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO t(name) VALUES ('kept')")
    with connect(path) as db:
        assert db.execute("SELECT name FROM t").fetchone()["name"] == "kept"
    with pytest.raises(sqlite3.IntegrityError), connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO t(id, name) VALUES (1, 'x')")
        db.execute("INSERT INTO t(id, name) VALUES (1, 'y')")
    with connect(path) as db:
        names = [row["name"] for row in db.execute("SELECT name FROM t")]
    assert names == ["kept"]


def test_another_thread_cannot_use_the_connection(tmp_path: Path) -> None:
    db = flexweek_engine.open_connection(str(tmp_path / "thr.db"))
    seen: list[str] = []

    def other() -> None:
        try:
            db.execute("SELECT 1")
        except sqlite3.ProgrammingError as error:
            seen.append(str(error))

    thread = threading.Thread(target=other)
    thread.start()
    thread.join()
    db.close()
    assert seen and "same thread" in seen[0]


def test_values_match_python_sqlite(tmp_path: Path) -> None:
    py = sqlite3.connect(tmp_path / "py.db")
    py.row_factory = sqlite3.Row
    rust = flexweek_engine.open_connection(str(tmp_path / "rust.db"))
    for db in (py, rust):
        db.execute("CREATE TABLE t(n INTEGER, r REAL, s TEXT, b BLOB)")
        db.execute("INSERT INTO t VALUES (?, ?, ?, ?)", (True, None, "hi", b"xy"))
    py_row = py.execute("SELECT * FROM t").fetchone()
    rust_row = rust.execute("SELECT * FROM t").fetchone()
    assert rust_row["n"] == py_row["n"] == 1
    assert rust_row[0] == 1
    assert rust_row["r"] is None and rust_row["s"] == "hi" and rust_row["b"] == b"xy"
    assert dict(rust_row) == dict(py_row)
    for db in (py, rust):
        with pytest.raises(OverflowError, match="Python int too large to convert to SQLite INTEGER"):
            db.execute("INSERT INTO t(n) VALUES (?)", (2**63,))
        with pytest.raises(sqlite3.ProgrammingError, match="Incorrect number of bindings supplied"):
            db.execute("SELECT ?", ())
        with pytest.raises(sqlite3.OperationalError) as caught:
            db.execute("SELEKT 1")
        assert isinstance(caught.value, sqlite3.DatabaseError)
    py.close()
    rust.close()


def test_foreign_key_and_lastrowid(tmp_path: Path) -> None:
    path = tmp_path / "fk.db"
    with connect(path) as db:
        db.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")
        db.execute("CREATE TABLE weeks(user_id INTEGER REFERENCES users(id), week_start TEXT)")
        cursor = db.execute("INSERT INTO users(name) VALUES ('ada')")
        assert cursor.lastrowid == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO weeks(user_id, week_start) VALUES (9, '2026-09-07')")


def test_fetch_and_iteration_and_a_row_after_close(tmp_path: Path) -> None:
    path = tmp_path / "rows.db"
    with connect(path) as db:
        db.execute("CREATE TABLE t(n INTEGER)")
        db.execute("INSERT INTO t VALUES (1)")
        db.execute("INSERT INTO t VALUES (2)")
        cursor = db.execute("SELECT n FROM t ORDER BY n")
        assert [row["n"] for row in cursor] == [1, 2]
        assert db.execute("SELECT n FROM t WHERE n = 3").fetchone() is None
        kept = db.execute("SELECT n FROM t WHERE n = 1").fetchone()
    assert kept["n"] == 1


def test_initialize_again_does_not_wipe_the_file(tmp_path: Path) -> None:
    path = tmp_path / "keep.db"
    initialize(path)
    with connect(path) as db:
        db.execute("INSERT INTO users(username, password_hash) VALUES ('ada', 'x')")
    initialize(path)
    with connect(path) as db:
        assert db.execute("SELECT username FROM users").fetchone()["username"] == "ada"


def test_a_held_write_lock_makes_throttle_wait(tmp_path: Path) -> None:
    path = tmp_path / "lock.db"
    initialize(path)
    holder = flexweek_engine.open_connection(str(path))
    holder.execute("BEGIN IMMEDIATE")
    beats: list[int] = []
    flag = {"stop": False}

    def beat() -> None:
        while not flag["stop"]:
            beats.append(1)
            time.sleep(0.05)

    thread = threading.Thread(target=beat)
    thread.start()
    started = time.perf_counter()
    with pytest.raises(sqlite3.OperationalError):
        throttle(path, "10.0.0.1", "ada")
    waited = time.perf_counter() - started
    flag["stop"] = True
    thread.join()
    holder.rollback()
    holder.close()
    assert waited >= 5
    assert len(beats) >= 10
