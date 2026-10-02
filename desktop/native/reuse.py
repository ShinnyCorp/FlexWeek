"""Clipboard, collision previews and Stage 3/4 planning helpers. No Qt."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import due_sort_key
from backend.slots import SLOT_MIN
from desktop.native.weekmodel import length_label

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


def week_label(week_start: str) -> str:
    return str(flexweek_engine.reuse_week_label(week_start))


def floor_slot(minutes: int) -> int:
    return int(flexweek_engine.reuse_floor_slot(minutes))


def is_homework_session(block: dict) -> bool:
    return bool(flexweek_engine.reuse_homework(json.dumps(block)))


def session_days(week_start: str, due: str) -> list[int]:
    return [int(day) for day in flexweek_engine.reuse_session_days(week_start, due)]


def is_planned(block: dict) -> bool:
    """Unfinished homework with its own time: one day and a start. Such a block is the student's plan,
    not a request to be planned, so nothing moves it unless its time stops working or they ask."""
    return bool(flexweek_engine.reuse_planned(json.dumps(block)))


def planning_days(block: dict, assignments: dict, week_start: str) -> list[int]:
    """The days homework may go on when it needs a new time. A plan narrows a session to the day it
    chose, so the days up to the deadline come back from the assignment rather than from the block."""
    return [
        int(day)
        for day in flexweek_engine.reuse_planning_days(
            json.dumps(block), json.dumps(assignments), week_start
        )
    ]


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
            None if trace is None else json.dumps(trace),
            None if targets is None else json.dumps(sorted(targets)),
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
    point = flexweek_engine.reuse_plan_start(
        week_start,
        now.date().isoformat(),
        now.hour * 60 + now.minute,
        bool(now.second or now.microsecond),
    )
    return None if point is None else (int(point[0]), int(point[1]))


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
    day = minute = None
    if not_before is not None:
        day, minute = not_before
    payload, targets = flexweek_engine.solve_request(
        json.dumps(blocks),
        json.dumps(assignments),
        week_start,
        everything,
        None if only is None else sorted(only),
        day,
        minute,
    )
    return json.loads(payload), set(targets)





def due_point(due: str | None, week_start: str) -> tuple[int, int] | None:
    """A deadline as (day index, minute) in this week: negative before it, None when it is later."""
    if not due:
        return None
    point = flexweek_engine.reuse_due_point(due, week_start)
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
    kept, lost = flexweek_engine.settle_placements(
        json.dumps(blocks), json.dumps(assignments), week_start, sorted(keep)
    )
    return json.loads(kept), json.loads(lost)



def occurrence_days(block: dict) -> list[int]:
    return [int(day) for day in flexweek_engine.reuse_occurrence_days(json.dumps(block or {}))]



def session_minutes(blocks: list[dict], assignment_id: str) -> int:
    return int(flexweek_engine.reuse_session_minutes(json.dumps(blocks), assignment_id))



def available_homework_minutes(
    assignment: dict | None,
    blocks: list[dict],
    committed_blocks: list[dict] | None = None,
) -> int:
    return int(
        flexweek_engine.reuse_available_minutes(
            None if assignment is None else json.dumps(assignment),
            json.dumps(blocks),
            None if committed_blocks is None else json.dumps(committed_blocks),
        )
    )



def copied_fixed_block(source: dict, days: list[int], block_id: str) -> dict:
    return json.loads(flexweek_engine.reuse_copied_fixed(json.dumps(source), json.dumps(days), block_id))



def copied_homework_block(assignment: dict, day: int, duration: int, block_id: str) -> dict:
    return json.loads(
        flexweek_engine.reuse_copied_homework(json.dumps(assignment), day, duration, block_id)
    )



def clipboard_item(block: dict, source_day: int, scope: str, group_id: str) -> dict:
    return json.loads(
        flexweek_engine.reuse_clipboard_item(json.dumps(block), source_day, scope, group_id)
    )



def clipboard_fingerprint(items: list[dict]) -> str:
    return str(flexweek_engine.reuse_fingerprint(json.dumps(items)))



def block_occurs_on_day(block: dict, day: int, placed: list[dict] | None = None) -> bool:
    return bool(
        flexweek_engine.reuse_occurs(
            json.dumps(block), day, None if placed is None else json.dumps(placed)
        )
    )



def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return bool(flexweek_engine.reuse_overlap(start_a, end_a, start_b, end_b))



def row_conflict(row: dict, rows: list[dict], existing: list[dict]) -> str | None:
    skip = next((index for index, item in enumerate(rows) if item is row), None)
    return flexweek_engine.reuse_row_conflict(
        json.dumps(row), json.dumps(rows), json.dumps(existing), skip
    )


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
    rows: list[dict] = []
    left = dict(available)
    for item_index, item in enumerate(items):
        source = item["block"]
        if is_homework_session(source):
            assignment = assignments.get(source["assignment_id"])
            remaining = left.get(source["assignment_id"], 0)
            duration = min(int(source["duration_min"]), remaining)
            usable = bool(assignment and duration >= SLOT_MIN)
            if usable:
                left[source["assignment_id"]] = remaining - duration
            if usable and assignment is not None:
                block = copied_homework_block(assignment, target_day, duration, item["group_id"])
                invalid = ""
            else:
                block = deepcopy(source)
                invalid = (
                    "No unplanned time remains for this homework."
                    if assignment
                    else "This homework did not load."
                )
            rows.append(
                {
                    "week_start": week_start,
                    "day": target_day,
                    "fixed": False,
                    "block": block,
                    "group_id": item["group_id"],
                    "checked": usable,
                    "invalid": invalid,
                    "original_duration": int(source["duration_min"]),
                }
            )
            continue
        days = list(source["days"]) if item["scope"] == "series" else [target_day]
        for day_index, day in enumerate(days):
            start = (
                target_start
                if target_start and kind == "block" and item["scope"] != "series"
                else source.get("start")
            )
            block = copied_fixed_block(source, [day], item["group_id"])
            block["start"] = start
            group_id = (
                item["group_id"]
                if item["scope"] == "series"
                else f"{item['group_id']}-{item_index}-{day_index}"
            )
            rows.append(
                {
                    "week_start": week_start,
                    "day": day,
                    "fixed": True,
                    "block": block,
                    "group_id": group_id,
                    "original_duration": int(source["duration_min"]),
                    "checked": True,
                    "invalid": "" if start else "Choose a start time.",
                }
            )
    return rows


def merge_preview_rows(rows: list[dict], operation_id: str) -> list[dict]:
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for row in rows:
        if not row.get("checked"):
            continue
        block = deepcopy(row["block"])
        if row.get("fixed"):
            block["days"] = [row["day"]]
        shape = {key: value for key, value in block.items() if key not in {"id", "days"}}
        key = (row["week_start"], row["group_id"], json.dumps(shape, sort_keys=True, default=str))
        if key not in groups:
            groups[key] = {"week_start": row["week_start"], "block": block, "days": []}
            order.append(key)
        groups[key]["days"].append(row["day"])
    stem = operation_id.replace("-", "")[:24]
    result = []
    for index, key in enumerate(order):
        group = groups[key]
        group["block"]["id"] = f"b-stage3-{stem}-{index:x}"
        group["block"]["days"] = sorted(set(group["days"]))
        result.append({"week_start": group["week_start"], "block": group["block"]})
    return result



def capacity_problem(existing_count: int, added_count: int, label: str) -> str:
    return str(flexweek_engine.reuse_capacity(existing_count, added_count, label))


def preview_conflict_message(row: dict, rows: list[dict], existing: list[dict]) -> str:
    if row.get("invalid"):
        return row["invalid"]
    conflict = row_conflict(row, rows, existing)
    if conflict:
        return f"Conflicts with {conflict}. Choose another time."
    if row.get("fixed"):
        return length_label(int(row["block"]["duration_min"])) + " · Only this week"
    return length_label(int(row["block"]["duration_min"])) + " · Time chosen when you plan"


def routine_source_blocks(blocks: list[dict]) -> list[dict]:
    return [
        block
        for block in blocks
        if block.get("kind") == "locked" and not block.get("assignment_id") and not block.get("pomodoro_role")
    ]


def routine_template(block: dict, template_id: str) -> dict:
    body: dict = {"template_id": template_id, "title": block["title"], "days": list(block["days"])}
    body["start"] = block["start"]
    body["duration_min"] = block["duration_min"]
    for field in ROUTINE_FIELDS:
        if field in {"template_id", "title", "days", "start", "duration_min"}:
            continue
        value = block.get(field)
        if value is not None:
            body[field] = value
    return body


def routine_rows(routine: dict, week_start: str, allowed_days: list[int]) -> list[dict]:
    rows: list[dict] = []
    allowed = set(allowed_days)
    for template in routine.get("blocks") or []:
        group_id = template["template_id"]
        for day in template.get("days") or []:
            if day not in allowed:
                continue
            block = copied_fixed_block({**template, "kind": "locked"}, [day], group_id)
            block.pop("template_id", None)
            rows.append(
                {
                    "week_start": week_start,
                    "day": day,
                    "fixed": True,
                    "block": block,
                    "group_id": group_id,
                    "original_duration": int(template["duration_min"]),
                    "checked": True,
                    "invalid": "",
                }
            )
    return rows


def unfinished_items(
    assignments: dict[str, dict],
    saved_weeks: list[str],
    week_start: str,
    blocks: list[dict],
    committed_blocks: list[dict],
) -> list[dict]:
    if not any(saved < week_start for saved in saved_weeks):
        return []
    items = []
    for item in assignments.values():
        minutes = available_homework_minutes(item, blocks, committed_blocks)
        if item.get("completed") or minutes < SLOT_MIN:
            continue
        items.append({**item, "remaining_min": minutes})
    return sorted(items, key=lambda item: due_sort_key(item.get("due"), item["id"]))



def late_from_start(minute: int) -> str:
    return str(flexweek_engine.reuse_late_from(minute))



def running_late_block(day: int, from_start: str, minutes: int, block_id: str) -> dict:
    return json.loads(flexweek_engine.reuse_late_block(day, from_start, minutes, block_id))



def running_late_refusal(
    *,
    week_start: str,
    now: datetime,
    dirty: bool,
    conflict: bool,
    block_count: int,
) -> str | None:
    return flexweek_engine.reuse_late_refusal(
        week_start, now.date().isoformat(), dirty, conflict, block_count
    )



def late_locked_line(block: dict, moved: int) -> str:
    return str(flexweek_engine.reuse_late_line(json.dumps(block), moved))



def late_id(operation_id: str) -> str:
    return str(flexweek_engine.reuse_late_id(operation_id))



def copy_label(block: dict, source_day: int, scope: str) -> str:
    return str(flexweek_engine.reuse_copy_label(json.dumps(block), source_day, scope))


DAYS_LONG = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def planner_title(
    session: object, view: str, *, short: bool = False, selected_day: str | None = None
) -> str:
    """Where you are, in words: "15 – 21 September", "Thursday 18 September", "September 2026".

    Week always uses short month names. `short` also abbreviates Day and Month for a narrow bar.

    The top bar used to say none of this. It had two buttons reading "Previous week" and "Next week"
    and no statement of which week you were on at all.
    """

    def name(names: tuple[str, ...], index: int) -> str:
        return names[index][:3] if short else names[index]

    start = date.fromisoformat(session.week_start)
    # selected_day is an ISO date, not an index into the week. Reading it as one raised on a real
    # run and left the title blank.
    chosen_iso = selected_day or getattr(session, "selected_day", None) or session.week_start
    try:
        chosen = date.fromisoformat(str(chosen_iso))
    except ValueError:
        chosen = start
    if view == "month":
        # Month has an anchor of its own, which is what the grid is showing.
        anchor_iso = getattr(session, "selected_month", None) or chosen_iso
        try:
            anchor = date.fromisoformat(
                str(anchor_iso) + "-01" if len(str(anchor_iso)) == 7 else str(anchor_iso)
            )
        except ValueError:
            anchor = chosen
        return f"{name(MONTHS, anchor.month - 1)} {anchor.year}"
    if view == "myday" and selected_day is None:
        chosen = datetime.fromtimestamp(session.now_ms() / 1000).date()
    if view in {"day", "myday"}:
        return f"{name(DAYS_LONG, chosen.weekday())} {chosen.day} {name(MONTHS, chosen.month - 1)}"
    short = True
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.day} – {end.day} {name(MONTHS, start.month - 1)}"
    return f"{start.day} {name(MONTHS, start.month - 1)} – {end.day} {name(MONTHS, end.month - 1)}"
