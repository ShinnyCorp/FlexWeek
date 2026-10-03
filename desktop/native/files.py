"""Week and day file payloads. Parse, merge and homework identity. No Qt."""

from __future__ import annotations

import json
from typing import cast

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import AssignmentContent, TimeBlock
from desktop.native.wire import plain, restore

EXPORT_FORMAT = "flexweek-week"
DAY_FORMAT = "flexweek-day"
EXPORT_VERSION = 2


def assignment_body(item: dict) -> dict:
    fields = list(AssignmentContent.model_fields)
    body = AssignmentContent.model_validate(
        restore(json.loads(flexweek_engine.files_assignment_input(plain(item), fields)))
    ).model_dump(mode="json")
    return body


def exportable_block(block: dict, assignments: dict) -> dict:
    copy = json.loads(flexweek_engine.files_export_input(json.dumps(block), json.dumps(assignments)))
    return TimeBlock.model_validate(copy).model_dump(mode="json")


def _block_models(items: list[dict]) -> list[dict]:
    return [TimeBlock.model_validate(item).model_dump(mode="json") for item in items]


def _bodies(ids: str, failure: Exception | None, assignments: dict) -> list[dict]:
    """The model's body for each homework id; a failure the engine stopped at is raised after them."""
    bodies = [assignment_body(assignments[item_id]) for item_id in json.loads(ids)]
    if failure is not None:
        raise failure
    return bodies


def _exported_blocks(blocks: list[dict], assignments: dict, day_text: str | None) -> list[dict]:
    inputs, failure = flexweek_engine.files_block_inputs(
        json.dumps(blocks), json.dumps(assignments), day_text
    )
    exported = _block_models(json.loads(inputs))
    if failure is not None:
        raise failure
    return exported


def _export_payload(week_start: str, day_text: str | None, blocks: list[dict], assignments: dict) -> dict:
    exported = _exported_blocks(blocks, assignments, day_text)
    payload, ids, failure = flexweek_engine.files_export_rest(
        json.dumps(week_start), day_text, json.dumps(exported), json.dumps(assignments)
    )
    bodies = _bodies(ids, failure, assignments)
    return json.loads(flexweek_engine.files_export_finish(payload, json.dumps(bodies)))


def referenced_assignments(blocks: list[dict], assignments: dict) -> list[dict]:
    ids, failure = flexweek_engine.files_referenced_ids(json.dumps(blocks), json.dumps(assignments))
    return _bodies(ids, failure, assignments)


def export_week_payload(week_start: str, blocks: list[dict], assignments: dict) -> dict:
    return _export_payload(week_start, None, blocks, assignments)


def export_day_payload(week_start: str, day: int, blocks: list[dict], assignments: dict) -> dict:
    return _export_payload(week_start, json.dumps(day), blocks, assignments)


def _read_import(raw: str) -> tuple[bool, bool, str | None]:
    """Whether the file is empty, whether it reads as JSON, and what it read, as the engine takes it."""
    text = (raw or "").strip()
    if not text:
        return True, False, None
    try:
        return False, True, plain(json.loads(text))
    except ValueError:
        return False, False, None


def _checked_import(blocks: str, homework: str) -> tuple[list[dict], list[dict], str | None]:
    """The models' version of the file's blocks and homework, or the first complaint they make."""
    try:
        return (
            _block_models(_read_list(blocks)),
            [assignment_body(item) for item in _read_list(homework)],
            None,
        )
    except Exception as error:
        return [], [], str(error)


def _read_list(text: str) -> list[dict]:
    return cast(list[dict], restore(json.loads(text)))


def parse_import_payload(raw: str) -> dict:
    empty, readable, data = _read_import(raw)
    head, blocks, homework = flexweek_engine.files_import_start(empty, readable, data)
    checked, bodies, complaint = _checked_import(blocks, homework)
    return json.loads(
        flexweek_engine.files_import_finish(head, json.dumps(checked), json.dumps(bodies), complaint)
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
