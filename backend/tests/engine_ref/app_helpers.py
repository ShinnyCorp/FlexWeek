"""The helpers of backend/app.py as they were before their SQL moved into the Rust store.

Copied from the commit before part C step 2, with only the imports changed. The store tests run the
same calls through these and through the shipped helpers and require equal results.
"""

from __future__ import annotations

import json
import secrets

from fastapi import HTTPException

from backend.app import (
    ASSIGNMENT_CONFLICT,
    ASSIGNMENT_LIMIT,
    MAX_ASSIGNMENTS,
    MAX_OPERATIONS,
    MAX_RESTORE_POINTS,
    MAX_ROUTINES,
    OPERATION_CONFLICT,
    ROUTINE_CONFLICT,
    ROUTINE_LIMIT,
    ROUTINE_UNKNOWN,
    WEEK_CONFLICT,
    Preferences,
    TransferSnapshot,
    dump_blocks,
    encode_assignment,
    encode_availability,
    encode_comfort,
    encode_routine,
    naive_now,
    preferences_from_row,
    routine_view,
)
from backend.assignments import legacy_session
from backend.models import AssignmentContent, Routine, TimeBlock
from backend.recovery import hash_recovery_code
from backend.restore import canonical
from backend.storage import Connection


def load_assignment_rows(db: Connection, user_id: int, ids: set[str]) -> dict[str, tuple[str, int]]:
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT id, body, revision FROM assignments WHERE user_id = ? AND id IN ({placeholders})",
        (user_id, *ids),
    ).fetchall()
    return {row["id"]: (row["body"], row["revision"]) for row in rows}


def adopt_legacy_deadlines(
    db: Connection, user_id: int, week_start: str, blocks: list[TimeBlock]
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


def list_account_weeks(db: Connection, user_id: int) -> list[tuple[str, list[dict]]]:
    rows = db.execute("SELECT week_start, blocks FROM weeks WHERE user_id = ?", (user_id,)).fetchall()
    return [(row["week_start"], json.loads(row["blocks"])) for row in rows]


def upsert_assignment(db: Connection, user_id: int, content: AssignmentContent, revision: int) -> dict:
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


def delete_assignment(db: Connection, user_id: int, assignment_id: str, revision: int) -> dict:
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
    db: Connection,
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


def capture_account(db: Connection, user_id: int) -> dict:
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


def prune_restore_points(db: Connection, user_id: int, keep_ids: set[str]) -> None:
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


def prune_operations(db: Connection, user_id: int) -> None:
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


def recall_operation(db: Connection, user_id: int, operation_id: str, digest_value: str) -> dict | None:
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
    db: Connection, user_id: int, operation_id: str, digest_value: str, response: dict
) -> None:
    db.execute(
        """INSERT INTO operations(user_id, operation_id, payload_hash, response)
        VALUES (?, ?, ?, ?)""",
        (user_id, operation_id, digest_value, canonical(response)),
    )
    prune_operations(db, user_id)


def insert_restore_point(db: Connection, user_id: int, label: str, keep_ids: set[str] | None = None) -> dict:
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


def replace_account(db: Connection, user_id: int, snapshot: dict) -> dict:
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


def replace_recovery_codes(db: Connection, user_id: int, codes: list[str]) -> None:
    db.execute("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
    for code in codes:
        db.execute(
            "INSERT INTO recovery_codes(user_id, code_hash) VALUES (?, ?)",
            (user_id, hash_recovery_code(code)),
        )


def upsert_routine(db: Connection, user_id: int, routine: Routine) -> dict:
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


def delete_routine(db: Connection, user_id: int, routine_id: str, revision: int) -> dict:
    row = db.execute(
        "SELECT revision FROM routines WHERE user_id = ? AND id = ?", (user_id, routine_id)
    ).fetchone()
    if row is None:
        raise HTTPException(404, ROUTINE_UNKNOWN)
    if revision != row["revision"]:
        raise HTTPException(409, ROUTINE_CONFLICT)
    db.execute("DELETE FROM routines WHERE user_id = ? AND id = ?", (user_id, routine_id))
    return {"id": routine_id}


def apply_transfer(db: Connection, user_id: int, snapshot: TransferSnapshot) -> dict:
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


def capture_transfer(db: Connection, user_id: int) -> dict:
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


def write_preferences(db: Connection, user_id: int, preferences: Preferences) -> dict:
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
