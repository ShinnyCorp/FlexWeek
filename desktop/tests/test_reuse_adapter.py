"""What the reuse wrapper still decides in Python: `row_conflict` finds the row's own place in the
preview rows by object identity before asking the engine, so a row never conflicts with itself."""

from __future__ import annotations

from desktop.native.reuse import proposals_from_clipboard, row_conflict


def soccer() -> dict:
    return {
        "id": "soccer",
        "title": "Soccer",
        "kind": "locked",
        "duration_min": 60,
        "days": [0, 2],
        "start": "16:00",
        "category": "exercise",
    }


def test_paste_of_a_fixed_block_onto_the_same_slot_conflicts() -> None:
    source = soccer()
    items = [{"block": source, "source_day": 0, "scope": "occurrence", "group_id": "g1"}]
    rows = proposals_from_clipboard(
        items,
        kind="block",
        week_start="2026-09-07",
        target_day=0,
        target_start="16:00",
        assignments={},
        available={},
    )
    assert row_conflict(rows[0], rows, [source]) == "Soccer"
    rows[0]["block"]["start"] = "18:00"
    assert row_conflict(rows[0], rows, [source]) is None


def test_adjacent_blocks_do_not_conflict() -> None:
    existing = [soccer()]
    row = {
        "week_start": "2026-09-07",
        "day": 0,
        "fixed": True,
        "checked": True,
        "block": {"title": "Piano", "start": "17:00", "duration_min": 30, "days": [0]},
    }
    assert row_conflict(row, [row], existing) is None
