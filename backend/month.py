"""Month calendar assembly. No HTTP, no database."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]


def build_month(
    month: str,
    assignment_rows: list[tuple[dict, int]],
    weeks: list[tuple[str, list[dict]]],
) -> dict:
    return json.loads(
        flexweek_engine.build_month(
            month,
            json.dumps([[body, revision] for body, revision in assignment_rows]),
            json.dumps([[start, blocks] for start, blocks in weeks]),
        )
    )
