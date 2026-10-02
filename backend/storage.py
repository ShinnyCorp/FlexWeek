from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

import flexweek_engine  # type: ignore[import-untyped]

from backend.weeks import current_week_start as current_week_start

SESSION_SECONDS = 7 * 24 * 60 * 60
# Each account's preferences row records the last of these one-time changes it has had, so a change
# reaches every account once and a choice made after it is never undone by it.
# 1: reminders on (0.15). Setup never asked, so they were off for everyone who had not turned them on.
PREFS_VERSION = 1


def digest(value: str) -> str:
    return flexweek_engine.digest(value)


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    return flexweek_engine.password_hash(password, salt)


def password_matches(password: str, encoded: str) -> bool:
    return flexweek_engine.password_matches(password, encoded)


class Row(Protocol):
    def __getitem__(self, key: Any, /) -> Any: ...

    def __iter__(self) -> Iterator[Any]: ...

    def keys(self) -> list[str]: ...


class Cursor(Protocol):
    @property
    def lastrowid(self) -> int: ...

    # Any, as in typeshed: callers index the row of a query that cannot come back empty.
    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Row]: ...

    def __iter__(self) -> Iterator[Row]: ...


class Connection(Protocol):
    def execute(self, sql: str, parameters: Sequence[Any] = (), /) -> Cursor: ...

    def load_assignment_rows(
        self, user_id: int, ids: Sequence[str], /
    ) -> Sequence[tuple[str, str, int]]: ...

    def assignment_exists(self, user_id: int, assignment_id: str, /) -> bool: ...

    def count_assignments(self, user_id: int, /) -> int: ...

    def insert_assignment(self, user_id: int, assignment_id: str, body: str, /) -> None: ...

    def save_assignment(
        self, user_id: int, assignment_id: str, body: str, revision: int, max_count: int, /
    ) -> tuple[str, int]: ...

    def delete_assignment(
        self, user_id: int, assignment_id: str, revision: int, /
    ) -> tuple[str, str]: ...

    def adopt_legacy_deadlines(
        self,
        user_id: int,
        week_start: str,
        blocks: str,
        max_assignments: int,
        encode: Callable[[str], str],
        /,
    ) -> tuple[bool, str]: ...

    def require_own_assignments(
        self, user_id: int, ids: Sequence[str], /
    ) -> tuple[bool, Sequence[tuple[str, str, int]]]: ...

    def list_account_weeks(self, user_id: int, /) -> Sequence[tuple[str, str]]: ...

    def save_week(
        self, user_id: int, week_start: str, blocks: str, revision: int, /
    ) -> tuple[str, int]: ...

    def capture_account(self, user_id: int, /) -> str: ...

    def prune_restore_points(self, user_id: int, keep_ids: Sequence[str], keep: int, /) -> None: ...

    def prune_operations(self, user_id: int, keep: int, /) -> None: ...

    def recall_operation(
        self, user_id: int, operation_id: str, digest_value: str, /
    ) -> tuple[str, str]: ...

    def remember_operation(
        self, user_id: int, operation_id: str, digest_value: str, response: str, keep: int, /
    ) -> None: ...

    def insert_restore_point(
        self,
        user_id: int,
        point_id: str,
        label: str,
        created_at: str,
        weeks_count: int,
        assignments_count: int,
        body: str,
        keep_ids: Sequence[str],
        keep: int,
        /,
    ) -> None: ...

    def create_restore_point(
        self,
        user_id: int,
        token: str,
        label: str,
        created_at: str,
        keep_ids: Sequence[str],
        limit: int,
        /,
    ) -> str: ...

    def replace_account(
        self,
        user_id: int,
        weeks: Sequence[tuple[str, str, int]],
        assignments: Sequence[tuple[str, str, int]],
        /,
    ) -> None: ...

    def replace_recovery_codes(self, user_id: int, hashes: Sequence[str], /) -> None: ...

    def save_routine(
        self,
        user_id: int,
        routine_id: str,
        name: str,
        body: str,
        revision: int,
        stamp: str,
        max_count: int,
        /,
    ) -> tuple[str, str]: ...

    def delete_routine(self, user_id: int, routine_id: str, revision: int, /) -> str: ...

    def list_routines(self, user_id: int, /) -> str: ...

    def replace_routines(self, user_id: int, rows_json: str, /) -> None: ...

    def preference_row(self, user_id: int, /) -> str | None: ...

    def write_preferences(self, user_id: int, fields_json: str, /) -> None: ...

    def insert_preferences(self, user_id: int, prefs_version: int, /) -> None: ...

    def delete_account(self, user_id: int, /) -> None: ...

    def create_session_row(
        self, token_hash: str, user_id: int, expires: int, now: int, /
    ) -> None: ...

    def open_session(self, token: str, user_id: int, now: int, /) -> None: ...

    def begin_immediate(self, /) -> None: ...

    def begin(self, /) -> None: ...

    def enforce_foreign_keys(self, /) -> None: ...

    def session_user(self, token_hash: str, now: int, /) -> tuple[int, str] | None: ...

    def insert_user(self, username: str, password_hash: str, /) -> int: ...

    def find_user(self, username: str, /) -> tuple[int, str, str] | None: ...

    def password_hash_of(self, user_id: int, /) -> str | None: ...

    def delete_session(self, token_hash: str, /) -> None: ...

    def recovery_hashes(self, user_id: int, /) -> list[str]: ...

    def count_recovery_codes(self, user_id: int, /) -> int: ...

    def use_recovery_code(self, user_id: int, code_hash: str, /) -> None: ...

    def rotate_password(self, user_id: int, new_hash: str, /) -> None: ...

    def read_week(self, user_id: int, week_start: str, /) -> tuple[str, int] | None: ...

    def week_blocks(self, user_id: int, week_start: str, /) -> str | None: ...

    def week_starts(self, user_id: int, /) -> list[str]: ...

    def assignment_body(self, user_id: int, assignment_id: str, /) -> str | None: ...

    def assignment_bodies(self, user_id: int, /) -> list[tuple[str, int]]: ...

    def list_assignment_rows(self, user_id: int, /) -> list[tuple[str, str, int]]: ...

    def list_restore_points(self, user_id: int, /) -> str: ...

    def restore_point_body(self, user_id: int, point_id: str, /) -> tuple[str, str] | None: ...

    def availability_json(self, user_id: int, /) -> str | None: ...


@contextmanager
def connect(path: Path) -> Iterator[Connection]:
    """The Rust store's connection. Python's sqlite3 is not opened on this file."""
    db = flexweek_engine.open_connection(str(path))
    try:
        with db:
            yield db
    finally:
        db.close()


def new_preferences(db: Connection, user_id: int) -> None:
    """A new account's preferences, already past every one-time change. A table 0.14 created still
    defaults reminders to off, so they are set here rather than left to the column."""
    db.insert_preferences(user_id, PREFS_VERSION)


def initialize(path: Path) -> None:
    flexweek_engine.store_initialize_today(str(path))


def delete_account(db: Connection, user_id: int) -> None:
    db.delete_account(user_id)


def create_session(db: Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.open_session(token, user_id, now)
    return token


def throttle(path: Path, address: str, username: str) -> bool:
    return flexweek_engine.store_throttle(str(path), address, username, int(time.time()))
