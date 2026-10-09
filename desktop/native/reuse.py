"""Clipboard, collision previews and Stage 3/4 planning helpers. No Qt."""

from __future__ import annotations

import json
from datetime import date, datetime

import flexweek_engine  # type: ignore[import-untyped]

from desktop.native.calendar import iso_of

MAX_WEEK_BLOCKS = 100
AVAILABILITY_LIMIT = 21
LATE_MINUTES = (15, 30, 60)
PROTECTED_KINDS = ("downtime", "commute", "meal")
ROUTINE_FIELDS = (
    "title",
    "days",
    "start",
    "duration_min",
    "category",
    "course",
    "priority",
    "energy",
    "spotify_url",
)


def restore_point_label(text: str) -> str:
    return str(flexweek_engine.reuse_restore_label(text))


def week_label(week_start: str, today: date | str | None = None) -> str:
    return str(flexweek_engine.reuse_week_label(week_start, iso_of(today)))


def floor_slot(minutes: int) -> int:
    return int(flexweek_engine.reuse_floor_slot(minutes))


def is_homework_session(block: dict) -> bool:
    return bool(flexweek_engine.reuse_homework(json.dumps(block)))


def session_days(week_start: str, due: str) -> list[int]:
    return list(flexweek_engine.reuse_session_days(week_start, json.dumps(due)))


def is_planned(block: dict) -> bool:
    """Unfinished homework with its own time: one day and a start. Such a block is the student's plan,
    not a request to be planned, so nothing moves it unless its time stops working or they ask."""
    return bool(flexweek_engine.reuse_planned(json.dumps(block)))


def planning_days(block: dict, assignments: dict, week_start: str) -> list[int]:
    """The days homework may go on when it needs a new time. A plan narrows a session to the day it
    chose, so the days up to the deadline come back from the assignment rather than from the block."""
    return json.loads(
        flexweek_engine.reuse_planning_days(json.dumps(block), json.dumps(assignments), week_start)
    )


def apply_plan(
    blocks: list[dict],
    trace: dict | None,
    *,
    targets: set[str] | None = None,
    assignments: dict | None = None,
    week_start: str | None = None,
) -> list[dict]:
    """Copy the solver's start times onto the week's blocks so a save keeps the plan.

    Plan my homework used to keep placements only in the in-memory trace. Save wrote the
    blocks without starts, and any later edit dropped the trace, so homework vanished
    until the student planned again. With `targets`, only those sessions change: a plan for part of
    the week never touches the rest of it.

    Only unfinished homework is written. The solver lists a fixed block without its missed days, and
    copying that back left Monday missed on a block that no longer ran on Monday, which no save
    accepts; a finished session keeps the time it was done in.
    """
    return json.loads(
        flexweek_engine.reuse_apply_plan(
            json.dumps(blocks),
            json.dumps(trace),
            None if targets is None else json.dumps(list(targets)),
            None if assignments is None else json.dumps(assignments),
            week_start,
        )
    )


def clear_stale_pins(blocks: list[dict]) -> list[dict]:
    """Drop `pinned` from any session that no longer has one time on one day. The server refuses a
    week with such a pin, so every save would fail after the first edit that took the time away."""
    return json.loads(flexweek_engine.reuse_clear_pins(json.dumps(blocks)))


def held_in_place(block: dict) -> dict:
    """Planned homework as the solver should see it while other work is placed: time already taken.
    A work session cannot be sent as a fixed block with its assignment, so only its time goes."""
    return json.loads(flexweek_engine.reuse_held(json.dumps(block)))


def plan_start(week_start: str, now: datetime) -> tuple[int, int] | None:
    """The first time a plan may use in this week, as (day, minute): now, rounded up to the next
    quarter hour. None while the whole week is still ahead; a day past Sunday once it is over."""
    return flexweek_engine.reuse_plan_start(week_start, now)


def solve_request(
    blocks: list[dict],
    assignments: dict,
    week_start: str,
    *,
    everything: bool = False,
    only: set[str] | None = None,
    not_before: tuple[int, int] | None = None,
) -> tuple[list[dict], set[str]]:
    """What to send the solver, and which sessions its answer may place.

    By default planned homework keeps its time and only homework without one is placed around it.
    `everything` places every unfinished session again, with every day up to its deadline open.
    `only` places just those sessions around everything else, for work whose time stopped working.
    `not_before` (from `plan_start`) keeps every placement at or after now.
    """
    payload, targets = flexweek_engine.reuse_solve_request(
        json.dumps(blocks), json.dumps(assignments), week_start, everything, only, not_before
    )
    return json.loads(payload), set(json.loads(targets))


def due_point(due: str | None, week_start: str) -> tuple[int, int] | None:
    """A deadline as (day index, minute) in this week: negative before it, None when it is later."""
    point = flexweek_engine.reuse_due_point(json.dumps(due), week_start)
    return None if point is None else (int(point[0]), int(point[1]))


def settle_placements(
    blocks: list[dict],
    assignments: dict,
    week_start: str,
    keep: set[str] | frozenset[str] = frozenset(),
) -> tuple[list[dict], list[dict]]:
    """Take the time away from planned homework whose slot no longer works, and from nothing else.

    A fixed commitment added or moved over it, a missed day undone, a deadline moved earlier: each can
    leave one session sitting where it can no longer be done. Every other session keeps its time. The
    one that lost it gets back every day up to its deadline and a sentence saying why. `keep` names
    homework the student just placed themselves; when two sessions collide, the other one gives way.

    Homework the student placed by hand, pinned, is theirs: nothing sitting on it takes its time, and
    it takes time from nothing, since the student chose to put the two side by side.
    """
    kept, lost = flexweek_engine.reuse_settle_placements(
        json.dumps(blocks), json.dumps(assignments), week_start, keep
    )
    return json.loads(kept), json.loads(lost)


def occurrence_days(block: dict) -> list[int]:
    return json.loads(flexweek_engine.reuse_occurrence_days(json.dumps(block)))


def session_minutes(blocks: list[dict], assignment_id: str) -> int:
    return int(flexweek_engine.reuse_session_minutes(json.dumps(blocks), json.dumps(assignment_id)))


def available_homework_minutes(
    assignment: dict | None,
    blocks: list[dict],
    committed_blocks: list[dict] | None = None,
) -> int:
    return int(
        flexweek_engine.reuse_available_minutes(
            json.dumps(assignment),
            json.dumps(blocks),
            json.dumps(committed_blocks),
        )
    )


def copied_fixed_block(source: dict, days: list[int], block_id: str) -> dict:
    return json.loads(
        flexweek_engine.reuse_copied_fixed(json.dumps(source), json.dumps(days), json.dumps(block_id))
    )


def copied_homework_block(assignment: dict, day: int, duration: int, block_id: str) -> dict:
    return json.loads(
        flexweek_engine.reuse_copied_homework(json.dumps(assignment), day, duration, json.dumps(block_id))
    )


def clipboard_item(block: dict, source_day: int, scope: str, group_id: str) -> dict:
    return json.loads(flexweek_engine.reuse_clipboard_item(json.dumps(block), source_day, scope, group_id))


def clipboard_fingerprint(items: list[dict]) -> str:
    return str(flexweek_engine.reuse_fingerprint(json.dumps(items)))


def block_occurs_on_day(block: dict, day: int, placed: list[dict] | None = None) -> bool:
    return bool(
        flexweek_engine.reuse_occurs(
            json.dumps(block), json.dumps(day), None if placed is None else json.dumps(placed)
        )
    )


def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return bool(flexweek_engine.reuse_overlap(start_a, end_a, start_b, end_b))


def row_conflict(row: dict, rows: list[dict], existing: list[dict]) -> str | None:
    title = flexweek_engine.reuse_row_conflict(row, rows, existing)
    return None if title is None else json.loads(title)


def proposals_from_clipboard(
    items: list[dict],
    *,
    kind: str,
    week_start: str,
    target_day: int,
    target_start: str | None,
    assignments: dict[str, dict],
    available: dict[str, int],
) -> list[dict]:
    return json.loads(
        flexweek_engine.reuse_proposals(
            json.dumps(items),
            kind,
            week_start,
            target_day,
            target_start,
            json.dumps(assignments),
            json.dumps(available),
        )
    )


def merge_preview_rows(rows: list[dict], operation_id: str) -> list[dict]:
    return json.loads(flexweek_engine.reuse_merge_rows(json.dumps(rows), operation_id))


def capacity_problem(existing_count: int, added_count: int, label: str) -> str:
    return str(flexweek_engine.reuse_capacity(existing_count, added_count, label))


def preview_conflict_message(row: dict, rows: list[dict], existing: list[dict]) -> str:
    return json.loads(flexweek_engine.reuse_preview_message(row, rows, existing))


def routine_source_blocks(blocks: list[dict]) -> list[dict]:
    return json.loads(flexweek_engine.reuse_routine_sources(json.dumps(blocks)))


def routine_template(block: dict, template_id: str) -> dict:
    return json.loads(flexweek_engine.reuse_routine_template(json.dumps(block), template_id))


def routine_rows(routine: dict, week_start: str, allowed_days: list[int]) -> list[dict]:
    return json.loads(
        flexweek_engine.reuse_routine_rows(json.dumps(routine), week_start, json.dumps(allowed_days))
    )


def unfinished_items(
    assignments: dict[str, dict],
    saved_weeks: list[str],
    week_start: str,
    blocks: list[dict],
    committed_blocks: list[dict],
) -> list[dict]:
    return json.loads(
        flexweek_engine.reuse_unfinished(
            json.dumps(assignments),
            json.dumps(saved_weeks),
            week_start,
            json.dumps(blocks),
            json.dumps(committed_blocks),
        )
    )


def late_from_start(minute: int) -> str:
    return str(flexweek_engine.reuse_late_from(minute))


def running_late_block(day: int, from_start: str, minutes: int, block_id: str) -> dict:
    return json.loads(
        flexweek_engine.reuse_late_block(json.dumps(day), from_start, minutes, json.dumps(block_id))
    )


def running_late_refusal(
    *,
    week_start: str,
    now: datetime,
    dirty: bool,
    conflict: bool,
    block_count: int,
) -> str | None:
    return flexweek_engine.reuse_late_refusal(week_start, now, dirty, conflict, block_count)


def late_locked_line(block: dict, moved: int) -> str:
    return str(flexweek_engine.reuse_late_line(json.dumps(block), json.dumps(moved)))


def late_id(operation_id: str) -> str:
    return str(flexweek_engine.reuse_late_id(operation_id))


def copy_label(block: dict, source_day: int, scope: str) -> str:
    return json.loads(
        flexweek_engine.reuse_copy_label(json.dumps(block), json.dumps(source_day), json.dumps(scope))
    )


def planner_title(session: object, view: str, *, short: bool = False, selected_day: str | None = None) -> str:
    """Where you are, in words: "15 – 21 Sep", "Thursday 18 September", "September 2026".

    The week always uses short month names. `short` also abbreviates Day and Month for a narrow bar.
    The year shows on a day only when it is not the session's current year.

    The top bar used to say none of this. It had two buttons reading "Previous week" and "Next week"
    and no statement of which week you were on at all.
    """
    return str(
        flexweek_engine.reuse_planner_title(session, view, short, selected_day, datetime.fromtimestamp)
    )
