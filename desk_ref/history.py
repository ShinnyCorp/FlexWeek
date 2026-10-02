"""Undo and redo snapshots for the native week on screen. No Qt."""

from __future__ import annotations

import json
from copy import deepcopy

HISTORY_LIMIT = 50


def same_value(left: object, right: object) -> bool:
    return json.dumps(left, sort_keys=True, default=str) == json.dumps(right, sort_keys=True, default=str)


def capture_step(
    label: str,
    week_start: str,
    before_blocks: list[dict],
    after_blocks: list[dict],
    before_assignments: dict[str, dict],
    after_assignments: dict[str, dict],
    changed_ids: set[str],
) -> dict | None:
    step: dict = {"label": label, "weeks": [], "assignments": [], "stale": False}
    if not same_value(before_blocks, after_blocks):
        step["weeks"].append(
            {
                "week_start": week_start,
                "before": deepcopy(before_blocks),
                "after": deepcopy(after_blocks),
            }
        )
    for item_id in sorted(changed_ids):
        prior = before_assignments.get(item_id)
        after = after_assignments.get(item_id)
        if same_value(prior, after):
            continue
        step["assignments"].append(
            {
                "id": item_id,
                "before": deepcopy(prior) if prior is not None else None,
                "after": deepcopy(after) if after is not None else None,
            }
        )
    if not step["weeks"] and not step["assignments"]:
        return None
    return step


def push_step(stack: list[dict], step: dict) -> None:
    stack.append(step)
    if len(stack) > HISTORY_LIMIT:
        del stack[0]


def join_step(stack: list[dict], step: dict) -> None:
    """Fold `step` into the step before it, so one Undo takes both back: homework added and the time
    FlexWeek gave it straight after. Each week and assignment keeps the earlier before and the later
    after."""
    if not stack or stack[-1].get("stale"):
        push_step(stack, step)
        return
    earlier = stack[-1]
    weeks = {entry["week_start"]: dict(entry) for entry in earlier["weeks"]}
    for entry in step["weeks"]:
        known = weeks.get(entry["week_start"])
        weeks[entry["week_start"]] = {**entry, "before": known["before"]} if known else dict(entry)
    assignments = {entry["id"]: dict(entry) for entry in earlier["assignments"]}
    for entry in step["assignments"]:
        known = assignments.get(entry["id"])
        assignments[entry["id"]] = {**entry, "before": known["before"]} if known else dict(entry)
    stack[-1] = {**earlier, "weeks": list(weeks.values()), "assignments": list(assignments.values())}


def mark_stale(steps: list[dict], week_start: str) -> None:
    for step in steps:
        if any(entry["week_start"] == week_start for entry in step.get("weeks") or []):
            step["stale"] = True
