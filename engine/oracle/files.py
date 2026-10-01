"""Week and day file payloads. Parse, merge and homework identity. No Qt."""

from __future__ import annotations

import json
from copy import deepcopy

from backend.tests.engine_ref.calendar import date_for_day, is_series
from backend.tests.engine_ref.reuse import MAX_WEEK_BLOCKS, occurrence_days

from backend.tests.engine_ref.assignments import migrated_assignment_id
from backend.tests.engine_ref.models import AssignmentContent, TimeBlock
from backend.tests.engine_ref.weeks import is_week_start

EXPORT_FORMAT = "flexweek-week"
DAY_FORMAT = "flexweek-day"
EXPORT_VERSION = 2


def assignment_body(item: dict) -> dict:
    body = AssignmentContent.model_validate(
        {key: value for key, value in item.items() if key in AssignmentContent.model_fields}
    ).model_dump(mode="json")
    return body


def exportable_block(block: dict, assignments: dict) -> dict:
    copy = deepcopy(block)
    if copy.get("assignment_id") and copy["assignment_id"] not in assignments:
        copy.pop("assignment_id", None)
    return TimeBlock.model_validate(copy).model_dump(mode="json")


def referenced_assignments(blocks: list[dict], assignments: dict) -> list[dict]:
    ids = [block.get("assignment_id") for block in blocks if block.get("assignment_id")]
    unique = []
    seen: set[str] = set()
    for item_id in ids:
        if item_id in seen or item_id not in assignments:
            continue
        seen.add(item_id)
        unique.append(assignment_body(assignments[item_id]))
    return unique


def export_week_payload(week_start: str, blocks: list[dict], assignments: dict) -> dict:
    exported = [exportable_block(block, assignments) for block in blocks]
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "week_start": week_start,
        "blocks": exported,
        "assignments": referenced_assignments(exported, assignments),
    }


def export_day_payload(week_start: str, day: int, blocks: list[dict], assignments: dict) -> dict:
    day_blocks = []
    for block in blocks:
        if day not in occurrence_days(block):
            continue
        copy = exportable_block(block, assignments)
        copy["days"] = [day]
        if copy.get("missed_days"):
            copy["missed_days"] = [item for item in copy["missed_days"] if item == day]
        day_blocks.append(copy)
    return {
        "format": DAY_FORMAT,
        "version": EXPORT_VERSION,
        "week_start": week_start,
        "date": date_for_day(week_start, day),
        "day": day,
        "blocks": day_blocks,
        "assignments": referenced_assignments(day_blocks, assignments),
    }


def parse_import_payload(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        return {"error": "Empty file."}
    try:
        data = json.loads(text)
    except ValueError:
        return {"error": "Not valid JSON. Plain-text import is export-only."}
    if not isinstance(data, dict):
        return {"error": "Invalid FlexWeek export."}
    if data.get("format") not in {EXPORT_FORMAT, DAY_FORMAT}:
        return {"error": "Unrecognized export format."}
    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        return {"error": "Export has no version."}
    if version > EXPORT_VERSION:
        return {"error": f"Export came from a newer FlexWeek (version {version})."}
    if not isinstance(data.get("blocks"), list):
        return {"error": "Export is missing blocks."}
    homework = data.get("assignments") if version >= 2 else []
    if not isinstance(homework, list):
        return {"error": "Export is missing its homework list."}
    week_start = data.get("week_start")
    if week_start and not is_week_start(week_start):
        return {"error": "Export week_start must be a Monday."}
    try:
        blocks = [TimeBlock.model_validate(block).model_dump(mode="json") for block in data["blocks"]]
        assignments = [assignment_body(item) for item in homework]
    except Exception as error:
        return {"error": str(error) + " Nothing was imported."}
    if data["format"] == DAY_FORMAT:
        day = data.get("day")
        if not isinstance(day, int) or day < 0 or day > 6:
            return {"error": "Day export must contain only its day in 0..6. Nothing was imported."}
        if any(block["days"] != [day] for block in blocks):
            return {"error": "Day export must contain only its day in 0..6. Nothing was imported."}
    ids = [block["id"] for block in blocks]
    if len(ids) > MAX_WEEK_BLOCKS:
        return {"error": f"Export has more than {MAX_WEEK_BLOCKS} blocks. Nothing was imported."}
    if len(ids) != len(set(ids)):
        return {"error": "Export repeats the id " + next(item for item in ids if ids.count(item) > 1) + "."}
    seen = set(ids)
    if any(block.get("pomodoro_parent_id") in seen for block in blocks):
        return {
            "error": "Export includes a task together with the focus chunks split from it. "
            "Nothing was imported."
        }
    homework_ids = [item["id"] for item in assignments]
    if version >= 2:
        if len(homework_ids) > MAX_WEEK_BLOCKS:
            return {"error": f"Export has more than {MAX_WEEK_BLOCKS} homework items. Nothing was imported."}
        if len(homework_ids) != len(set(homework_ids)):
            repeated = next(item for item in homework_ids if homework_ids.count(item) > 1)
            return {"error": "Export repeats the homework id " + repeated + ". Nothing was imported."}
        for index, block in enumerate(blocks):
            assignment_id = block.get("assignment_id")
            if assignment_id and assignment_id not in homework_ids:
                return {
                    "error": f"Block {index + 1} points at homework the file does not include. "
                    "Nothing was imported."
                }
    return {
        "format": data["format"],
        "week_start": week_start or None,
        "day": data.get("day") if isinstance(data.get("day"), int) else None,
        "blocks": blocks,
        "assignments": assignments,
        "error": None,
    }


def occurrence_import_id(day: int, block_id: str) -> str:
    prefix = f"occ-{day}-"
    legacy = prefix + block_id
    if len(legacy) <= 80:
        return legacy
    hash_val = 2166136261
    for character in block_id:
        hash_val ^= ord(character)
        hash_val = (hash_val * 16777619) & 0xFFFFFFFF
    suffix = "-" + format(hash_val, "08x")
    available = 80 - len(prefix + suffix)
    return prefix + block_id[:available] + suffix


def plan_imported_homework(
    homework: list[dict], blocks: list[dict], week_start: str, assignments: dict
) -> dict:
    id_for: dict[str, str] = {}
    create = []
    for item in homework:
        own = assignments.get(item["id"])
        if own and own.get("title") == item.get("title") and own.get("due") == item.get("due"):
            id_for[item["id"]] = item["id"]
            continue
        new_id = migrated_assignment_id(week_start, item["id"])
        if new_id not in assignments:
            created = deepcopy(item)
            created["id"] = new_id
            create.append(created)
        id_for[item["id"]] = new_id
    remapped = []
    for block in blocks:
        copy = deepcopy(block)
        source = copy.get("assignment_id")
        if source in id_for:
            copy["assignment_id"] = id_for[source]
        remapped.append(copy)
    return {"blocks": remapped, "create": create}


def merge_imported_blocks(
    existing: list[dict], incoming: list[dict], mode: str, day: int | None
) -> list[dict]:
    if mode == "replace":
        return [deepcopy(block) for block in incoming]
    by_id = {block["id"]: deepcopy(block) for block in existing}
    for block in incoming:
        if not block or not block.get("id"):
            continue
        current = by_id.get(block["id"])
        split_id = occurrence_import_id(day, block["id"]) if day is not None else ""
        prior_split = by_id.get(split_id)
        imports_one_day = isinstance(day, int) and (block.get("days") or []) == [day]
        if (
            current
            and imports_one_day
            and current.get("kind") == "flexible"
            and len(current.get("days") or []) > 1
        ):
            raise ValueError(
                "Day import cannot merge multi-day task " + block["id"] + ". Import the full week instead."
            )
        if (
            current
            and block.get("kind") == "locked"
            and current.get("kind") == "locked"
            and imports_one_day
            and day in (current.get("days") or [])
            and is_series(current)
        ):
            if prior_split:
                raise ValueError("Import would overwrite existing block " + split_id + ".")
            kept_days = [item for item in current["days"] if item != day]
            split = deepcopy(block)
            split["id"] = split_id
            split["days"] = [day]
            split["missed_days"] = [item for item in (split.get("missed_days") or []) if item == day]
            if kept_days:
                kept = deepcopy(current)
                kept["days"] = kept_days
                kept["missed_days"] = [item for item in (kept.get("missed_days") or []) if item in kept_days]
                by_id[current["id"]] = kept
            else:
                by_id.pop(current["id"], None)
            by_id[split["id"]] = split
            continue
        if (
            current
            and block.get("kind") == "locked"
            and current.get("kind") == "locked"
            and imports_one_day
            and day not in (current.get("days") or [])
            and prior_split
            and (prior_split.get("days") or []) == [day]
        ):
            split = deepcopy(block)
            split["id"] = split_id
            by_id[split_id] = split
            continue
        by_id[block["id"]] = deepcopy(block)
    return list(by_id.values())
