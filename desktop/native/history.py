"""Undo and redo snapshots for the native week on screen. No Qt. The engine keeps the steps."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

HISTORY_LIMIT = 50


def same_value(left: object, right: object) -> bool:
    return bool(
        flexweek_engine.history_same_value(
            json.dumps(left, sort_keys=True, default=str),
            json.dumps(right, sort_keys=True, default=str),
        )
    )


def capture_step(
    label: str,
    week_start: str,
    before_blocks: list[dict],
    after_blocks: list[dict],
    before_assignments: dict[str, dict],
    after_assignments: dict[str, dict],
    changed_ids: set[str],
) -> dict | None:
    raw = flexweek_engine.history_capture_step(
        label,
        week_start,
        json.dumps(before_blocks),
        json.dumps(after_blocks),
        json.dumps(before_assignments),
        json.dumps(after_assignments),
        sorted(changed_ids),
    )
    return None if raw is None else json.loads(raw)


def push_step(stack: list[dict], step: dict) -> None:
    stack.append(step)
    if flexweek_engine.history_over_limit(len(stack)):
        del stack[0]


def join_step(stack: list[dict], step: dict) -> None:
    """Fold `step` into the step before it, so one Undo takes both back: homework added and the time
    FlexWeek gave it straight after. Each week and assignment keeps the earlier before and the later
    after."""
    if not stack or stack[-1].get("stale"):
        push_step(stack, step)
        return
    stack[-1] = json.loads(flexweek_engine.history_joined(json.dumps(stack[-1]), json.dumps(step)))


def mark_stale(steps: list[dict], week_start: str) -> None:
    for step in steps:
        if flexweek_engine.history_touches(json.dumps(step), json.dumps(week_start)):
            step["stale"] = True
