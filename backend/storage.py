from __future__ import annotations

import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import flexweek_engine  # type: ignore[import-untyped]

from backend.weeks import current_week_start

SESSION_SECONDS = 7 * 24 * 60 * 60
# Each account's preferences row records the last of these one-time changes it has had, so a change
# reaches every account once and a choice made after it is never undone by it.
# 1: reminders on (0.15). Setup never asked, so they were off for everyone who had not turned them on.
PREFS_VERSION = 1
ACCOUNT_TABLES = (
    "sessions",
    "weeks",
    "assignments",
    "routines",
    "restore_points",
    "operations",
    "preferences",
    "recovery_codes",
)


def digest(value: str) -> str:
    return flexweek_engine.digest(value)


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    return flexweek_engine.password_hash(password, salt)


def password_matches(password: str, encoded: str) -> bool:
    parts = encoded.split("$")
    if len(parts) < 2:
        raise IndexError("list index out of range")
    return flexweek_engine.password_matches(password, encoded)


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def new_preferences(db: sqlite3.Connection, user_id: int) -> None:
    """A new account's preferences, already past every one-time change. A table 0.14 created still
    defaults reminders to off, so they are set here rather than left to the column."""
    db.execute(
        "INSERT INTO preferences(user_id, reminders_enabled, prefs_version) VALUES (?, 1, ?)",
        (user_id, PREFS_VERSION),
    )


def initialize(path: Path) -> None:
    flexweek_engine.store_initialize(str(path), current_week_start())


def delete_account(db: sqlite3.Connection, user_id: int) -> None:
    for table in ACCOUNT_TABLES:
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))


def create_session(db: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.execute("DELETE FROM sessions WHERE expires <= ?", (now,))
    db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (digest(token), user_id, now + SESSION_SECONDS))
    return token


def throttle(path: Path, address: str, username: str) -> bool:
    return flexweek_engine.store_throttle(str(path), address, username, int(time.time()))
