import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.assignments import (
    legacy_session,
    planned_minutes_by_id,
    prepare_solve,
    rewrite_session,
    unplanned_minutes,
)
from backend.availability import occupancy_from_windows, spread_sessions
from backend.comfort import REMINDER_LIMITS, TIMER_PRESETS, preview_split
from backend.day import build_day
from backend.limits import MAX_BODY
from backend.models import (
    Assignment,
    AssignmentContent,
    ProtectedWindow,
    Routine,
    SolveRequest,
    SpreadRequest,
    StudyWindow,
    TimeBlock,
    WeekRequest,
    WorkWindow,
    due_sort_key,
    valid_naive_stamp,
    valid_spotify_url,
)
from backend.month import build_month
from backend.recovery import (
    RECOVERY_CODE_COUNT,
    generate_recovery_codes,
    hash_recovery_code,
    recovery_code_matches,
)
from backend.restore import canonical, diff_snapshots, diff_transfer, state_token
from backend.slots import DAY_END_MIN, SLOT_MIN
from backend.solver import reschedule_after_miss, reschedule_running_late, solve
from backend.storage import (
    SESSION_SECONDS,
    connect,
    create_session,
    delete_account,
    digest,
    initialize,
    new_preferences,
    password_hash,
    password_matches,
    throttle,
)
from backend.transfer import TRANSFER_TOO_LARGE, transfer_fits
from backend.weeks import (
    current_week_start,
    is_calendar_date,
    is_month_label,
    is_week_start,
    monday_of,
)

ROOT = Path(__file__).resolve().parent.parent
COOKIE = "flexweek_session"
WEEK_START_RULE = "week_start must be a Monday from 2000-01-03 through 2099-12-28, or 1999-12-27"
DATE_RULE = "date must be YYYY-MM-DD between 2000-01-01 and 2099-12-31"
MONTH_RULE = "month must be YYYY-MM between 2000-01 and 2099-12"
ASSIGNMENT_UNKNOWN = "assignment_id must name an assignment of this account"
ASSIGNMENT_CONFLICT = "This assignment changed in another window. Reload before saving."
ASSIGNMENT_LIMIT = "An account holds at most 1000 assignments"
WEEK_CONFLICT = "This week changed in another window. Reload before saving."
ROUTINE_CONFLICT = "This routine changed in another window. Reload before saving."
ROUTINE_LIMIT = "An account holds at most 50 routines"
ROUTINE_UNKNOWN = "Routine not found"
RESTORE_UNKNOWN = "Restore point not found"
RESTORE_STALE = "This preview is out of date. Refresh it before restoring."
IMPORT_STALE = "This preview is out of date. Refresh it before importing."
RECOVER_WRONG = "Incorrect username or recovery code"
PASSWORD_WRONG = "Incorrect password"
PASSWORD_SAME = "New password must be different"
OPERATION_CONFLICT = "This operation was already used with different data."
MAX_ASSIGNMENTS = 1000
MAX_ROUTINES = 50
MAX_RESTORE_POINTS = 20
MAX_OPERATIONS = 100


def encode_assignment(content: AssignmentContent) -> str:
    return json.dumps(content.model_dump(), sort_keys=True, separators=(",", ":"))


def assignment_ids_of(blocks: list[TimeBlock]) -> set[str]:
    return {block.assignment_id for block in blocks if block.assignment_id}


def load_assignment_rows(db: sqlite3.Connection, user_id: int, ids: set[str]) -> dict[str, tuple[str, int]]:
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT id, body, revision FROM assignments WHERE user_id = ? AND id IN ({placeholders})",
        (user_id, *ids),
    ).fetchall()
    return {row["id"]: (row["body"], row["revision"]) for row in rows}


def load_assignment_bodies(db: sqlite3.Connection, user_id: int, ids: set[str]) -> dict[str, dict]:
    loaded = load_assignment_rows(db, user_id, ids)
    return {key: json.loads(body) for key, (body, _revision) in loaded.items()}


def require_own_assignments(db: sqlite3.Connection, user_id: int, ids: set[str]) -> dict[str, dict]:
    found = load_assignment_bodies(db, user_id, ids)
    if found.keys() != ids:
        raise HTTPException(422, ASSIGNMENT_UNKNOWN)
    return found


def adopt_legacy_deadlines(
    db: sqlite3.Connection, user_id: int, week_start: str, blocks: list[TimeBlock]
) -> list[TimeBlock]:
    adopted: list[TimeBlock] = []
    created: list[dict] = []
    for block in blocks:
        if block.kind != "flexible" or block.assignment_id or not block.latest:
            adopted.append(block)
            continue
        session, body = legacy_session(week_start, block)
        exists = db.execute(
            "SELECT 1 FROM assignments WHERE user_id = ? AND id = ?", (user_id, body["id"])
        ).fetchone()
        if exists is None:
            created.append(body)
        adopted.append(session)
    if created:
        count = db.execute("SELECT COUNT(*) AS n FROM assignments WHERE user_id = ?", (user_id,)).fetchone()
        if int(count["n"]) + len(created) > MAX_ASSIGNMENTS:
            raise HTTPException(422, ASSIGNMENT_LIMIT)
        for body in created:
            db.execute(
                "INSERT INTO assignments(user_id, id, body, revision) VALUES (?, ?, ?, 1)",
                (user_id, body["id"], encode_assignment(AssignmentContent.model_validate(body))),
            )
    return adopted


def rewrite_blocks(blocks: list[TimeBlock], assignments: dict[str, dict]) -> list[TimeBlock]:
    rewritten: list[TimeBlock] = []
    for block in blocks:
        if block.assignment_id:
            rewritten.append(rewrite_session(block, assignments[block.assignment_id]))
        else:
            rewritten.append(block)
    return rewritten


def rewrite_stored_blocks(blocks: list[dict], assignments: dict[str, dict]) -> list[dict]:
    rewritten: list[dict] = []
    for raw in blocks:
        aid = raw.get("assignment_id")
        if not aid or aid not in assignments:
            rewritten.append(raw)
            continue
        rewritten.append(rewrite_session(TimeBlock.model_validate(raw), assignments[aid]).model_dump())
    return rewritten


def dump_blocks(blocks: list[TimeBlock]) -> list[dict]:
    return [block.model_dump() for block in blocks]


def list_account_weeks(db: sqlite3.Connection, user_id: int) -> list[tuple[str, list[dict]]]:
    rows = db.execute("SELECT week_start, blocks FROM weeks WHERE user_id = ?", (user_id,)).fetchall()
    return [(row["week_start"], json.loads(row["blocks"])) for row in rows]


def assignment_view(body: dict, revision: int, planned: int) -> dict:
    return {
        **body,
        "revision": revision,
        "planned_min": planned,
        "unplanned_min": unplanned_minutes(int(body["estimate_min"]), int(body["focus_minutes"]), planned),
    }


def upsert_assignment(
    db: sqlite3.Connection, user_id: int, content: AssignmentContent, revision: int
) -> dict:
    encoded = encode_assignment(content)
    row = db.execute(
        "SELECT body, revision FROM assignments WHERE user_id = ? AND id = ?", (user_id, content.id)
    ).fetchone()
    stored, stored_revision = (row["body"], row["revision"]) if row else (None, 0)
    if stored == encoded:
        return {**content.model_dump(), "revision": stored_revision}
    if revision != stored_revision:
        raise HTTPException(409, ASSIGNMENT_CONFLICT)
    if stored is None:
        count = db.execute("SELECT COUNT(*) AS n FROM assignments WHERE user_id = ?", (user_id,)).fetchone()
        if int(count["n"]) >= MAX_ASSIGNMENTS:
            raise HTTPException(422, ASSIGNMENT_LIMIT)
        db.execute(
            "INSERT INTO assignments(user_id, id, body, revision) VALUES (?, ?, ?, 1)",
            (user_id, content.id, encoded),
        )
        return {**content.model_dump(), "revision": 1}
    db.execute(
        "UPDATE assignments SET body = ?, revision = revision + 1 WHERE user_id = ? AND id = ?",
        (encoded, user_id, content.id),
    )
    return {**content.model_dump(), "revision": revision + 1}


def delete_assignment(db: sqlite3.Connection, user_id: int, assignment_id: str, revision: int) -> dict:
    row = db.execute(
        "SELECT revision FROM assignments WHERE user_id = ? AND id = ?", (user_id, assignment_id)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Assignment not found")
    if revision != row["revision"]:
        raise HTTPException(409, ASSIGNMENT_CONFLICT)
    weeks = db.execute(
        "SELECT week_start, blocks, revision FROM weeks WHERE user_id = ? ORDER BY week_start",
        (user_id,),
    ).fetchall()
    changed_weeks: list[dict] = []
    removed_sessions: dict[str, list[dict]] = {}
    for week in weeks:
        blocks = json.loads(week["blocks"])
        kept = [block for block in blocks if block.get("assignment_id") != assignment_id]
        removed = [block for block in blocks if block.get("assignment_id") == assignment_id]
        if not removed:
            continue
        new_revision = week["revision"] + 1
        db.execute(
            "UPDATE weeks SET blocks = ?, revision = ? WHERE user_id = ? AND week_start = ?",
            (
                json.dumps(kept, sort_keys=True, separators=(",", ":")),
                new_revision,
                user_id,
                week["week_start"],
            ),
        )
        changed_weeks.append({"week_start": week["week_start"], "revision": new_revision})
        removed_sessions[week["week_start"]] = removed
    db.execute("DELETE FROM assignments WHERE user_id = ? AND id = ?", (user_id, assignment_id))
    return {"changed_weeks": changed_weeks, "removed_sessions": removed_sessions}


def save_week_row(
    db: sqlite3.Connection,
    user_id: int,
    week_start: str,
    blocks: list[dict],
    revision: int,
) -> tuple[list[dict], int]:
    encoded = json.dumps(blocks, sort_keys=True, separators=(",", ":"))
    row = db.execute(
        "SELECT blocks, revision FROM weeks WHERE user_id = ? AND week_start = ?",
        (user_id, week_start),
    ).fetchone()
    stored, stored_revision = (row["blocks"], row["revision"]) if row else ("[]", 0)
    if encoded == stored:
        return blocks, stored_revision
    if revision != stored_revision:
        raise HTTPException(409, WEEK_CONFLICT)
    db.execute(
        """INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id, week_start)
        DO UPDATE SET blocks = excluded.blocks, revision = revision + 1""",
        (user_id, week_start, encoded),
    )
    return blocks, revision + 1


def naive_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M")


def payload_digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def capture_account(db: sqlite3.Connection, user_id: int) -> dict:
    weeks = [
        {
            "week_start": row["week_start"],
            "blocks": json.loads(row["blocks"]),
            "revision": row["revision"],
        }
        for row in db.execute(
            "SELECT week_start, blocks, revision FROM weeks WHERE user_id = ? ORDER BY week_start",
            (user_id,),
        )
    ]
    assignments = [
        {"id": row["id"], "body": json.loads(row["body"]), "revision": row["revision"]}
        for row in db.execute(
            "SELECT id, body, revision FROM assignments WHERE user_id = ? ORDER BY id",
            (user_id,),
        )
    ]
    return {"weeks": weeks, "assignments": assignments}


def prune_restore_points(db: sqlite3.Connection, user_id: int, keep_ids: set[str]) -> None:
    rows = db.execute(
        "SELECT seq, id FROM restore_points WHERE user_id = ? ORDER BY seq ASC",
        (user_id,),
    ).fetchall()
    overflow = len(rows) - MAX_RESTORE_POINTS
    if overflow <= 0:
        return
    extras = [row for row in rows if row["id"] not in keep_ids]
    for row in extras[:overflow]:
        db.execute("DELETE FROM restore_points WHERE seq = ?", (row["seq"],))


def prune_operations(db: sqlite3.Connection, user_id: int) -> None:
    count = db.execute("SELECT COUNT(*) AS n FROM operations WHERE user_id = ?", (user_id,)).fetchone()
    extra = int(count["n"]) - MAX_OPERATIONS
    if extra <= 0:
        return
    db.execute(
        """DELETE FROM operations WHERE seq IN (
            SELECT seq FROM operations WHERE user_id = ? ORDER BY seq ASC LIMIT ?
        )""",
        (user_id, extra),
    )


def recall_operation(
    db: sqlite3.Connection, user_id: int, operation_id: str, digest_value: str
) -> dict | None:
    row = db.execute(
        """SELECT payload_hash, response FROM operations
        WHERE user_id = ? AND operation_id = ?""",
        (user_id, operation_id),
    ).fetchone()
    if row is None:
        return None
    if row["payload_hash"] != digest_value:
        raise HTTPException(409, OPERATION_CONFLICT)
    return json.loads(row["response"])


def remember_operation(
    db: sqlite3.Connection, user_id: int, operation_id: str, digest_value: str, response: dict
) -> None:
    db.execute(
        """INSERT INTO operations(user_id, operation_id, payload_hash, response)
        VALUES (?, ?, ?, ?)""",
        (user_id, operation_id, digest_value, canonical(response)),
    )
    prune_operations(db, user_id)


def restore_point_view(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "label": row["label"],
        "created_at": row["created_at"],
        "weeks": row["weeks_count"],
        "assignments": row["assignments_count"],
    }


def insert_restore_point(
    db: sqlite3.Connection, user_id: int, label: str, keep_ids: set[str] | None = None
) -> dict:
    snapshot = capture_account(db, user_id)
    point_id = "rp-" + secrets.token_hex(8)
    created_at = naive_now()
    db.execute(
        """INSERT INTO restore_points(
            user_id, id, label, created_at, weeks_count, assignments_count, body
        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            point_id,
            label,
            created_at,
            len(snapshot["weeks"]),
            len(snapshot["assignments"]),
            canonical(snapshot),
        ),
    )
    protected = set(keep_ids or ())
    protected.add(point_id)
    prune_restore_points(db, user_id, protected)
    return {
        "id": point_id,
        "label": label,
        "created_at": created_at,
        "weeks": len(snapshot["weeks"]),
        "assignments": len(snapshot["assignments"]),
    }


def replace_account(db: sqlite3.Connection, user_id: int, snapshot: dict) -> dict:
    db.execute("DELETE FROM weeks WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM assignments WHERE user_id = ?", (user_id,))
    weeks = []
    assignments = []
    for week in snapshot["weeks"]:
        db.execute(
            "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?, ?, ?, ?)",
            (user_id, week["week_start"], canonical(week["blocks"]), week["revision"]),
        )
        weeks.append({"week_start": week["week_start"], "revision": week["revision"]})
    for item in snapshot["assignments"]:
        db.execute(
            "INSERT INTO assignments(user_id, id, body, revision) VALUES (?, ?, ?, ?)",
            (user_id, item["id"], canonical(item["body"]), item["revision"]),
        )
        assignments.append({"id": item["id"], "revision": item["revision"]})
    return {"weeks": weeks, "assignments": assignments}


def replace_recovery_codes(db: sqlite3.Connection, user_id: int, codes: list[str]) -> None:
    db.execute("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
    for code in codes:
        db.execute(
            "INSERT INTO recovery_codes(user_id, code_hash) VALUES (?, ?)",
            (user_id, hash_recovery_code(code)),
        )


def encode_routine(routine: Routine) -> str:
    return canonical([block.model_dump() for block in routine.blocks])


def routine_view(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "blocks": json.loads(row["body"]),
        "revision": row["revision"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_routine(db: sqlite3.Connection, user_id: int, routine: Routine) -> dict:
    encoded = encode_routine(routine)
    row = db.execute(
        """SELECT id, name, body, revision, created_at, updated_at FROM routines
        WHERE user_id = ? AND id = ?""",
        (user_id, routine.id),
    ).fetchone()
    stored_revision = row["revision"] if row else 0
    if row is not None and row["name"] == routine.name and row["body"] == encoded:
        return routine_view(row)
    if routine.revision != stored_revision:
        raise HTTPException(409, ROUTINE_CONFLICT)
    stamp = naive_now()
    if row is None:
        count = db.execute("SELECT COUNT(*) AS n FROM routines WHERE user_id = ?", (user_id,)).fetchone()
        if int(count["n"]) >= MAX_ROUTINES:
            raise HTTPException(422, ROUTINE_LIMIT)
        db.execute(
            """INSERT INTO routines(user_id, id, name, body, revision, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (user_id, routine.id, routine.name, encoded, stamp, stamp),
        )
        stored = db.execute(
            """SELECT id, name, body, revision, created_at, updated_at FROM routines
            WHERE user_id = ? AND id = ?""",
            (user_id, routine.id),
        ).fetchone()
        assert stored is not None
        return routine_view(stored)
    db.execute(
        """UPDATE routines SET name = ?, body = ?, revision = revision + 1, updated_at = ?
        WHERE user_id = ? AND id = ?""",
        (routine.name, encoded, stamp, user_id, routine.id),
    )
    stored = db.execute(
        """SELECT id, name, body, revision, created_at, updated_at FROM routines
        WHERE user_id = ? AND id = ?""",
        (user_id, routine.id),
    ).fetchone()
    assert stored is not None
    return routine_view(stored)


def delete_routine(db: sqlite3.Connection, user_id: int, routine_id: str, revision: int) -> dict:
    row = db.execute(
        "SELECT revision FROM routines WHERE user_id = ? AND id = ?", (user_id, routine_id)
    ).fetchone()
    if row is None:
        raise HTTPException(404, ROUTINE_UNKNOWN)
    if revision != row["revision"]:
        raise HTTPException(409, ROUTINE_CONFLICT)
    db.execute("DELETE FROM routines WHERE user_id = ? AND id = ?", (user_id, routine_id))
    return {"id": routine_id}


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.lower()


class SavedWeek(WeekRequest):
    model_config = ConfigDict(extra="forbid")
    week_start: str
    revision: int = Field(ge=0, le=2**53 - 1)

    @field_validator("week_start")
    @classmethod
    def week_start_is_a_monday(cls, value: str) -> str:
        if not is_week_start(value):
            raise ValueError(WEEK_START_RULE)
        return value


class AssignmentChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    assignment: AssignmentContent | None
    revision: int = Field(ge=0, le=2**53 - 1)


class ChangesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weeks: list[SavedWeek] = Field(default_factory=list)
    assignments: list[AssignmentChange] = Field(default_factory=list)
    operation_id: str | None = Field(default=None, min_length=1, max_length=80)
    snapshot_label: str | None = Field(default=None, min_length=1, max_length=80)


class RestoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    operation_id: str = Field(min_length=1, max_length=80)

    @field_validator("label")
    @classmethod
    def label_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("label required")
        return value


class RestoreApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state_token: str = Field(min_length=1, max_length=128)
    operation_id: str = Field(min_length=1, max_length=80)


class AlarmPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    time: str = Field(pattern=r"(?:[01]\d|2[0-3]):[0-5]\d")
    days: list[int] = Field(min_length=1, max_length=7)
    enabled: bool = True
    sound: Literal["chime", "soft", "bright", "low", "glass", "spotify"] = "chime"
    spotify_url: str | None = Field(default=None, max_length=500)

    @field_validator("days")
    @classmethod
    def valid_days(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("alarm days must be unique values in 0..6")
        return sorted(value)

    _spotify_url = field_validator("spotify_url")(valid_spotify_url)


class SetupProgress(BaseModel):
    """Where first-run setup stands, so a skip or a finish is remembered and a quit resumes."""

    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1, le=100)
    step: int = Field(default=0, ge=0, le=20)
    finished_at: str | None = Field(default=None, max_length=32)

    @field_validator("finished_at")
    @classmethod
    def finished_at_is_a_timestamp(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", value):
            raise ValueError("finished_at must be YYYY-MM-DDTHH:MM")
        return value


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # "system" follows the device light/dark setting; slate is Light and nocturne is Dark.
    theme: Literal["system", "slate", "nocturne"]
    reminders_enabled: bool = True
    reminder_lead_min: int = Field(default=5, ge=0, le=120)
    reminder_sound: bool = True
    reminder_dnd_override: bool = False
    timer_work_min: int = Field(default=30, ge=1, le=180)
    timer_break_min: int = Field(default=15, ge=1, le=60)
    timer_long_break_min: int = Field(default=30, ge=1, le=120)
    timer_long_break_every: int = Field(default=4, ge=2, le=12)
    auto_split_pomodoro: bool = False
    default_spotify_url: str | None = Field(default=None, max_length=500)
    alarms: list[AlarmPreference] = Field(default_factory=list, max_length=20)
    protected: list[ProtectedWindow] = Field(
        default_factory=list, max_length=21, exclude_if=lambda value: not value
    )
    study_windows: list[StudyWindow] = Field(
        default_factory=list, max_length=21, exclude_if=lambda value: not value
    )
    work_windows: list[WorkWindow] = Field(
        default_factory=list, max_length=21, exclude_if=lambda value: not value
    )
    day_cutoff: str | None = Field(default=None, exclude_if=lambda value: value is None)
    alert_volume: int = Field(default=80, ge=0, le=100, exclude_if=lambda value: value == 80)
    end_chime: bool = Field(default=False, exclude_if=lambda value: value is False)
    tray_notifications: bool = Field(default=True, exclude_if=lambda value: value is True)
    start_at_login: bool = Field(default=False, exclude_if=lambda value: value is False)
    preferred_view: Literal["week", "day"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    sidebar_collapsed: bool = Field(default=False, exclude_if=lambda value: value is False)
    sidebar_width_px: int | None = Field(default=None, ge=200, le=640, exclude_if=lambda value: value is None)
    theme_pack: Literal["system", "light-frost", "dark-frost", "nocturne", "slate"] = Field(
        default="system", exclude_if=lambda value: value == "system"
    )
    accent: Literal["default", "sky", "gold", "sea", "sand"] = Field(
        default="default", exclude_if=lambda value: value == "default"
    )
    accent_chips: bool = Field(default=False, exclude_if=lambda value: value is False)
    motion: Literal["off", "normal", "extra", "reduce"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # One sound for reminders, the end of a focus session and new alarms. "spotify" plays
    # default_spotify_url instead.
    alarm_tone: Literal["chime", "soft", "bright", "low", "glass", "spotify"] = Field(
        default="chime", exclude_if=lambda value: value == "chime"
    )
    # How homework gets a time: as it is added, when Plan my homework is pressed, or by dragging.
    planning_style: Literal["auto", "suggest", "manual"] = Field(
        default="suggest", exclude_if=lambda value: value == "suggest"
    )
    # Minutes a dragged, resized or drawn block moves by. Typed times are any minute either way.
    drag_step_min: Literal[5, 15] = Field(default=5, exclude_if=lambda value: value == 5)
    # Times on screen as 16:00 or as 4:00 PM. Stored and sent as HH:MM either way.
    clock_24h: bool = Field(default=True, exclude_if=lambda value: value is True)
    setup: SetupProgress | None = Field(default=None, exclude_if=lambda value: value is None)

    _spotify_url = field_validator("default_spotify_url")(valid_spotify_url)

    @field_validator("day_cutoff")
    @classmethod
    def cutoff_is_on_the_grid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("day_cutoff must be HH:MM on the 15-minute grid")
        hour, minute = map(int, value.split(":"))
        start = hour * 60 + minute
        if minute % 15 or start < SLOT_MIN or start > DAY_END_MIN - SLOT_MIN:
            raise ValueError("day_cutoff must be between 00:15 and 23:45 on the 15-minute grid")
        return value

    @model_validator(mode="after")
    def protected_windows_do_not_overlap(self) -> Preferences:
        # Half-open [start, end) ranges, checked per day: touching windows and
        # windows on disjoint days are fine.
        for day in range(7):
            intervals: list[tuple[int, int]] = []
            for window in self.protected:
                if day not in window.days:
                    continue
                hour, minute = map(int, window.start.split(":"))
                start = hour * 60 + minute
                end = start + window.duration_min
                if any(start < other_end and other_start < end for other_start, other_end in intervals):
                    raise ValueError("protected windows must not overlap on a shared day")
                intervals.append((start, end))
        return self

    @model_validator(mode="after")
    def split_lengths_are_on_the_grid(self) -> Preferences:
        if not self.auto_split_pomodoro:
            return self
        for length in (self.timer_work_min, self.timer_break_min, self.timer_long_break_min):
            if length % 15:
                raise ValueError("auto_split_pomodoro needs 15-minute work and break lengths")
        return self

    @model_validator(mode="after")
    def pack_keeps_theme_on_its_axis(self) -> Preferences:
        if self.theme_pack == "system":
            return self
        axis = "slate" if self.theme_pack in {"light-frost", "slate"} else "nocturne"
        if self.theme != axis:
            raise ValueError("theme_pack needs theme on the same light or dark axis")
        return self


class PasswordConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=12, max_length=128)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=12, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class RecoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    code: str = Field(min_length=8, max_length=64)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.lower()


class TransferAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    body: AssignmentContent
    revision: int = Field(ge=0, le=2**53 - 1)

    @model_validator(mode="after")
    def assignment_ids_match(self) -> TransferAssignment:
        if self.id != self.body.id:
            raise ValueError("assignment id and body.id must match")
        return self


class TransferRoutine(Routine):
    created_at: str
    updated_at: str

    _stamps = field_validator("created_at", "updated_at")(valid_naive_stamp)


class TransferSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal[3]
    exported_at: str
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    weeks: list[SavedWeek]
    assignments: list[TransferAssignment] = Field(max_length=1000)
    preferences: Preferences
    routines: list[TransferRoutine] = Field(max_length=50)

    _exported_at = field_validator("exported_at")(valid_naive_stamp)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def snapshot_refs_are_consistent(self) -> TransferSnapshot:
        starts = [week.week_start for week in self.weeks]
        if len(set(starts)) != len(starts):
            raise ValueError("week_start values must be unique")
        assignment_ids = [item.id for item in self.assignments]
        if len(set(assignment_ids)) != len(assignment_ids):
            raise ValueError("assignment ids must be unique")
        routine_ids = [item.id for item in self.routines]
        if len(set(routine_ids)) != len(routine_ids):
            raise ValueError("routine ids must be unique")
        owned = set(assignment_ids)
        for week in self.weeks:
            for block in week.blocks:
                if block.assignment_id and block.assignment_id not in owned:
                    raise ValueError("assignment_id must name an assignment in this snapshot")
        return self


class TransferPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot: TransferSnapshot


class TransferApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot: TransferSnapshot
    state_token: str = Field(min_length=1, max_length=128)
    operation_id: str = Field(min_length=1, max_length=80)


def apply_transfer(db: sqlite3.Connection, user_id: int, snapshot: TransferSnapshot) -> dict:
    write_preferences(db, user_id, snapshot.preferences)
    db.execute("DELETE FROM routines WHERE user_id = ?", (user_id,))
    for routine in snapshot.routines:
        db.execute(
            """INSERT INTO routines(user_id, id, name, body, revision, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                routine.id,
                routine.name,
                encode_routine(routine),
                routine.revision,
                routine.created_at,
                routine.updated_at,
            ),
        )
    replaced = replace_account(
        db,
        user_id,
        {
            "weeks": [
                {
                    "week_start": week.week_start,
                    "blocks": dump_blocks(week.blocks),
                    "revision": week.revision,
                }
                for week in snapshot.weeks
            ],
            "assignments": [
                {"id": item.id, "body": item.body.model_dump(), "revision": item.revision}
                for item in snapshot.assignments
            ],
        },
    )
    return {
        **replaced,
        "preferences": snapshot.preferences.model_dump(),
        "routines": [item.model_dump() for item in snapshot.routines],
    }


class TimerSplitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_min: int | None = Field(default=None, ge=15, le=7140)
    timer_work_min: int = Field(ge=1, le=180)
    timer_break_min: int = Field(ge=1, le=60)
    timer_long_break_min: int = Field(ge=1, le=120)
    timer_long_break_every: int = Field(ge=2, le=12)

    @field_validator("duration_min")
    @classmethod
    def duration_is_on_the_grid(cls, value: int | None) -> int | None:
        if value is not None and value % 15:
            raise ValueError("duration_min must be a multiple of 15")
        return value


def encode_availability(preferences: Preferences) -> str:
    return json.dumps(
        {
            "protected": [window.model_dump() for window in preferences.protected],
            "study_windows": [window.model_dump() for window in preferences.study_windows],
            "work_windows": [window.model_dump() for window in preferences.work_windows],
            "day_cutoff": preferences.day_cutoff,
        },
        separators=(",", ":"),
    )


def encode_comfort(preferences: Preferences) -> str:
    return json.dumps(
        {
            "alert_volume": preferences.alert_volume,
            "end_chime": preferences.end_chime,
            "tray_notifications": preferences.tray_notifications,
            "start_at_login": preferences.start_at_login,
            "preferred_view": preferences.preferred_view,
            "sidebar_collapsed": preferences.sidebar_collapsed,
            "sidebar_width_px": preferences.sidebar_width_px,
            "theme_pack": preferences.theme_pack,
            "accent": preferences.accent,
            "accent_chips": preferences.accent_chips,
            "motion": preferences.motion,
            "alarm_tone": preferences.alarm_tone,
            "planning_style": preferences.planning_style,
            "drag_step_min": preferences.drag_step_min,
            "clock_24h": preferences.clock_24h,
            "setup": preferences.setup.model_dump() if preferences.setup is not None else None,
        },
        separators=(",", ":"),
    )


def preferences_from_row(row: sqlite3.Row) -> dict:
    availability = json.loads(row["availability_json"] or "{}")
    comfort = json.loads(row["comfort_json"] or "{}")
    return Preferences(
        theme=row["theme"],
        reminders_enabled=bool(row["reminders_enabled"]),
        reminder_lead_min=int(row["reminder_lead_min"]),
        reminder_sound=bool(row["reminder_sound"]),
        reminder_dnd_override=bool(row["reminder_dnd_override"]),
        timer_work_min=int(row["timer_work_min"]),
        timer_break_min=int(row["timer_break_min"]),
        timer_long_break_min=int(row["timer_long_break_min"]),
        timer_long_break_every=int(row["timer_long_break_every"]),
        auto_split_pomodoro=bool(row["auto_split_pomodoro"]),
        default_spotify_url=row["default_spotify_url"],
        alarms=json.loads(row["alarms_json"]),
        protected=availability.get("protected") or [],
        study_windows=availability.get("study_windows") or [],
        work_windows=availability.get("work_windows") or [],
        day_cutoff=availability.get("day_cutoff"),
        alert_volume=comfort.get("alert_volume", 80),
        end_chime=bool(comfort.get("end_chime", False)),
        tray_notifications=bool(comfort.get("tray_notifications", True)),
        start_at_login=bool(comfort.get("start_at_login", False)),
        preferred_view=comfort.get("preferred_view"),
        sidebar_collapsed=bool(comfort.get("sidebar_collapsed", False)),
        sidebar_width_px=comfort.get("sidebar_width_px"),
        theme_pack=comfort.get("theme_pack", "system"),
        accent=comfort.get("accent", "default"),
        accent_chips=bool(comfort.get("accent_chips", False)),
        motion=comfort.get("motion"),
        alarm_tone=comfort.get("alarm_tone", "chime"),
        planning_style=comfort.get("planning_style", "suggest"),
        drag_step_min=comfort.get("drag_step_min", 5),
        clock_24h=bool(comfort.get("clock_24h", True)),
        setup=comfort.get("setup"),
    ).model_dump()


def capture_transfer(db: sqlite3.Connection, user_id: int) -> dict:
    snapshot = capture_account(db, user_id)
    prefs = db.execute("SELECT * FROM preferences WHERE user_id = ?", (user_id,)).fetchone()
    assert prefs is not None
    routines = [
        routine_view(row)
        for row in db.execute(
            """SELECT id, name, body, revision, created_at, updated_at FROM routines
            WHERE user_id = ? ORDER BY name, id""",
            (user_id,),
        )
    ]
    return {
        **snapshot,
        "preferences": preferences_from_row(prefs),
        "routines": routines,
    }


def write_preferences(db: sqlite3.Connection, user_id: int, preferences: Preferences) -> dict:
    db.execute(
        """UPDATE preferences
        SET theme = ?, reminders_enabled = ?, reminder_lead_min = ?, reminder_sound = ?,
            reminder_dnd_override = ?, timer_work_min = ?, timer_break_min = ?,
            timer_long_break_min = ?, timer_long_break_every = ?, auto_split_pomodoro = ?,
            default_spotify_url = ?, alarms_json = ?, availability_json = ?, comfort_json = ?
        WHERE user_id = ?""",
        (
            preferences.theme,
            int(preferences.reminders_enabled),
            preferences.reminder_lead_min,
            int(preferences.reminder_sound),
            int(preferences.reminder_dnd_override),
            preferences.timer_work_min,
            preferences.timer_break_min,
            preferences.timer_long_break_min,
            preferences.timer_long_break_every,
            int(preferences.auto_split_pomodoro),
            preferences.default_spotify_url,
            json.dumps([alarm.model_dump() for alarm in preferences.alarms], separators=(",", ":")),
            encode_availability(preferences),
            encode_comfort(preferences),
            user_id,
        ),
    )
    return preferences.model_dump()


def solve_availability(
    row: sqlite3.Row | None,
) -> tuple[list[int], list[StudyWindow], list[WorkWindow]]:
    if row is None:
        return [0] * 7, [], []
    availability = json.loads(row["availability_json"] or "{}")
    protected = [ProtectedWindow.model_validate(item) for item in availability.get("protected") or []]
    study = [StudyWindow.model_validate(item) for item in availability.get("study_windows") or []]
    work = [WorkWindow.model_validate(item) for item in availability.get("work_windows") or []]
    return occupancy_from_windows(protected, availability.get("day_cutoff")), study, work


def create_app(database: Path | None = None, origin: str | None = None) -> FastAPI:
    path = database or Path(os.environ.get("FLEXWEEK_DATABASE", str(ROOT / "var" / "flexweek.db")))
    public_origin = (origin or os.environ.get("FLEXWEEK_ORIGIN", "http://127.0.0.1:8000")).rstrip("/")
    parsed = urlsplit(public_origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path or parsed.query:
        raise ValueError("FLEXWEEK_ORIGIN must be an http(s) origin without a path")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "testserver"}:
        raise ValueError("Non-local deployments require an HTTPS origin")
    secure = parsed.scheme == "https"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize(path)
        yield

    app = FastAPI(title="FlexWeek", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[parsed.hostname])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            if (
                request.headers.get("X-FlexWeek-Request") != "1"
                or request.headers.get("origin", public_origin) != public_origin
                or request.headers.get("sec-fetch-site") == "cross-site"
            ):
                return JSONResponse({"detail": "Request origin rejected"}, status_code=403)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_BODY:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Pydantic errors otherwise echo rejected passwords into the response.
        return JSONResponse(
            {"detail": "Invalid input. Check field lengths, times and required values."}, status_code=422
        )

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request: Request, exc: sqlite3.OperationalError):
        return JSONResponse(
            {"detail": "Storage unavailable. Your changes were not saved; retry shortly."}, status_code=503
        )

    def user(request: Request) -> dict:
        token = request.cookies.get(COOKIE, "")
        with connect(path) as db:
            row = db.execute(
                """SELECT users.id, users.username FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE token_hash = ? AND expires > ?""",
                (digest(token), int(time.time())),
            ).fetchone()
        if row is None:
            raise HTTPException(401, "Please sign in")
        expected = request.headers.get("X-FlexWeek-Account")
        if expected is not None and expected != str(row["id"]):
            raise HTTPException(401, "Account changed. Please sign in again.")
        return dict(row)

    def session_response(response: Response, token: str) -> None:
        response.set_cookie(
            COOKIE, token, max_age=SESSION_SECONDS, httponly=True, secure=secure, samesite="strict", path="/"
        )

    def authenticate(data: Credentials, request: Request, response: Response, register: bool) -> dict:
        address = request.client.host if request.client else "unknown"
        if not throttle(path, address, data.username):
            raise HTTPException(
                429, "Too many attempts. Try again in five minutes.", headers={"Retry-After": "300"}
            )
        codes: list[str] | None = None
        if register:
            encoded = password_hash(data.password)
            codes = generate_recovery_codes()
            try:
                with connect(path) as db:
                    cursor = db.execute(
                        "INSERT INTO users(username, password_hash) VALUES (?, ?)", (data.username, encoded)
                    )
                    user_id = int(cursor.lastrowid or 0)
                    new_preferences(db, user_id)
                    replace_recovery_codes(db, user_id, codes)
                    token = create_session(db, user_id)
            except sqlite3.IntegrityError as exc:
                raise HTTPException(409, "Username unavailable") from exc
        else:
            with connect(path) as db:
                row = db.execute("SELECT * FROM users WHERE username = ?", (data.username,)).fetchone()
            encoded = row["password_hash"] if row else password_hash("missing-account-password", "00" * 16)
            matched = password_matches(data.password, encoded)
            if not row or not matched:
                raise HTTPException(401, "Incorrect username or password")
            user_id = row["id"]
            with connect(path) as db:
                token = create_session(db, user_id)
        with connect(path) as db:
            db.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (digest(request.cookies.get(COOKIE, "")),)
            )
        session_response(response, token)
        result = {"id": user_id, "username": data.username}
        if codes is not None:
            result["recovery_codes"] = codes
        return result

    @app.post("/api/auth/register", status_code=201)
    def register(data: Credentials, request: Request, response: Response) -> dict:
        return authenticate(data, request, response, True)

    @app.post("/api/auth/login")
    def login(data: Credentials, request: Request, response: Response) -> dict:
        return authenticate(data, request, response, False)

    @app.get("/api/auth/me")
    def me(account: Annotated[dict, Depends(user)]) -> dict:
        return account

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response) -> None:
        if request.headers.get("X-FlexWeek-Account") is not None:
            user(request)
        with connect(path) as db:
            db.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (digest(request.cookies.get(COOKIE, "")),)
            )
        response.delete_cookie(COOKIE, path="/", httponly=True, secure=secure, samesite="strict")

    def deny_if_throttled(request: Request, username: str) -> None:
        address = request.client.host if request.client else "unknown"
        if not throttle(path, address, username):
            raise HTTPException(
                429, "Too many attempts. Try again in five minutes.", headers={"Retry-After": "300"}
            )

    def require_password(db: sqlite3.Connection, user_id: int, password: str) -> None:
        # Called inside the caller's transaction so a password rotated by another
        # session between the check and the write cannot still authorize the write.
        row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not password_matches(password, row["password_hash"]):
            raise HTTPException(401, PASSWORD_WRONG)

    @app.post("/api/auth/recover")
    def recover(data: RecoverRequest, request: Request, response: Response) -> dict:
        deny_if_throttled(request, data.username)
        dummy = hash_recovery_code("missing-recovery-code")
        # scrypt runs before the write lock is taken, like register.
        new_hash = password_hash(data.password)
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM users WHERE username = ?", (data.username,)).fetchone()
            hashes = (
                [
                    item["code_hash"]
                    for item in db.execute(
                        "SELECT code_hash FROM recovery_codes WHERE user_id = ?", (row["id"],)
                    )
                ]
                if row is not None
                else []
            )
            real = set(hashes)
            padded = list(hashes)
            while len(padded) < RECOVERY_CODE_COUNT:
                padded.append(dummy)
            matched = None
            for stored in padded:
                if recovery_code_matches(data.code, stored):
                    matched = stored
            if row is None or matched is None or matched not in real:
                raise HTTPException(401, RECOVER_WRONG)
            db.execute(
                "DELETE FROM recovery_codes WHERE user_id = ? AND code_hash = ?",
                (row["id"], matched),
            )
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, row["id"]))
            db.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            token = create_session(db, row["id"])
            user_id = row["id"]
            username = row["username"]
        session_response(response, token)
        return {"id": user_id, "username": username}

    @app.get("/api/auth/recovery-status")
    def recovery_status(account: Annotated[dict, Depends(user)]) -> dict:
        with connect(path) as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM recovery_codes WHERE user_id = ?", (account["id"],)
            ).fetchone()
        return {"remaining": int(row["n"]) if row else 0}

    @app.post("/api/auth/recovery-codes")
    def refresh_recovery_codes(
        data: PasswordConfirm, request: Request, account: Annotated[dict, Depends(user)]
    ) -> dict:
        deny_if_throttled(request, account["username"])
        codes = generate_recovery_codes()
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            require_password(db, account["id"], data.password)
            replace_recovery_codes(db, account["id"], codes)
        return {"recovery_codes": codes, "remaining": len(codes)}

    @app.post("/api/auth/password")
    def change_password(
        data: PasswordChange, request: Request, response: Response, account: Annotated[dict, Depends(user)]
    ) -> dict:
        deny_if_throttled(request, account["username"])
        new_hash = password_hash(data.new_password)
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            require_password(db, account["id"], data.current_password)
            if data.new_password == data.current_password:
                raise HTTPException(422, PASSWORD_SAME)
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, account["id"]))
            db.execute("DELETE FROM sessions WHERE user_id = ?", (account["id"],))
            token = create_session(db, account["id"])
        session_response(response, token)
        return {"id": account["id"], "username": account["username"]}

    @app.delete("/api/auth/account", status_code=204)
    def remove_account(
        data: PasswordConfirm, request: Request, response: Response, account: Annotated[dict, Depends(user)]
    ) -> None:
        deny_if_throttled(request, account["username"])
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            require_password(db, account["id"], data.password)
            delete_account(db, account["id"])
        response.delete_cookie(COOKIE, path="/", httponly=True, secure=secure, samesite="strict")

    @app.get("/api/week")
    def get_week(account: Annotated[dict, Depends(user)], week_start: str | None = None) -> dict:
        start = week_start if week_start is not None else current_week_start()
        if not is_week_start(start):
            raise HTTPException(422, WEEK_START_RULE)
        with connect(path) as db:
            row = db.execute(
                "SELECT blocks, revision FROM weeks WHERE user_id = ? AND week_start = ?",
                (account["id"], start),
            ).fetchone()
            blocks = json.loads(row["blocks"]) if row else []
            owned = load_assignment_bodies(
                db,
                account["id"],
                {block["assignment_id"] for block in blocks if block.get("assignment_id")},
            )
        # A week nobody has saved yet is empty, not missing: the client needs no create-then-fetch.
        return {
            "week_start": start,
            "blocks": rewrite_stored_blocks(blocks, owned),
            "revision": row["revision"] if row else 0,
        }

    @app.get("/api/weeks")
    def get_weeks(account: Annotated[dict, Depends(user)]) -> dict:
        with connect(path) as db:
            rows = db.execute(
                "SELECT week_start FROM weeks WHERE user_id = ? ORDER BY week_start", (account["id"],)
            ).fetchall()
        return {"weeks": [row["week_start"] for row in rows]}

    @app.get("/api/day")
    def get_day(account: Annotated[dict, Depends(user)], date: str | None = None) -> dict:
        if date is None or not is_calendar_date(date):
            raise HTTPException(422, DATE_RULE)
        week_start = monday_of(date)
        with connect(path) as db:
            row = db.execute(
                "SELECT blocks FROM weeks WHERE user_id = ? AND week_start = ?",
                (account["id"], week_start),
            ).fetchone()
            blocks = json.loads(row["blocks"]) if row else []
            owned = load_assignment_bodies(
                db,
                account["id"],
                {block["assignment_id"] for block in blocks if block.get("assignment_id")},
            )
            assignment_rows = [
                (json.loads(item["body"]), int(item["revision"]))
                for item in db.execute(
                    "SELECT body, revision FROM assignments WHERE user_id = ?", (account["id"],)
                ).fetchall()
            ]
            weeks = list_account_weeks(db, account["id"])
        return build_day(date, week_start, rewrite_stored_blocks(blocks, owned), assignment_rows, weeks)

    @app.get("/api/month")
    def get_month(account: Annotated[dict, Depends(user)], month: str | None = None) -> dict:
        if month is None or not is_month_label(month):
            raise HTTPException(422, MONTH_RULE)
        with connect(path) as db:
            assignment_rows = [
                (json.loads(item["body"]), int(item["revision"]))
                for item in db.execute(
                    "SELECT body, revision FROM assignments WHERE user_id = ?", (account["id"],)
                ).fetchall()
            ]
            weeks = list_account_weeks(db, account["id"])
        return build_month(month, assignment_rows, weeks)

    @app.put("/api/week")
    def put_week(week: SavedWeek, account: Annotated[dict, Depends(user)]) -> dict:
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            incoming = adopt_legacy_deadlines(db, account["id"], week.week_start, week.blocks)
            owned = require_own_assignments(db, account["id"], assignment_ids_of(incoming))
            blocks = dump_blocks(rewrite_blocks(incoming, owned))
            stored_blocks, revision = save_week_row(db, account["id"], week.week_start, blocks, week.revision)
        return {"week_start": week.week_start, "blocks": stored_blocks, "revision": revision}

    @app.get("/api/assignments")
    def get_assignments(
        account: Annotated[dict, Depends(user)],
        week_start: str | None = None,
        include_completed: bool = False,
    ) -> dict:
        if week_start is None or not is_week_start(week_start):
            raise HTTPException(422, WEEK_START_RULE)
        with connect(path) as db:
            rows = db.execute(
                "SELECT id, body, revision FROM assignments WHERE user_id = ?", (account["id"],)
            ).fetchall()
            weeks = list_account_weeks(db, account["id"])
        planned_by_id = planned_minutes_by_id(weeks, week_start)
        items = []
        for row in rows:
            body = json.loads(row["body"])
            if body["completed"] and not include_completed:
                continue
            items.append(assignment_view(body, row["revision"], planned_by_id.get(row["id"], 0)))
        items.sort(key=lambda item: due_sort_key(item["due"], item["id"]))
        return {"assignments": items}

    @app.put("/api/assignments/{assignment_id}")
    def put_assignment(
        assignment_id: str, payload: Assignment, account: Annotated[dict, Depends(user)]
    ) -> dict:
        if payload.id != assignment_id:
            raise HTTPException(422, "assignment id in the path and body must match")
        content = AssignmentContent.model_validate(payload.model_dump(exclude={"revision"}))
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            return upsert_assignment(db, account["id"], content, payload.revision)

    @app.post("/api/assignments/{assignment_id}/spread")
    def post_spread(
        assignment_id: str, payload: SpreadRequest, account: Annotated[dict, Depends(user)]
    ) -> dict:
        with connect(path) as db:
            row = db.execute(
                "SELECT body FROM assignments WHERE user_id = ? AND id = ?",
                (account["id"], assignment_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Assignment not found")
            weeks = list_account_weeks(db, account["id"])
        body = json.loads(row["body"])
        if body["completed"]:
            raise HTTPException(422, "completed assignments cannot be spread")
        planned = planned_minutes_by_id(weeks, "2000-01-01").get(assignment_id, 0)
        sessions, remaining = spread_sessions(
            estimate_min=int(body["estimate_min"]),
            focus_minutes=int(body["focus_minutes"]),
            planned_min=planned,
            due=body["due"],
            session_min=payload.session_min,
            from_date=payload.from_date,
        )
        return {
            "assignment_id": assignment_id,
            "session_min": payload.session_min,
            "remaining_min": remaining,
            "sessions": sessions,
        }

    @app.delete("/api/assignments/{assignment_id}")
    def remove_assignment(
        assignment_id: str, account: Annotated[dict, Depends(user)], revision: int | None = None
    ) -> dict:
        if revision is None:
            raise HTTPException(422, "revision is required")
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            return delete_assignment(db, account["id"], assignment_id, revision)

    @app.post("/api/changes")
    def post_changes(batch: ChangesRequest, account: Annotated[dict, Depends(user)]) -> dict:
        digest_value = payload_digest(batch.model_dump())
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            if batch.operation_id is not None:
                remembered = recall_operation(db, account["id"], batch.operation_id, digest_value)
                if remembered is not None:
                    return remembered
            if batch.snapshot_label is not None:
                insert_restore_point(db, account["id"], batch.snapshot_label)
            assignment_results: list[dict] = []
            deletes: list[AssignmentChange] = []
            for change in batch.assignments:
                if change.assignment is None:
                    deletes.append(change)
                    continue
                if change.assignment.id != change.id:
                    raise HTTPException(422, "assignment id in the path and body must match")
                saved = upsert_assignment(db, account["id"], change.assignment, change.revision)
                assignment_results.append(
                    {
                        "id": change.id,
                        "revision": saved["revision"],
                        "assignment": {key: value for key, value in saved.items() if key != "revision"},
                    }
                )
            for change in deletes:
                deleted = delete_assignment(db, account["id"], change.id, change.revision)
                assignment_results.append(
                    {
                        "id": change.id,
                        "revision": change.revision,
                        "assignment": None,
                        "changed_weeks": deleted["changed_weeks"],
                        "removed_sessions": deleted["removed_sessions"],
                    }
                )
            week_results: list[dict] = []
            for week in batch.weeks:
                incoming = adopt_legacy_deadlines(db, account["id"], week.week_start, week.blocks)
                owned = require_own_assignments(db, account["id"], assignment_ids_of(incoming))
                blocks = dump_blocks(rewrite_blocks(incoming, owned))
                stored_blocks, revision = save_week_row(
                    db, account["id"], week.week_start, blocks, week.revision
                )
                week_results.append(
                    {"week_start": week.week_start, "blocks": stored_blocks, "revision": revision}
                )
            result = {"weeks": week_results, "assignments": assignment_results}
            if batch.operation_id is not None:
                remember_operation(db, account["id"], batch.operation_id, digest_value, result)
        return result

    @app.get("/api/preferences")
    def get_preferences(account: Annotated[dict, Depends(user)]) -> dict:
        with connect(path) as db:
            row = db.execute("SELECT * FROM preferences WHERE user_id = ?", (account["id"],)).fetchone()
        return preferences_from_row(row)

    @app.put("/api/preferences")
    def put_preferences(preferences: Preferences, account: Annotated[dict, Depends(user)]) -> dict:
        with connect(path) as db:
            return write_preferences(db, account["id"], preferences)

    @app.get("/api/routines")
    def get_routines(account: Annotated[dict, Depends(user)]) -> dict:
        with connect(path) as db:
            rows = db.execute(
                """SELECT id, name, body, revision, created_at, updated_at FROM routines
                WHERE user_id = ? ORDER BY name, id""",
                (account["id"],),
            ).fetchall()
        return {"routines": [routine_view(row) for row in rows]}

    @app.put("/api/routines/{routine_id}")
    def put_routine(routine_id: str, payload: Routine, account: Annotated[dict, Depends(user)]) -> dict:
        if payload.id != routine_id:
            raise HTTPException(422, "routine id in the path and body must match")
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            return upsert_routine(db, account["id"], payload)

    @app.delete("/api/routines/{routine_id}")
    def remove_routine(
        routine_id: str,
        account: Annotated[dict, Depends(user)],
        revision: int | None = None,
        operation_id: str | None = None,
    ) -> dict:
        if revision is None:
            raise HTTPException(422, "revision is required")
        digest_value = payload_digest({"id": routine_id, "revision": revision, "op": "delete"})
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            if operation_id is not None:
                remembered = recall_operation(db, account["id"], operation_id, digest_value)
                if remembered is not None:
                    return remembered
            result = delete_routine(db, account["id"], routine_id, revision)
            if operation_id is not None:
                remember_operation(db, account["id"], operation_id, digest_value, result)
        return result

    @app.get("/api/storage-info")
    def get_storage_info(account: Annotated[dict, Depends(user)]) -> dict:
        hostname = parsed.hostname or ""
        if hostname in {"127.0.0.1", "localhost", "testserver"}:
            mode, label = "local", "On this device"
        else:
            mode, label = "hosted", "On your FlexWeek server"
        return {
            "mode": mode,
            "label": label,
            "username": account["username"],
            "origin": public_origin,
            "transfer_limit_bytes": MAX_BODY,
        }

    @app.post("/api/account-export")
    def export_account(
        data: PasswordConfirm, request: Request, account: Annotated[dict, Depends(user)]
    ) -> dict:
        deny_if_throttled(request, account["username"])
        with connect(path) as db:
            db.execute("BEGIN")
            require_password(db, account["id"], data.password)
            payload = {
                "format": 3,
                "exported_at": naive_now(),
                "username": account["username"],
                **capture_transfer(db, account["id"]),
            }
        snapshot = TransferSnapshot.model_validate(payload).model_dump()
        if not transfer_fits(snapshot):
            raise HTTPException(413, TRANSFER_TOO_LARGE)
        return snapshot

    @app.post("/api/account-import/preview")
    def preview_account_import(
        payload: TransferPreviewRequest, account: Annotated[dict, Depends(user)]
    ) -> dict:
        incoming = payload.snapshot.model_dump()
        with connect(path) as db:
            current = capture_transfer(db, account["id"])
        return {
            "state_token": state_token({"current": current, "incoming": incoming}),
            "source_username": payload.snapshot.username,
            "changes": diff_transfer(current, incoming),
        }

    @app.post("/api/account-import")
    def apply_account_import(payload: TransferApplyRequest, account: Annotated[dict, Depends(user)]) -> dict:
        incoming = payload.snapshot.model_dump()
        digest_value = payload_digest(payload.model_dump())
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            remembered = recall_operation(db, account["id"], payload.operation_id, digest_value)
            if remembered is not None:
                return remembered
            current = capture_transfer(db, account["id"])
            if payload.state_token != state_token({"current": current, "incoming": incoming}):
                raise HTTPException(409, IMPORT_STALE)
            stamp = naive_now()
            recovery = insert_restore_point(db, account["id"], f"Before import — {stamp}")
            replaced = apply_transfer(db, account["id"], payload.snapshot)
            result = {"recovery_id": recovery["id"], **replaced}
            remember_operation(db, account["id"], payload.operation_id, digest_value, result)
        return result

    @app.get("/api/timer-presets")
    def get_timer_presets(_account: Annotated[dict, Depends(user)]) -> dict:
        return {"presets": list(TIMER_PRESETS)}

    @app.get("/api/reminder-limits")
    def get_reminder_limits(_account: Annotated[dict, Depends(user)]) -> dict:
        return dict(REMINDER_LIMITS)

    @app.post("/api/timer-split-preview")
    def post_timer_split_preview(
        payload: TimerSplitRequest, _account: Annotated[dict, Depends(user)]
    ) -> dict:
        return preview_split(
            duration_min=payload.duration_min,
            timer_work_min=payload.timer_work_min,
            timer_break_min=payload.timer_break_min,
            timer_long_break_min=payload.timer_long_break_min,
            timer_long_break_every=payload.timer_long_break_every,
        )

    @app.get("/api/restore-points")
    def get_restore_points(account: Annotated[dict, Depends(user)]) -> dict:
        with connect(path) as db:
            rows = db.execute(
                """SELECT id, label, created_at, weeks_count, assignments_count
                FROM restore_points WHERE user_id = ? ORDER BY seq DESC""",
                (account["id"],),
            ).fetchall()
        return {"restore_points": [restore_point_view(row) for row in rows]}

    @app.post("/api/restore-points")
    def post_restore_point(payload: RestoreCreate, account: Annotated[dict, Depends(user)]) -> dict:
        digest_value = payload_digest(payload.model_dump())
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            remembered = recall_operation(db, account["id"], payload.operation_id, digest_value)
            if remembered is not None:
                return remembered
            result = insert_restore_point(db, account["id"], payload.label)
            remember_operation(db, account["id"], payload.operation_id, digest_value, result)
        return result

    @app.get("/api/restore-points/{point_id}/preview")
    def preview_restore_point(point_id: str, account: Annotated[dict, Depends(user)]) -> dict:
        with connect(path) as db:
            row = db.execute(
                "SELECT id, body FROM restore_points WHERE user_id = ? AND id = ?",
                (account["id"], point_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, RESTORE_UNKNOWN)
            current = capture_account(db, account["id"])
        stored = json.loads(row["body"])
        return {
            "id": row["id"],
            "state_token": state_token(current),
            "changes": diff_snapshots(current, stored),
        }

    @app.post("/api/restore-points/{point_id}/restore")
    def restore_restore_point(
        point_id: str, payload: RestoreApply, account: Annotated[dict, Depends(user)]
    ) -> dict:
        digest_value = payload_digest({"id": point_id, **payload.model_dump()})
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            remembered = recall_operation(db, account["id"], payload.operation_id, digest_value)
            if remembered is not None:
                return remembered
            row = db.execute(
                "SELECT id, body FROM restore_points WHERE user_id = ? AND id = ?",
                (account["id"], point_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, RESTORE_UNKNOWN)
            current = capture_account(db, account["id"])
            if payload.state_token != state_token(current):
                raise HTTPException(409, RESTORE_STALE)
            stored = json.loads(row["body"])
            stamp = naive_now()
            recovery = insert_restore_point(
                db, account["id"], f"Before restore — {stamp}", keep_ids={point_id}
            )
            replaced = replace_account(db, account["id"], stored)
            result = {"id": point_id, "recovery_id": recovery["id"], **replaced}
            remember_operation(db, account["id"], payload.operation_id, digest_value, result)
        return result

    @app.post("/api/solve")
    def post_solve(week: SolveRequest, account: Annotated[dict, Depends(user)]) -> dict:
        ids = assignment_ids_of(week.blocks)
        with connect(path) as db:
            owned = require_own_assignments(db, account["id"], ids) if ids else {}
            prefs = db.execute(
                "SELECT availability_json FROM preferences WHERE user_id = ?", (account["id"],)
            ).fetchone()
        extra_occ, study_windows, work_windows = solve_availability(prefs)
        blocks = week.blocks
        extra_deadlines = None
        extra_slack = None
        if ids:
            if week.week_start is None:
                raise HTTPException(422, "week_start is required when a block has assignment_id")
            blocks, extra_deadlines, extra_slack = prepare_solve(week.blocks, week.week_start, owned)
        if week.recover is not None:
            return reschedule_after_miss(
                blocks,
                week.recover.missed_block_id,
                week.recover.missed_day,
                week.recover.previous_placed,
                deadlines=extra_deadlines,
                slack_deadlines=extra_slack,
                extra_occ=extra_occ,
                study_windows=study_windows,
                work_windows=work_windows,
            ).model_dump()
        if week.running_late is not None:
            return reschedule_running_late(
                blocks,
                week.running_late.day,
                week.running_late.minutes,
                week.running_late.from_start,
                week.running_late.previous_placed,
                deadlines=extra_deadlines,
                slack_deadlines=extra_slack,
                extra_occ=extra_occ,
                study_windows=study_windows,
                work_windows=work_windows,
            ).model_dump()
        return solve(
            blocks,
            deadlines=extra_deadlines,
            slack_deadlines=extra_slack,
            extra_occ=extra_occ,
            study_windows=study_windows,
            work_windows=work_windows,
        ).model_dump()

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()
