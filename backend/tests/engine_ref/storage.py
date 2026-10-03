from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from backend.tests.engine_ref.assignments import migrate_blocks
from backend.tests.engine_ref.weeks import current_week_start

SESSION_SECONDS = 7 * 24 * 60 * 60
PREFERENCES_TABLE = """
    CREATE TABLE IF NOT EXISTS preferences (
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        theme TEXT NOT NULL DEFAULT 'system' CHECK(theme IN ('system', 'slate', 'nocturne')),
        reminders_enabled INTEGER NOT NULL DEFAULT 1
            CHECK(reminders_enabled IN (0, 1)),
        reminder_lead_min INTEGER NOT NULL DEFAULT 5
            CHECK(reminder_lead_min >= 0 AND reminder_lead_min <= 120),
        reminder_sound INTEGER NOT NULL DEFAULT 1
            CHECK(reminder_sound IN (0, 1)),
        reminder_dnd_override INTEGER NOT NULL DEFAULT 0
            CHECK(reminder_dnd_override IN (0, 1)),
        timer_work_min INTEGER NOT NULL DEFAULT 30,
        timer_break_min INTEGER NOT NULL DEFAULT 15,
        timer_long_break_min INTEGER NOT NULL DEFAULT 30,
        timer_long_break_every INTEGER NOT NULL DEFAULT 4,
        auto_split_pomodoro INTEGER NOT NULL DEFAULT 0
            CHECK(auto_split_pomodoro IN (0, 1)),
        default_spotify_url TEXT,
        alarms_json TEXT NOT NULL DEFAULT '[]',
        availability_json TEXT NOT NULL DEFAULT '{}',
        comfort_json TEXT NOT NULL DEFAULT '{}',
        prefs_version INTEGER NOT NULL DEFAULT 0
    )
"""
# Each account's preferences row records the last of these one-time changes it has had, so a change
# reaches every account once and a choice made after it is never undone by it.
# 1: reminders on (0.15). Setup never asked, so they were off for everyone who had not turned them on.
PREFS_VERSION = 1
WEEKS_TABLE = """
    CREATE TABLE IF NOT EXISTS weeks (
        user_id INTEGER NOT NULL REFERENCES users(id), week_start TEXT NOT NULL,
        blocks TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, week_start)
    )
"""
ASSIGNMENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS assignments (
        user_id INTEGER NOT NULL REFERENCES users(id), id TEXT NOT NULL,
        body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, id)
    )
"""
ROUTINES_TABLE = """
    CREATE TABLE IF NOT EXISTS routines (
        user_id INTEGER NOT NULL REFERENCES users(id), id TEXT NOT NULL,
        name TEXT NOT NULL, body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, id)
    )
"""
RESTORE_POINTS_TABLE = """
    CREATE TABLE IF NOT EXISTS restore_points (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        id TEXT NOT NULL,
        label TEXT NOT NULL,
        created_at TEXT NOT NULL,
        weeks_count INTEGER NOT NULL,
        assignments_count INTEGER NOT NULL,
        body TEXT NOT NULL,
        UNIQUE(user_id, id)
    )
"""
RECOVERY_CODES_TABLE = """
    CREATE TABLE IF NOT EXISTS recovery_codes (
        user_id INTEGER NOT NULL REFERENCES users(id),
        code_hash TEXT NOT NULL,
        PRIMARY KEY (user_id, code_hash)
    )
"""
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
OPERATIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS operations (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        operation_id TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        response TEXT NOT NULL,
        UNIQUE(user_id, operation_id)
    )
"""


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024, dklen=32
    )
    return f"scrypt$32768$8$3${salt}${key.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    return hmac.compare_digest(password_hash(password, encoded.split("$")[-2]), encoded)


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


def date_legacy_weeks(db: sqlite3.Connection) -> None:
    """Give pre-dated week rows the current week. Runs on every start, so it must be a no-op twice."""
    tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "weeks" not in tables:
        return
    columns = {row["name"] for row in db.execute("PRAGMA table_info('weeks')")}
    if "week_start" in columns:
        return
    # One transaction: a crash between the rename and the create would leave no weeks table at all.
    db.execute("BEGIN IMMEDIATE")
    db.execute("ALTER TABLE weeks RENAME TO weeks_legacy")
    db.execute(WEEKS_TABLE)
    db.execute(
        """INSERT INTO weeks(user_id, week_start, blocks, revision)
        SELECT user_id, ?, blocks, revision FROM weeks_legacy""",
        (current_week_start(),),
    )
    db.execute("DROP TABLE weeks_legacy")
    db.execute("COMMIT")


def migrate_preferences(db: sqlite3.Connection) -> None:
    """Add preference columns introduced after the original account schema."""
    cols = {row[1] for row in db.execute("PRAGMA table_info(preferences)").fetchall()}
    if "reminders_enabled" not in cols:
        db.execute("ALTER TABLE preferences ADD COLUMN reminders_enabled INTEGER NOT NULL DEFAULT 0")
    if "reminder_lead_min" not in cols:
        db.execute("ALTER TABLE preferences ADD COLUMN reminder_lead_min INTEGER NOT NULL DEFAULT 5")
    if "reminder_sound" not in cols:
        db.execute("ALTER TABLE preferences ADD COLUMN reminder_sound INTEGER NOT NULL DEFAULT 1")
    phase7_columns = {
        "reminder_dnd_override": "INTEGER NOT NULL DEFAULT 0",
        "timer_work_min": "INTEGER NOT NULL DEFAULT 30",
        "timer_break_min": "INTEGER NOT NULL DEFAULT 15",
        "timer_long_break_min": "INTEGER NOT NULL DEFAULT 30",
        "timer_long_break_every": "INTEGER NOT NULL DEFAULT 4",
        "auto_split_pomodoro": "INTEGER NOT NULL DEFAULT 0",
        "default_spotify_url": "TEXT",
        "alarms_json": "TEXT NOT NULL DEFAULT '[]'",
        "availability_json": "TEXT NOT NULL DEFAULT '{}'",
        "comfort_json": "TEXT NOT NULL DEFAULT '{}'",
        "prefs_version": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, declaration in phase7_columns.items():
        if name not in cols:
            db.execute(f"ALTER TABLE preferences ADD COLUMN {name} {declaration}")


def allow_system_theme(db: sqlite3.Connection) -> None:
    """Rebuild a preferences table whose CHECK predates the system theme. A no-op once rebuilt.

    SQLite cannot alter a CHECK constraint in place. Themes already chosen are
    kept; anything the old unconstrained schema allowed that is not a theme now
    becomes system.
    """
    row = db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'preferences'").fetchone()
    if row is None or "'system'" in row["sql"]:
        return
    kept = [
        name
        for name in (column["name"] for column in db.execute("PRAGMA table_info('preferences')"))
        if name != "theme"
    ]
    columns = ", ".join(kept)
    # One transaction: a crash between the rename and the copy would leave no preferences table.
    db.execute("BEGIN IMMEDIATE")
    db.execute("ALTER TABLE preferences RENAME TO preferences_legacy")
    db.execute(PREFERENCES_TABLE)
    db.execute(
        f"""INSERT INTO preferences(theme, {columns})
        SELECT CASE WHEN theme IN ('slate', 'nocturne') THEN theme ELSE 'system' END, {columns}
        FROM preferences_legacy"""
    )
    db.execute("DROP TABLE preferences_legacy")
    db.execute("COMMIT")


def upgrade_preferences(db: sqlite3.Connection) -> None:
    """Bring each account's preferences to PREFS_VERSION. A no-op once they are there."""
    db.execute("BEGIN IMMEDIATE")
    db.execute("UPDATE preferences SET reminders_enabled = 1, prefs_version = 1 WHERE prefs_version < 1")
    db.execute("COMMIT")


def new_preferences(db: sqlite3.Connection, user_id: int) -> None:
    """A new account's preferences, already past every one-time change. A table 0.14 created still
    defaults reminders to off, so they are set here rather than left to the column."""
    db.execute(
        "INSERT INTO preferences(user_id, reminders_enabled, prefs_version) VALUES (?, 1, ?)",
        (user_id, PREFS_VERSION),
    )


def migrate_assignments(db: sqlite3.Connection) -> None:
    """Turn leftover flexible blocks and pomodoro groups into assignments. A no-op on a second start."""
    tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "weeks" not in tables:
        return
    db.execute("BEGIN IMMEDIATE")
    rows = db.execute("SELECT user_id, week_start, blocks FROM weeks").fetchall()
    for row in rows:
        blocks = json.loads(row["blocks"])
        updated, created = migrate_blocks(row["week_start"], blocks)
        for body in created:
            db.execute(
                """INSERT INTO assignments(user_id, id, body, revision) VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, id) DO NOTHING""",
                (row["user_id"], body["id"], json.dumps(body, sort_keys=True, separators=(",", ":"))),
            )
        if updated != blocks:
            db.execute(
                "UPDATE weeks SET blocks = ? WHERE user_id = ? AND week_start = ?",
                (
                    json.dumps(updated, sort_keys=True, separators=(",", ":")),
                    row["user_id"],
                    row["week_start"],
                ),
            )
    db.execute("COMMIT")


def initialize(path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    with connect(path) as db:
        db.executescript(f"""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                expires INTEGER NOT NULL
            );
            {WEEKS_TABLE};
            {ASSIGNMENTS_TABLE};
            {ROUTINES_TABLE};
            {RESTORE_POINTS_TABLE};
            {OPERATIONS_TABLE};
            {PREFERENCES_TABLE};
            {RECOVERY_CODES_TABLE};
            CREATE TABLE IF NOT EXISTS auth_attempts (
                key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL
            );
        """)
        date_legacy_weeks(db)
        migrate_preferences(db)
        allow_system_theme(db)
        upgrade_preferences(db)
        migrate_assignments(db)


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
    now = int(time.time())
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM auth_attempts WHERE expires <= ?", (now,))
        for key, limit in ((digest("ip:" + address), 30), (digest("user:" + username), 10)):
            row = db.execute("SELECT count FROM auth_attempts WHERE key = ?", (key,)).fetchone()
            if row and row["count"] >= limit:
                return False
        for key in (digest("ip:" + address), digest("user:" + username)):
            db.execute(
                """INSERT INTO auth_attempts VALUES (?, 1, ?)
                ON CONFLICT(key) DO UPDATE SET count = count + 1""",
                (key, now + 300),
            )
    return True
