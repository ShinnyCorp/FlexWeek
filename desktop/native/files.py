"""Week and day file payloads. Parse, merge and homework identity. No Qt."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import AssignmentContent, TimeBlock
from desktop.native.calendar import date_for_day
from desktop.native.reuse import occurrence_days
from desktop.native.wire import plain

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
    copy = json.loads(flexweek_engine.files_export_input(json.dumps(block), json.dumps(assignments)))
    return TimeBlock.model_validate(copy).model_dump(mode="json")


def referenced_assignments(blocks: list[dict], assignments: dict) -> list[dict]:
    ids, failure = flexweek_engine.files_referenced_ids(json.dumps(blocks), json.dumps(assignments))
    unique = [assignment_body(assignments[item_id]) for item_id in json.loads(ids)]
    if failure is not None:
        raise failure
    return unique


def export_week_payload(week_start: str, blocks: list[dict], assignments: dict) -> dict:
    exported = [exportable_block(block, assignments) for block in blocks]
    return json.loads(
        flexweek_engine.files_export_week(
            json.dumps(week_start),
            json.dumps(exported),
            json.dumps(referenced_assignments(exported, assignments)),
        )
    )


def export_day_payload(week_start: str, day: int, blocks: list[dict], assignments: dict) -> dict:
    day_blocks = []
    for block in blocks:
        if day not in occurrence_days(block):
            continue
        copy = exportable_block(block, assignments)
        day_blocks.append(json.loads(flexweek_engine.files_day_copy(json.dumps(copy), json.dumps(day))))
    date = date_for_day(week_start, day)
    return json.loads(
        flexweek_engine.files_export_day(
            json.dumps(week_start),
            json.dumps(date),
            json.dumps(day),
            json.dumps(day_blocks),
            json.dumps(referenced_assignments(day_blocks, assignments)),
        )
    )


def parse_import_payload(raw: str) -> dict:
    text = (raw or "").strip()
    data = None
    readable = False
    if text:
        try:
            data = json.loads(text)
            readable = True
        except ValueError:
            readable = False
    head = json.loads(
        flexweek_engine.files_import_head(not text, readable, plain(data) if readable else None)
    )
    if head.get("error"):
        return head
    homework = data.get("assignments") if head["homework_from_file"] else []
    try:
        blocks = [TimeBlock.model_validate(block).model_dump(mode="json") for block in data["blocks"]]
        assignments = [assignment_body(item) for item in homework]
    except Exception as error:
        return {"error": str(error) + " Nothing was imported."}
    return json.loads(
        flexweek_engine.files_import_tail(json.dumps(head), json.dumps(blocks), json.dumps(assignments))
    )


def occurrence_import_id(day: int, block_id: str) -> str:
    return str(flexweek_engine.files_occurrence_id(json.dumps(day), json.dumps(block_id)))


def plan_imported_homework(
    homework: list[dict], blocks: list[dict], week_start: str, assignments: dict
) -> dict:
    return json.loads(
        flexweek_engine.files_plan_homework(
            json.dumps(homework), json.dumps(blocks), json.dumps(week_start), json.dumps(assignments)
        )
    )


def merge_imported_blocks(
    existing: list[dict], incoming: list[dict], mode: str, day: int | None
) -> list[dict]:
    return json.loads(
        flexweek_engine.files_merge(
            json.dumps(existing), json.dumps(incoming), json.dumps(mode), json.dumps(day)
        )
    )
