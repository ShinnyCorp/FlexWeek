"""Day agenda assembly. No HTTP, no database."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import TimeBlock


def is_work_session(block: dict) -> bool:
    return bool(flexweek_engine.is_work_session(json.dumps(block)))


def build_day(
    date_str: str,
    week_start: str,
    blocks: list[dict],
    assignment_rows: list[tuple[dict, int]],
    weeks: list[tuple[str, list[dict]]],
) -> dict:
    raw = json.loads(
        flexweek_engine.build_day(
            date_str,
            week_start,
            json.dumps(blocks),
            json.dumps([[body, revision] for body, revision in assignment_rows]),
            json.dumps([[start, week_blocks] for start, week_blocks in weeks]),
        )
    )
    raw["sessions"] = [TimeBlock.model_validate(block).model_dump() for block in raw["sessions"]]
    raw["locked"] = [TimeBlock.model_validate(block).model_dump() for block in raw["locked"]]
    return raw
