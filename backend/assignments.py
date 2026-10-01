"""Assignment helpers. No HTTP, no database."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import TimeBlock


def migrated_assignment_id(week_start: str, source_id: str) -> str:
    return flexweek_engine.migrated_assignment_id(week_start, source_id)


def due_from_latest(week_start: str, latest: str | None, days: list[int]) -> str:
    return flexweek_engine.due_from_latest(week_start, latest, days)


def completed_at_for_block(week_start: str, block: dict) -> str:
    return flexweek_engine.completed_at_for_block(week_start, json.dumps(block))


def due_placement_bound(week_start: str, due: str) -> tuple[int, int] | None:
    bound = flexweek_engine.due_placement_bound(week_start, due)
    if bound is None:
        return None
    return (int(bound[0]), int(bound[1]))


def due_slack_point(week_start: str, due: str) -> tuple[int, int]:
    day, minute = flexweek_engine.due_slack_point(week_start, due)
    return (int(day), int(minute))


def prepare_solve(
    blocks: list[TimeBlock],
    week_start: str,
    assignments: dict[str, dict],
) -> tuple[list[TimeBlock], dict[str, tuple[int, int] | None], dict[str, tuple[int, int]]]:
    raw = json.loads(
        flexweek_engine.prepare_solve(
            json.dumps([block.model_dump() for block in blocks]),
            week_start,
            json.dumps(assignments),
        )
    )
    keep = [TimeBlock.model_validate(item) for item in raw["keep"]]
    deadlines = {
        key: None if value is None else (int(value[0]), int(value[1]))
        for key, value in raw["deadlines"].items()
    }
    slack = {key: (int(value[0]), int(value[1])) for key, value in raw["slack"].items()}
    return keep, deadlines, slack


def legacy_session(week_start: str, block: TimeBlock) -> tuple[TimeBlock, dict]:
    session, body = json.loads(flexweek_engine.legacy_session(week_start, json.dumps(block.model_dump())))
    return TimeBlock.model_validate(session), body


def rewrite_session(block: TimeBlock, assignment: dict) -> TimeBlock:
    raw = json.loads(flexweek_engine.rewrite_session(json.dumps(block.model_dump()), json.dumps(assignment)))
    return TimeBlock.model_validate(raw)


def planned_minutes_by_id(weeks: list[tuple[str, list[dict]]], from_week: str) -> dict[str, int]:
    raw = json.loads(flexweek_engine.planned_minutes_by_id(json.dumps(weeks), from_week))
    return {key: int(value) for key, value in raw.items()}


def unplanned_minutes(estimate_min: int, focus_minutes: int, planned: int) -> int:
    return flexweek_engine.unplanned_minutes(estimate_min, focus_minutes, planned)


def migrate_blocks(week_start: str, blocks: list[dict]) -> tuple[list[dict], list[dict]]:
    updated, created = json.loads(flexweek_engine.migrate_blocks(week_start, json.dumps(blocks)))
    return updated, created
