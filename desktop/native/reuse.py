"""Clipboard, collision previews and Stage 3/4 planning helpers. No Qt."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta

from backend.models import due_sort_key, parse_due
from backend.slots import DAY_END_MIN, DAY_START_MIN, SLOT_MIN, hhmm_to_minutes, minutes_to_hhmm
from desktop.native.calendar import DAY_FULL
from desktop.native.weekmodel import clock_text, hhmm_text, length_label

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
    characters = list(text)
    if len(characters) <= 80:
        return text
    return "".join(characters[:79]) + "…"


def week_label(week_start: str) -> str:
    return "Week of " + week_start


def floor_slot(minutes: int) -> int:
    return max(0, minutes) // SLOT_MIN * SLOT_MIN


def is_homework_session(block: dict) -> bool:
    return bool(block.get("assignment_id"))


def session_days(week_start: str, due: str) -> list[int]:
    monday = date.fromisoformat(week_start)
    due_day = date.fromisoformat(due[:10])
    last = monday + timedelta(days=6)
    if due_day < monday:
        return [0]
    if due_day > last:
        return [0, 1, 2, 3, 4]
    return list(range(due_day.weekday() + 1))


def is_planned(block: dict) -> bool:
    """Unfinished homework with its own time: one day and a start. Such a block is the student's plan,
    not a request to be planned, so nothing moves it unless its time stops working or they ask."""
    return (
        block.get("kind") == "flexible"
        and bool(block.get("start"))
        and not block.get("completed")
        and len(block.get("days") or []) == 1
    )


def planning_days(block: dict, assignments: dict, week_start: str) -> list[int]:
    """The days homework may go on when it needs a new time. A plan narrows a session to the day it
    chose, so the days up to the deadline come back from the assignment rather than from the block."""
    assignment = assignments.get(block.get("assignment_id") or "")
    if assignment and assignment.get("due"):
        return session_days(week_start, assignment["due"])
    return list(block.get("days") or [0])


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
    placed = {item["id"]: item for item in (trace or {}).get("placed") or []}
    unplaced_ids = {item["id"] for item in (trace or {}).get("unplaced") or []}
    out = []
    for block in blocks:
        copy = dict(block)
        unplanned_work = copy.get("kind") == "flexible" and not copy.get("completed")
        if not unplanned_work or (targets is not None and copy["id"] not in targets):
            out.append(copy)
            continue
        winner = placed.get(copy["id"])
        if winner and winner.get("start"):
            copy["start"] = winner["start"]
            if winner.get("days"):
                copy["days"] = list(winner["days"])
        elif copy["id"] in unplaced_ids:
            copy.pop("pinned", None)
            if copy.pop("start", None) and assignments is not None and week_start is not None:
                copy["days"] = planning_days(copy, assignments, week_start)
        out.append(copy)
    return out


def clear_stale_pins(blocks: list[dict]) -> list[dict]:
    """Drop `pinned` from any session that no longer has one time on one day. The server refuses a
    week with such a pin, so every save would fail after the first edit that took the time away."""
    return [
        {key: value for key, value in block.items() if key != "pinned"}
        if block.get("pinned") and not (block.get("start") and len(block.get("days") or []) == 1)
        else block
        for block in blocks
    ]


def held_in_place(block: dict) -> dict:
    """Planned homework as the solver should see it while other work is placed: time already taken.
    A work session cannot be sent as a fixed block with its assignment, so only its time goes."""
    return {
        "id": block["id"],
        "title": block.get("title") or "Homework",
        "kind": "locked",
        "duration_min": block["duration_min"],
        "days": list(block["days"]),
        "start": block["start"],
    }


def plan_start(week_start: str, now: datetime) -> tuple[int, int] | None:
    """The first time a plan may use in this week, as (day, minute): now, rounded up to the next
    quarter hour. None while the whole week is still ahead; a day past Sunday once it is over."""
    day = (now.date() - date.fromisoformat(week_start)).days
    if day < 0:
        return None
    minute = now.hour * 60 + now.minute + (1 if now.second or now.microsecond else 0)
    minute = -(-minute // SLOT_MIN) * SLOT_MIN
    if minute >= DAY_END_MIN:
        return day + 1, DAY_START_MIN
    return day, minute


def _begun(block: dict, not_before: tuple[int, int] | None) -> bool:
    return not_before is not None and (block["days"][0], hhmm_to_minutes(block["start"])) < not_before


def _from(session: dict, not_before: tuple[int, int]) -> dict:
    """A session the solver may place no earlier than `not_before`, said as the earliest start the
    model already has, so the reasons it gives stay true. The days already gone come off; with none
    left it keeps today, so the solver says it is too late for it rather than that it does not fit."""
    day, minute = not_before
    days = [item for item in session["days"] if item >= day] or [day]
    return {**session, "days": days, "earliest": f"{DAY_FULL[day]} {minutes_to_hhmm(minute)}"}


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
    payload: list[dict] = []
    targets: set[str] = set()
    for block in blocks:
        if block.get("kind") != "flexible" or block.get("completed"):
            payload.append(block)
            continue
        planned = is_planned(block)
        # Homework the student placed by hand stays put in Replan all, like a fixed block, and so does
        # homework whose time has already come: a plan does not reach back into the past.
        kept = planned and (bool(block.get("pinned")) or _begun(block, not_before))
        wanted = block["id"] in only if only is not None else (everything and not kept) or not planned
        if wanted:
            session = dict(block)
            if planned:
                session.pop("start")
                session["days"] = planning_days(block, assignments, week_start)
            payload.append(session if not_before is None else _from(session, not_before))
            targets.add(block["id"])
        elif planned:
            payload.append(held_in_place(block))
    return payload, targets


def due_point(due: str | None, week_start: str) -> tuple[int, int] | None:
    """A deadline as (day index, minute) in this week: negative before it, None when it is later."""
    if not due:
        return None
    due_day, minutes = parse_due(due)
    offset = (due_day - date.fromisoformat(week_start)).days
    if offset > 6:
        return None
    return offset, minutes


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
    taken: dict[int, list[tuple[int, int, str]]] = {day: [] for day in range(7)}
    for block in blocks:
        if not block.get("start"):
            continue
        start = hhmm_to_minutes(block["start"])
        end = start + int(block.get("duration_min") or 0)
        if block.get("kind") == "locked":
            for day in block.get("days") or []:
                if day not in (block.get("missed_days") or []):
                    taken[day].append((start, end, block.get("title") or "a fixed block"))
        elif block.get("completed"):
            days = block.get("days") or []
            day = block.get("completed_day", days[0] if len(days) == 1 else None)
            if day is not None:
                taken[day].append((start, end, block.get("title") or "finished work"))
    sessions = sorted(
        (block for block in blocks if is_planned(block)),
        key=lambda block: (block["id"] not in keep, block["days"][0], block["start"], block["id"]),
    )
    lost: dict[str, dict] = {}
    for block in sessions:
        day = block["days"][0]
        start = hhmm_to_minutes(block["start"])
        end = start + int(block.get("duration_min") or 0)
        assignment = assignments.get(block.get("assignment_id") or "") or {}
        due = due_point(assignment.get("due"), week_start)
        pinned = bool(block.get("pinned"))
        clashes = (title for low, high, title in taken[day] if start < high and low < end)
        clash = None if pinned else next(clashes, None)
        why = None
        if start < DAY_START_MIN or end > DAY_END_MIN:
            why = "that is outside the hours FlexWeek plans in"
        elif due is not None and (day, end) > due:
            why = "that is after it is due"
        elif clash is not None:
            why = f"{clash} is there now"
        if why is None:
            if not pinned:
                taken[day].append((start, end, block.get("title") or "homework"))
            continue
        title = block.get("title") or "Homework"
        lost[block["id"]] = {
            "block_id": block["id"],
            "assignment_id": block.get("assignment_id"),
            "title": title,
            "day": day,
            "start": block["start"],
            "message": f"{title} no longer fits {DAY_FULL[day]} at {hhmm_text(block['start'])}: {why}.",
        }
    if not lost:
        return blocks, []
    out = []
    for block in blocks:
        if block["id"] in lost:
            block = dict(block)
            block.pop("start")
            block.pop("pinned", None)
            block["days"] = planning_days(block, assignments, week_start)
        out.append(block)
    return out, [lost[block["id"]] for block in sessions if block["id"] in lost]


def occurrence_days(block: dict) -> list[int]:
    if block and block.get("kind") == "flexible" and block.get("completed"):
        completed_day = block.get("completed_day")
        if isinstance(completed_day, int):
            return [completed_day]
        if isinstance(block.get("days"), list) and len(block["days"]) > 1:
            return []
    return list((block or {}).get("days") or [])


def session_minutes(blocks: list[dict], assignment_id: str) -> int:
    total = 0
    for block in blocks:
        if block.get("assignment_id") == assignment_id and not block.get("completed"):
            total += int(block["duration_min"])
    return total


def available_homework_minutes(
    assignment: dict | None,
    blocks: list[dict],
    committed_blocks: list[dict] | None = None,
) -> int:
    if not assignment or assignment.get("completed"):
        return 0
    here = session_minutes(blocks, assignment["id"])
    committed = session_minutes(committed_blocks or [], assignment["id"])
    server = assignment.get("unplanned_min")
    if server is None:
        remaining = max(0, int(assignment["estimate_min"]) - int(assignment.get("focus_minutes") or 0))
        return floor_slot(remaining - here)
    return floor_slot(int(server) + committed - here)


def copied_fixed_block(source: dict, days: list[int], block_id: str) -> dict:
    copy = deepcopy(source)
    copy["id"] = block_id
    copy["kind"] = "locked"
    copy["days"] = list(days)
    copy["completed"] = False
    copy["completed_day"] = None
    copy["missed_days"] = []
    copy["focus_minutes"] = 0
    copy["focus_sessions"] = 0
    for key in ("assignment_id", "pomodoro_parent_id", "pomodoro_role", "pomodoro_index", "template_id"):
        copy.pop(key, None)
    return copy


def copied_homework_block(assignment: dict, day: int, duration: int, block_id: str) -> dict:
    return {
        "id": block_id,
        "kind": "flexible",
        "title": assignment["title"],
        "duration_min": duration,
        "days": [day],
        "start": None,
        "earliest": None,
        "latest": None,
        "priority": assignment.get("priority") or 3,
        "energy": assignment.get("energy") or "medium",
        "course": assignment.get("course"),
        "category": assignment.get("category"),
        "spotify_url": assignment.get("spotify_url"),
        "completed": False,
        "completed_day": None,
        "missed_days": [],
        "assignment_id": assignment["id"],
    }


def clipboard_item(block: dict, source_day: int, scope: str, group_id: str) -> dict:
    return {
        "block": deepcopy(block),
        "source_day": source_day,
        "scope": scope,
        "group_id": group_id,
    }


def clipboard_fingerprint(items: list[dict]) -> str:
    payload = [
        {"block": item["block"], "source_day": item["source_day"], "scope": item["scope"]} for item in items
    ]
    return json.dumps(payload, sort_keys=True, default=str)


def block_occurs_on_day(block: dict, day: int, placed: list[dict] | None = None) -> bool:
    if is_homework_session(block) or block.get("kind") == "flexible":
        source = block if block.get("start") else None
        if source is None and placed:
            source = next(
                (
                    item
                    for item in placed
                    if item.get("id") == block.get("id") and day in occurrence_days(item)
                ),
                None,
            )
        return bool(source and source.get("start") and day in occurrence_days(source))
    return day in occurrence_days(block)


def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def row_conflict(row: dict, rows: list[dict], existing: list[dict]) -> str | None:
    if not row.get("fixed") or not row["block"].get("start"):
        return None
    start = hhmm_to_minutes(row["block"]["start"])
    end = start + int(row["block"]["duration_min"])
    for block in existing:
        if not block.get("start") or row["day"] not in occurrence_days(block):
            continue
        other = hhmm_to_minutes(block["start"])
        if intervals_overlap(start, end, other, other + int(block["duration_min"])):
            return block["title"]
    for candidate in rows:
        if (
            candidate is row
            or not candidate.get("checked")
            or not candidate.get("fixed")
            or candidate["day"] != row["day"]
            or candidate.get("week_start") != row.get("week_start")
            or not candidate["block"].get("start")
        ):
            continue
        other = hhmm_to_minutes(candidate["block"]["start"])
        if intervals_overlap(start, end, other, other + int(candidate["block"]["duration_min"])):
            return candidate["block"]["title"]
    return None


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
    if existing_count + added_count > MAX_WEEK_BLOCKS:
        return f"{label} would exceed 100 blocks. Uncheck an item or remove a block first."
    return ""


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
    snapped = minute // SLOT_MIN * SLOT_MIN
    snapped = max(DAY_START_MIN, min(DAY_END_MIN - SLOT_MIN, snapped))
    return minutes_to_hhmm(snapped)


def running_late_block(day: int, from_start: str, minutes: int, block_id: str) -> dict:
    start = hhmm_to_minutes(from_start)
    duration = min(minutes, DAY_END_MIN - start)
    return {
        "id": block_id,
        "kind": "locked",
        "title": "Running late",
        "duration_min": duration,
        "days": [day],
        "start": from_start,
        "priority": 1,
        "energy": "medium",
        "category": "downtime",
        "completed": False,
        "missed_days": [],
    }


def running_late_refusal(
    *,
    week_start: str,
    now: datetime,
    dirty: bool,
    conflict: bool,
    block_count: int,
) -> str | None:
    today = now.date()
    this_week = (today - timedelta(days=today.weekday())).isoformat()
    if week_start != this_week:
        return "Open this week before using Running late."
    if conflict:
        return "This week was changed somewhere else. Reload it first."
    if dirty:
        return "Your last change is still saving. Try again in a moment."
    if block_count >= MAX_WEEK_BLOCKS:
        return "This week already has 100 blocks. Remove one before recording a late start."
    return None


def late_locked_line(block: dict, moved: int) -> str:
    start = hhmm_to_minutes(str(block["start"]))
    end = start + int(block["duration_min"])
    extra = f"{moved} moved." if moved else "Nothing had to move."
    return f"Running late: {clock_text(start)}–{clock_text(end)} is now locked. {extra}"


def late_id(operation_id: str) -> str:
    return "b-late-" + operation_id.replace("-", "")[:24]


def copy_label(block: dict, source_day: int, scope: str) -> str:
    title = block["title"]
    series = block.get("kind") == "locked" and len(block.get("days") or []) > 1
    if scope == "series":
        return f"{title} (all days)"
    if series:
        return f"{title} ({DAY_FULL[source_day]} only)"
    return title


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


def planner_title(session: object, view: str, *, short: bool = False) -> str:
    """Where you are, in words: "15 – 21 September", "Thursday 18 September", "September 2026".

    `short` abbreviates the names ("28 Sep – 4 Oct") for a bar with no room for them, so the whole
    range still reads rather than being cut after the first month.

    The top bar used to say none of this. It had two buttons reading "Previous week" and "Next week"
    and no statement of which week you were on at all.
    """
    from datetime import date, timedelta

    def name(names: tuple[str, ...], index: int) -> str:
        return names[index][:3] if short else names[index]

    start = date.fromisoformat(session.week_start)
    # selected_day is an ISO date, not an index into the week. Reading it as one raised on a real
    # run and left the title blank.
    chosen_iso = getattr(session, "selected_day", None) or session.week_start
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
    if view == "day":
        return f"{name(DAYS_LONG, chosen.weekday())} {chosen.day} {name(MONTHS, chosen.month - 1)}"
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.day} – {end.day} {name(MONTHS, start.month - 1)}"
    return f"{start.day} {name(MONTHS, start.month - 1)} – {end.day} {name(MONTHS, end.month - 1)}"
