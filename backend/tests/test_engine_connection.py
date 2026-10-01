"""The Rust connection against Python's sqlite3, on generated scripts of statements.

`backend.storage.connect` is the Rust connection; `backend.tests.engine_ref.storage.connect` is the
original, on Python's sqlite3. Results, errors, `in_transaction`, `lastrowid`, `rowcount` and the
tables must be equal after every statement. `AUDIT_EXAMPLES` sets how many scripts run.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend import storage as live
from backend.tests.engine_ref import storage as ref

N = int(os.environ.get("AUDIT_EXAMPLES", "300"))
SCHEMA = [
    "CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, n INTEGER, r REAL, b BLOB)",
    "CREATE TABLE weeks(user_id INTEGER NOT NULL REFERENCES users(id), week TEXT NOT NULL, body TEXT, PRIMARY KEY(user_id, week))",
]

name = st.sampled_from(["ada", "bo", "cy", "Ada", "émile", "", "a" * 40])
uid = st.integers(1, 4)
week = st.sampled_from(["2026-09-07", "2026-09-14"])
value = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(-5, 5),
    st.sampled_from([2**63 - 1, -(2**63), 2**63, -(2**63) - 1, 2**70]),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
    st.sampled_from(["", "x", "ünï", "a'b", "😀", "line\nbreak"]),
    st.sampled_from([b"", b"\x00\xff", b"abc"]),
)

statement = st.one_of(
    st.tuples(
        st.just("INSERT INTO users(username, n, r, b) VALUES (?, ?, ?, ?)"),
        st.tuples(name, value, value, value),
    ),
    st.tuples(st.just("insert into users(username) values (?)"), st.tuples(name)),
    st.tuples(st.just("\n        INSERT INTO users(username) VALUES (?)"), st.tuples(name)),
    st.tuples(st.just("INSERT OR IGNORE INTO users(username) VALUES (?)"), st.tuples(name)),
    st.tuples(
        st.just("REPLACE INTO weeks(user_id, week, body) VALUES (?, ?, ?)"), st.tuples(uid, week, value)
    ),
    st.tuples(
        st.just("INSERT INTO weeks(user_id, week, body) VALUES (?, ?, ?)"), st.tuples(uid, week, value)
    ),
    st.tuples(st.just("UPDATE users SET n = ? WHERE id = ?"), st.tuples(value, uid)),
    st.tuples(st.just("Update weeks SET body = ? WHERE user_id = ?"), st.tuples(value, uid)),
    st.tuples(st.just("DELETE FROM weeks WHERE user_id = ?"), st.tuples(uid)),
    st.tuples(st.just("DELETE FROM users WHERE id = ?"), st.tuples(uid)),
    st.tuples(st.just("SELECT * FROM users ORDER BY id"), st.just(())),
    st.tuples(st.just("SELECT COUNT(*) AS n FROM weeks WHERE user_id = ?"), st.tuples(uid)),
    st.tuples(st.just("SELECT id, username AS name, n, r, b FROM users WHERE username = ?"), st.tuples(name)),
    st.tuples(st.just("SELECT user_id, week, body FROM weeks ORDER BY user_id, week"), st.just(())),
    st.tuples(st.just("SELECT ?, ?"), st.tuples(value, value)),
    st.tuples(
        st.sampled_from(["BEGIN IMMEDIATE", "BEGIN", "COMMIT", "ROLLBACK", "begin immediate"]), st.just(())
    ),
    st.tuples(st.sampled_from(["SELEC 1", "SELECT * FROM nowhere", "DROP TABLE nowhere"]), st.just(())),
    st.tuples(
        st.sampled_from(
            [
                "-- add one\nINSERT INTO users(username) VALUES (?)",
                "/* add one */ INSERT INTO users(username) VALUES (?)",
            ]
        ),
        st.tuples(name),
    ),
    st.tuples(
        st.just("WITH picked(x) AS (SELECT ?) INSERT INTO users(username) SELECT x FROM picked"),
        st.tuples(name),
    ),
    st.tuples(
        st.sampled_from(["INSERT INTO nowhere VALUES (1)", "INSERT INTO users(username) VALUES ("]),
        st.just(()),
    ),
    st.tuples(st.just("INSERT INTO users(username) VALUES (?)"), st.sampled_from([(), ("a", "b")])),
    st.tuples(st.just("PRAGMA foreign_keys"), st.just(())),
    st.tuples(st.just("INSERT INTO users(username) VALUES (?) RETURNING id, username"), st.tuples(name)),
)
fetch = st.sampled_from(["none", "one", "all", "iterate", "one-then-all"])
step = st.one_of(
    st.tuples(st.just("run"), statement, fetch),
    st.tuples(st.just("run"), statement, fetch),
    st.just(("fail",)),
)
session = st.lists(step, min_size=1, max_size=7)
script = st.lists(session, min_size=1, max_size=4)


class Stop(Exception):
    pass


def shown(row):
    if row is None:
        return None
    keys = list(row.keys())
    return {
        "keys": keys,
        "values": [cell(item) for item in row],
        "by_name": [cell(row[key]) for key in keys],
        "first": cell(row[0]),
        "dict": {k: cell(v) for k, v in dict(row).items()},
    }


def cell(item):
    if isinstance(item, bytes):
        return {"bytes": item.hex()}
    if isinstance(item, float):
        return {"float": repr(item)}
    return item


def play(module, path: Path, sessions) -> list:
    log: list = []
    with module.connect(path) as db:
        for sql in SCHEMA:
            db.execute(sql)
    for steps in sessions:
        try:
            with module.connect(path) as db:
                for action in steps:
                    if action[0] == "fail":
                        raise Stop
                    _, (sql, params), how = action
                    entry: dict = {"sql": sql}
                    cursor = None  # a Python cursor left unread keeps its connection, and its lock, alive
                    try:
                        cursor = db.execute(sql, params)
                        if how == "one":
                            entry["rows"] = [shown(cursor.fetchone())]
                        elif how == "all":
                            entry["rows"] = [shown(row) for row in cursor.fetchall()]
                        elif how == "iterate":
                            entry["rows"] = [shown(row) for row in cursor]
                        elif how == "one-then-all":
                            entry["rows"] = [shown(cursor.fetchone())] + [
                                shown(row) for row in cursor.fetchall()
                            ]
                        if (
                            sql.lstrip().lower().startswith(("insert into users", "replace"))
                            and "RETURNING" not in sql
                        ):
                            entry["lastrowid"] = cursor.lastrowid
                        entry["rowcount"] = cursor.rowcount
                    except Exception as error:  # noqa: BLE001
                        entry["error"] = [type(error).__module__ + "." + type(error).__name__, str(error)]
                    except BaseException as error:  # noqa: BLE001
                        entry["error"] = ["BASE " + type(error).__name__, str(error)]
                    entry["in_transaction"] = db.in_transaction
                    cursor = None
                    log.append(entry)
        except Stop:
            log.append("session failed")
        except Exception as error:  # noqa: BLE001
            log.append(["session error", type(error).__module__ + "." + type(error).__name__, str(error)])
        check = sqlite3.connect(path)
        log.append(
            {
                "users": [[cell(x) for x in row] for row in check.execute("SELECT * FROM users ORDER BY id")],
                "weeks": [
                    [cell(x) for x in row]
                    for row in check.execute("SELECT * FROM weeks ORDER BY user_id, week")
                ],
            }
        )
        check.close()
    return log


COUNTER = iter(range(10**9))


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    return tmp_path_factory.mktemp("connection")


@settings(max_examples=N, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
@given(script)
def test_scripts_run_the_same_on_both_connections(folder, sessions):
    n = next(COUNTER)
    a, b = folder / f"live-{n}.db", folder / f"ref-{n}.db"
    for path in (a, b):
        path.unlink(missing_ok=True)
    try:
        got, want = play(live, a, sessions), play(ref, b, sessions)
    finally:
        for path in (a, b):
            path.unlink(missing_ok=True)
            Path(str(path) + "-journal").unlink(missing_ok=True)
    if got != want:
        for index, (left, right) in enumerate(zip(got, want, strict=False)):
            if left != right:
                raise AssertionError(
                    f"step {index} differs\n  script: {json.dumps(sessions, default=repr)[:1500]}\n  rust:   {json.dumps(left, default=repr)[:900]}\n  python: {json.dumps(right, default=repr)[:900]}"
                )
        raise AssertionError(f"lengths differ: {len(got)} vs {len(want)}")


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
