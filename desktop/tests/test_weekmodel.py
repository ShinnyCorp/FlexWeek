"""The week model is the one reading of the week every layout shares. Its placement rules are tested
in engine/engine/tests/desk_weekmodel.rs; this file keeps the agreement with what the week table
draws, and the week every layout test builds from.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

from desktop.native.weekmodel import build_week

WEEK = "2026-09-14"
HOMEWORK = {
    "chem": {"id": "chem", "title": "Chem lab report", "due": "2026-09-17T23:59", "completed": False},
    "essay": {"id": "essay", "title": "History essay", "due": "2026-09-18T21:00", "completed": False},
    "poster": {"id": "poster", "title": "Science fair poster", "due": "2026-09-20T20:00", "completed": False},
    "math": {"id": "math", "title": "Math worksheet", "due": "2026-09-15T08:00", "completed": True},
}


def block(
    block_id: str, kind: str, days: list[int], start: str | None, minutes: int, **extra: object
) -> dict:
    return {
        "id": block_id,
        "title": extra.pop("title", block_id.title()),
        "kind": kind,
        "category": extra.pop("category", "class" if kind == "locked" else "assignments"),
        "days": days,
        "start": start,
        "duration_min": minutes,
        **extra,
    }


BLOCKS = [
    block("school", "locked", [0, 1, 2, 3, 4], "08:00", 390),
    block("dinner", "locked", [0, 1, 2, 3, 4, 5, 6], "18:00", 30, category="meals"),
    block("chem-1", "flexible", [3], None, 90, assignment_id="chem"),
    block("essay-1", "flexible", [3], "18:45", 60, assignment_id="essay"),
    block("poster-1", "flexible", [], None, 120, assignment_id="poster"),
    block("math-1", "flexible", [0, 1], "15:45", 45, assignment_id="math", completed=True, completed_day=0),
]
TRACE = {
    "placed": [block("chem-1", "flexible", [3], "20:00", 90, assignment_id="chem")],
    "unplaced": [block("poster-1", "flexible", [], None, 120, assignment_id="poster")],
    "explanations": [
        {
            "block_id": "chem-1",
            "message": "Finishes only 2 h 29 min before it is due.",
            "slack_min": 149,
            "slack_status": "danger",
        },
        {
            "block_id": "essay-1",
            "message": "Finishes 25 h 15 min before it is due.",
            "slack_min": 1515,
            "slack_status": "tight",
        },
        {
            "block_id": "poster-1",
            "message": "There is not enough time left before it is due, even with nothing else planned.",
            "reason": "DEADLINE_MISS",
        },
    ],
}


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent")
def test_the_model_places_every_block_where_the_week_calendar_draws_it() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget

    from desktop.native.hours.classic import ClassicWeek
    from desktop.native.hours.hand import Hand, Verdict

    app = QApplication.instance() or QApplication(["flexweek-weekmodel-test"])
    host = QWidget()
    calendar = ClassicWeek(Hand(lambda block_id, from_day, span: Verdict(False, ""), host), host)
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    calendar.set_week(week, None, None)
    calendar.resize(980, 640)
    calendar.hours.relayout()
    hours = calendar.hours
    drawn = {
        (item.block_id, item.span.day, item.span.start)
        for track in hours.tracks
        for item, _rect in hours.drawn(track)
    }
    modelled = {(item.block_id, item.day, item.start) for item in week.occurrences}
    assert modelled == drawn
    assert len(drawn) == 15
    del app
