"""Day agenda assembly. No HTTP, no database."""

from __future__ import annotations

from datetime import date, timedelta

from backend.tests.engine_ref.assignments import planned_minutes_by_id, unplanned_minutes
from backend.tests.engine_ref.models import TimeBlock, due_sort_key, parse_due
from backend.tests.engine_ref.slots import SLOT_MIN, SLOTS_PER_DAY, block_interval_on_day, occupancy_between


def is_work_session(block: dict) -> bool:
    if not block.get("assignment_id"):
        return False
    if block.get("kind") == "flexible":
        return True
    return block.get("kind") == "locked" and block.get("pomodoro_role") == "work"


def _on_day(block: dict, day_index: int) -> bool:
    days = list(block.get("days") or [])
    if block.get("kind") == "flexible" and block.get("completed"):
        # A completed session keeps its candidate list, so counting every candidate
        # would bill one finished hour to three days. completed_day names the slot it
        # held; a lone candidate is its own. Same rule as occurrenceDays in app.js.
        pinned = block.get("completed_day")
        if pinned is None:
            return len(days) == 1 and days[0] == day_index
        return int(pinned) == day_index
    return day_index in days


def _dump(block: dict) -> dict:
    return TimeBlock.model_validate(block).model_dump()


def _due_soon(
    assignment_rows: list[tuple[dict, int]],
    agenda: date,
    week_start: str,
    weeks: list[tuple[str, list[dict]]],
) -> list[dict]:
    planned = planned_minutes_by_id(weeks, week_start)
    tomorrow = agenda + timedelta(days=1)
    items = []
    for body, revision in assignment_rows:
        if body.get("completed"):
            continue
        due_day, _minutes = parse_due(body["due"])
        if due_day > tomorrow:
            continue
        items.append(
            {
                **body,
                "revision": revision,
                "planned_min": planned.get(body["id"], 0),
                "unplanned_min": unplanned_minutes(
                    int(body["estimate_min"]), int(body["focus_minutes"]), planned.get(body["id"], 0)
                ),
            }
        )
    items.sort(key=lambda item: due_sort_key(item["due"], item["id"]))
    return items


def _available_min(blocks: list[dict], day_index: int) -> int:
    mask = 0
    for raw in blocks:
        if not _on_day(raw, day_index) or not raw.get("start"):
            continue
        interval = block_interval_on_day(TimeBlock.model_validate(raw), day_index)
        if interval is None:
            continue
        mask |= occupancy_between(*interval)
    return (SLOTS_PER_DAY - mask.bit_count()) * SLOT_MIN


def _planned(block: dict) -> bool:
    """Work with a time, or work already done that day. Homework still waiting for a time is offered on
    every day it could go, and counting it there billed one hour to each of them as "planned". Done
    work stays in, so focus time is never more than planned time, as in Month."""
    return bool(block.get("start") or block.get("completed"))


def _by_category(sessions: list[dict], locked: list[dict]) -> list[dict]:
    groups: dict[str | None, dict[str, int]] = {}
    for block in sessions + locked:
        category = block.get("category")
        group = groups.setdefault(category, {"scheduled_min": 0, "focus_min": 0})
        duration = int(block["duration_min"])
        if _planned(block):
            group["scheduled_min"] += duration
        if is_work_session(block) and block.get("completed"):
            group["focus_min"] += duration
    ordered = sorted(
        groups.items(),
        key=lambda item: (-item[1]["scheduled_min"], item[0] or ""),
    )
    return [
        {"category": category, "scheduled_min": group["scheduled_min"], "focus_min": group["focus_min"]}
        for category, group in ordered
        if group["scheduled_min"] or group["focus_min"]
    ]


def _next_action(sessions: list[dict], due_soon: list[dict]) -> dict:
    starters = [block for block in sessions if block.get("start") and not block.get("completed")]
    starters.sort(key=lambda block: (block["start"], block["id"]))
    if starters:
        return {"kind": "start", "block_id": starters[0]["id"]}
    for item in due_soon:
        if item["unplanned_min"] > 0:
            return {"kind": "plan", "assignment_id": item["id"]}
    return {"kind": "add"}


def build_day(
    date_str: str,
    week_start: str,
    blocks: list[dict],
    assignment_rows: list[tuple[dict, int]],
    weeks: list[tuple[str, list[dict]]],
) -> dict:
    agenda = date.fromisoformat(date_str)
    day_index = (agenda - date.fromisoformat(week_start)).days
    sessions = [_dump(block) for block in blocks if is_work_session(block) and _on_day(block, day_index)]
    locked = [
        _dump(block)
        for block in blocks
        if block.get("kind") == "locked" and not is_work_session(block) and _on_day(block, day_index)
    ]
    due_soon = _due_soon(assignment_rows, agenda, week_start, weeks)
    scheduled = sum(int(block["duration_min"]) for block in sessions + locked if _planned(block))
    focus = sum(int(block["duration_min"]) for block in sessions if block.get("completed"))
    return {
        "date": date_str,
        "week_start": week_start,
        "due_soon": due_soon,
        "sessions": sessions,
        "locked": locked,
        "next_action": _next_action(sessions, due_soon),
        "workload": {
            "scheduled_min": scheduled,
            "focus_min": focus,
            "available_min": _available_min(blocks, day_index),
            "by_category": _by_category(sessions, locked),
        },
    }
