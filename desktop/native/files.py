"""Week and day file payloads. Parse, merge and homework identity. No Qt."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import AssignmentContent, TimeBlock

EXPORT_FORMAT = "flexweek-week"
DAY_FORMAT = "flexweek-day"
EXPORT_VERSION = 2


def assignment_body(item: dict) -> dict:
    fields = list(AssignmentContent.model_fields)
    body = AssignmentContent.model_validate(
        json.loads(flexweek_engine.files_assignment_input(json.dumps(item), fields))
    ).model_dump(mode="json")
    return body


def exportable_block(block: dict, assignments: dict) -> dict:
    copy = json.loads(flexweek_engine.files_export_input(json.dumps(block), list(assignments)))
    return TimeBlock.model_validate(copy).model_dump(mode="json")


def referenced_assignments(blocks: list[dict], assignments: dict) -> list[dict]:
    ids, failure = flexweek_engine.files_referenced_ids(json.dumps(blocks), list(assignments))
    unique = [assignment_body(assignments[item_id]) for item_id in ids]
    if failure is not None:
        raise failure
    return unique


def export_week_payload(week_start: str, blocks: list[dict], assignments: dict) -> dict:
    return json.loads(
        flexweek_engine.files_export_week(week_start, json.dumps(blocks), json.dumps(assignments))
    )


def export_day_payload(week_start: str, day: int, blocks: list[dict], assignments: dict) -> dict:
    return json.loads(
        flexweek_engine.files_export_day(week_start, day, json.dumps(blocks), json.dumps(assignments))
    )


def parse_import_payload(raw: str) -> dict:
    return json.loads(flexweek_engine.files_parse_import(raw))


def occurrence_import_id(day: int, block_id: str) -> str:
    return str(flexweek_engine.files_occurrence_id(day, block_id))


def plan_imported_homework(
    homework: list[dict], blocks: list[dict], week_start: str, assignments: dict
) -> dict:
    return json.loads(
        flexweek_engine.files_plan_homework(
            json.dumps(homework), json.dumps(blocks), week_start, json.dumps(assignments)
        )
    )


def merge_imported_blocks(
    existing: list[dict], incoming: list[dict], mode: str, day: int | None
) -> list[dict]:
    return json.loads(flexweek_engine.files_merge(json.dumps(existing), json.dumps(incoming), mode, day))
