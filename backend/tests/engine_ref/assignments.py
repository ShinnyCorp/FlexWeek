"""Assignment helpers. No HTTP, no database."""

from __future__ import annotations

import copy
import hashlib
from datetime import date, timedelta

from backend.tests.engine_ref.models import TimeBlock, parse_due
from backend.tests.engine_ref.slots import hhmm_to_minutes, minutes_to_hhmm, parse_deadline
from backend.tests.engine_ref.weeks import LAST_DAY


def migrated_assignment_id(week_start: str, source_id: str) -> str:
    return "a-" + hashlib.sha256(f"{week_start}:{source_id}".encode()).hexdigest()[:32]


def due_from_latest(week_start: str, latest: str | None, days: list[int]) -> str:
    monday = date.fromisoformat(week_start)
    parsed = parse_deadline(latest, days)
    if parsed is None:
        return f"{(monday + timedelta(days=6)).isoformat()}T23:59"
    day_index, minutes = parsed
    return f"{(monday + timedelta(days=day_index)).isoformat()}T{minutes_to_hhmm(minutes)}"


def completed_at_for_block(week_start: str, block: dict) -> str:
    monday = date.fromisoformat(week_start)
    start = block.get("start")
    days = list(block.get("days") or [])
    day = block.get("completed_day")
    if start:
        if day is None and len(days) == 1:
            day = days[0]
        if day is not None:
            end = hhmm_to_minutes(start) + int(block["duration_min"])
            # 24:00 is the next date at 00:00. A stamp of T24:00 is not a time the API accepts.
            day_date = monday + timedelta(days=int(day))
            if end >= 24 * 60:
                day_date += timedelta(days=end // (24 * 60))
                end %= 24 * 60
            if day_date > LAST_DAY:
                return f"{LAST_DAY.isoformat()}T23:59"
            return f"{day_date.isoformat()}T{minutes_to_hhmm(end)}"
    return f"{(monday + timedelta(days=6)).isoformat()}T23:59"


def _assignment_body(
    assignment_id: str,
    block: dict,
    *,
    due: str,
    estimate_min: int,
    focus_minutes: int,
    focus_sessions: int,
    completed: bool,
    completed_at: str | None,
) -> dict:
    return {
        "id": assignment_id,
        "title": block.get("title") or assignment_id,
        "course": block.get("course"),
        "category": block.get("category"),
        "priority": block.get("priority", 3),
        "energy": block.get("energy", "medium"),
        "spotify_url": block.get("spotify_url"),
        "due": due,
        "estimate_min": estimate_min,
        "focus_minutes": focus_minutes,
        "focus_sessions": focus_sessions,
        "completed": completed,
        "completed_at": completed_at,
    }


def _as_session(block: dict, assignment_id: str) -> None:
    block["assignment_id"] = assignment_id
    block.pop("latest", None)
    block.pop("focus_minutes", None)
    block.pop("focus_sessions", None)


def due_placement_bound(week_start: str, due: str) -> tuple[int, int] | None:
    monday = date.fromisoformat(week_start)
    due_day, minutes = parse_due(due)
    if due_day > monday + timedelta(days=6):
        return None
    if due_day < monday:
        return (0, 0)
    return ((due_day - monday).days, minutes)


def due_slack_point(week_start: str, due: str) -> tuple[int, int]:
    monday = date.fromisoformat(week_start)
    due_day, minutes = parse_due(due)
    return ((due_day - monday).days, minutes)


def prepare_solve(
    blocks: list[TimeBlock],
    week_start: str,
    assignments: dict[str, dict],
) -> tuple[list[TimeBlock], dict[str, tuple[int, int] | None], dict[str, tuple[int, int]]]:
    keep: list[TimeBlock] = []
    deadlines: dict[str, tuple[int, int] | None] = {}
    slack: dict[str, tuple[int, int]] = {}
    for block in blocks:
        aid = block.assignment_id
        if not aid:
            keep.append(block)
            continue
        body = assignments[aid]
        if body["completed"] and not block.completed:
            continue
        # The subject comes from the assignment, so a session the client has not saved yet still
        # finds the study window kept for its subject.
        keep.append(block.model_copy(update={"course": body.get("course")}))
        deadlines[block.id] = due_placement_bound(week_start, body["due"])
        slack[block.id] = due_slack_point(week_start, body["due"])
    return keep, deadlines, slack


def legacy_session(week_start: str, block: TimeBlock) -> tuple[TimeBlock, dict]:
    raw = block.model_dump()
    aid = migrated_assignment_id(week_start, block.id)
    body = _assignment_body(
        aid,
        raw,
        due=due_from_latest(week_start, block.latest, list(block.days)),
        estimate_min=block.duration_min,
        focus_minutes=block.focus_minutes,
        focus_sessions=block.focus_sessions,
        completed=block.completed,
        completed_at=completed_at_for_block(week_start, raw) if block.completed else None,
    )
    session = block.model_copy(
        update={"assignment_id": aid, "latest": None, "focus_minutes": 0, "focus_sessions": 0}
    )
    return session, body


def rewrite_session(block: TimeBlock, assignment: dict) -> TimeBlock:
    return block.model_copy(
        update={
            "title": assignment["title"],
            "priority": assignment["priority"],
            "energy": assignment["energy"],
            "course": assignment["course"],
            "category": assignment["category"],
            "spotify_url": assignment["spotify_url"],
        }
    )


def planned_minutes_by_id(weeks: list[tuple[str, list[dict]]], from_week: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for week_start, blocks in weeks:
        if week_start < from_week:
            continue
        for block in blocks:
            aid = block.get("assignment_id")
            if not aid or block.get("completed"):
                continue
            totals[aid] = totals.get(aid, 0) + int(block["duration_min"])
    return totals


def unplanned_minutes(estimate_min: int, focus_minutes: int, planned: int) -> int:
    remaining = max(0, estimate_min - focus_minutes)
    return max(0, remaining - planned)


def migrate_blocks(week_start: str, blocks: list[dict]) -> tuple[list[dict], list[dict]]:
    updated = copy.deepcopy(blocks)
    created: list[dict] = []
    grouped: dict[str, list[int]] = {}
    for index, block in enumerate(updated):
        parent = block.get("pomodoro_parent_id")
        if block.get("kind") == "locked" and parent:
            grouped.setdefault(str(parent), []).append(index)
    claimed: set[int] = set()
    sunday_due = f"{(date.fromisoformat(week_start) + timedelta(days=6)).isoformat()}T23:59"
    for parent, indices in grouped.items():
        work_indices = [index for index in indices if updated[index].get("pomodoro_role") == "work"]
        if not work_indices or any(updated[index].get("assignment_id") for index in work_indices):
            continue
        work = [updated[index] for index in work_indices]
        aid = migrated_assignment_id(week_start, parent)
        completed = all(bool(block.get("completed")) for block in work)
        completed_at = None
        if completed:
            ends = [completed_at_for_block(week_start, block) for block in work if block.get("start")]
            completed_at = max(ends) if ends else sunday_due
        created.append(
            _assignment_body(
                aid,
                work[0],
                due=sunday_due,
                estimate_min=sum(int(block["duration_min"]) for block in work),
                focus_minutes=sum(int(block.get("focus_minutes") or 0) for block in work),
                focus_sessions=sum(int(block.get("focus_sessions") or 0) for block in work),
                completed=completed,
                completed_at=completed_at,
            )
        )
        for index in work_indices:
            _as_session(updated[index], aid)
            claimed.add(index)
    for index, block in enumerate(updated):
        if index in claimed or block.get("assignment_id") or block.get("kind") != "flexible":
            continue
        aid = migrated_assignment_id(week_start, str(block["id"]))
        completed = bool(block.get("completed"))
        created.append(
            _assignment_body(
                aid,
                block,
                due=due_from_latest(week_start, block.get("latest"), list(block.get("days") or [])),
                estimate_min=int(block["duration_min"]),
                focus_minutes=int(block.get("focus_minutes") or 0),
                focus_sessions=int(block.get("focus_sessions") or 0),
                completed=completed,
                completed_at=completed_at_for_block(week_start, block) if completed else None,
            )
        )
        _as_session(block, aid)
    return updated, created
