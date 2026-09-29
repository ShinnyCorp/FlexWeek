"""The week model is the one reading of the week every layout shares, so it is held to two things:
the placement rules written out as literal cases, and agreement with what the week table draws.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

from desktop.native.weekmodel import build_week, clock_label, due_label, length_label, planned_line

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


def thursday() -> list[tuple[str, str, str]]:
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    return [(item.block_id, clock_label(item.start), clock_label(item.end)) for item in week.on_day(3)]


def test_the_solver_placement_gives_unscheduled_work_its_time() -> None:
    assert thursday() == [
        ("school", "08:00", "14:30"),
        ("dinner", "18:00", "18:30"),
        ("essay-1", "18:45", "19:45"),
        ("chem-1", "20:00", "21:30"),
    ]


def test_a_finished_session_stays_on_the_day_it_was_finished() -> None:
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    math = [(item.day, item.done) for item in week.occurrences if item.block_id == "math-1"]
    assert math == [(0, True)]


def test_a_solver_placement_never_moves_finished_work() -> None:
    moved = {**TRACE, "placed": [*TRACE["placed"], block("math-1", "flexible", [4], "10:00", 45)]}
    week = build_week(WEEK, BLOCKS, HOMEWORK, moved)
    assert [
        (item.day, clock_label(item.start)) for item in week.occurrences if item.block_id == "math-1"
    ] == [(0, "15:45")]


def test_work_with_no_time_waits_with_the_solvers_reason() -> None:
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    assert [(item.title, item.minutes, item.reason) for item in week.waiting] == [
        ("Poster-1", 120, "There is not enough time left before it is due, even with nothing else planned.")
    ]


def test_work_nobody_has_planned_yet_says_so() -> None:
    week = build_week(WEEK, BLOCKS, HOMEWORK, None)
    assert [(item.block_id, item.reason) for item in week.waiting] == [
        ("chem-1", "Not planned yet."),
        ("poster-1", "Not planned yet."),
    ]


def test_waiting_work_that_shares_a_due_date_comes_in_title_order_whatever_the_ids() -> None:
    titles = ["Zoology", "Algebra", "Music", "Biology"]
    homework = {t: {"id": t, "title": t, "due": "2026-09-17T23:59", "completed": False} for t in titles}
    for ids in (["a", "b", "c", "d"], ["d", "c", "b", "a"], ["q", "z", "b", "m"]):
        blocks = [
            block(block_id, "flexible", [], None, 30, title=title, assignment_id=title)
            for block_id, title in zip(ids, titles, strict=True)
        ]
        for order in (blocks, blocks[::-1]):
            week = build_week(WEEK, order, homework, None)
            assert [item.title for item in week.waiting] == ["Algebra", "Biology", "Music", "Zoology"]


def test_waiting_work_with_the_same_due_and_title_breaks_the_tie_by_id() -> None:
    homework = {"essay": {"id": "essay", "title": "Essay", "due": "2026-09-17T23:59", "completed": False}}
    blocks = [block(i, "flexible", [], None, 30, title="Essay", assignment_id="essay") for i in ("s2", "s1")]
    assert [item.block_id for item in build_week(WEEK, blocks, homework, None).waiting] == ["s1", "s2"]


def test_risk_is_the_solvers_verdict_and_the_most_squeezed_comes_first() -> None:
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    assert [(item.block_id, item.slack, item.slack_words) for item in week.open_work()] == [
        ("chem-1", "danger", "Cutting it close"),
        ("essay-1", "tight", "Tight"),
    ]


def test_without_a_verdict_no_risk_is_claimed() -> None:
    week = build_week(WEEK, BLOCKS, HOMEWORK, None)
    assert [(item.block_id, item.slack, item.slack_words) for item in week.open_work()] == [
        ("essay-1", None, "")
    ]


def test_load_counts_homework_minutes_only() -> None:
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    assert [week.load_min(day) for day in range(7)] == [45, 0, 0, 150, 0, 0, 0]


def test_planned_line_uses_length_label() -> None:
    assert planned_line(60, 0) == "1 h planned · 0 done"
    assert planned_line(90, 45) == "1 h 30 min planned · 45 min done"
    assert planned_line(0, 0) == "Nothing planned yet"


def test_the_day_queue_is_what_is_on_now_then_the_rest_in_order() -> None:
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    lunch = week.day_queue(3, 13 * 60 + 40)
    assert lunch.current is not None and lunch.current.block_id == "school"
    assert [item.block_id for item in lunch.queue] == ["school", "dinner", "essay-1", "chem-1"]
    evening = week.day_queue(3, 19 * 60)
    assert evening.current is not None and evening.current.block_id == "essay-1"
    assert [item.block_id for item in evening.queue] == ["essay-1", "chem-1"]
    night = week.day_queue(3, 22 * 60)
    assert night.current is None and night.queue == ()


def test_homework_wins_over_the_fixed_block_around_it() -> None:
    blocks = [*BLOCKS, block("study-hall", "flexible", [3], "10:00", 30, assignment_id="essay")]
    week = build_week(WEEK, blocks, HOMEWORK, TRACE)
    current = week.day_queue(3, 10 * 60 + 10).current
    assert current is not None and current.block_id == "study-hall"


def test_finished_and_missed_homework_leave_the_queue() -> None:
    blocks = [
        block("essay-1", "flexible", [3], "18:45", 60, assignment_id="essay", missed_days=[3]),
        block("chem-1", "flexible", [3], "20:00", 90, assignment_id="chem", completed=True),
    ]
    week = build_week(WEEK, blocks, HOMEWORK, None)
    assert week.day_queue(3, 18 * 60).queue == ()
    assert [(item.block_id, item.missed, item.done) for item in week.on_day(3)] == [
        ("essay-1", True, False),
        ("chem-1", False, True),
    ]


def test_focus_is_what_the_timer_credited_to_this_weeks_homework_and_blocks() -> None:
    """The timer adds its minutes to the homework, or to a block with no homework. The week counts
    the homework it has sessions of, each once however many sessions, and its other blocks; homework
    with no session this week is another week's."""
    homework = {
        **HOMEWORK,
        "chem": {**HOMEWORK["chem"], "focus_minutes": 25},
        "essay": {**HOMEWORK["essay"], "focus_minutes": 15},
        "later": {"id": "later", "title": "Next week's reading", "due": "2026-09-25", "focus_minutes": 40},
    }
    blocks = [
        *BLOCKS,
        block("essay-2", "flexible", [4], "17:00", 30, assignment_id="essay"),
        block("piano", "locked", [2], "17:00", 45, focus_minutes=10),
    ]
    assert build_week(WEEK, blocks, homework, TRACE).focus_min == 25 + 15 + 10
    assert build_week(WEEK, BLOCKS, HOMEWORK, TRACE).focus_min == 0


def test_homework_the_account_marks_complete_is_done_even_if_the_block_is_not() -> None:
    blocks = [block("math-2", "flexible", [2], "16:00", 30, assignment_id="math")]
    week = build_week(WEEK, blocks, HOMEWORK, None)
    assert [(item.block_id, item.done) for item in week.occurrences] == [("math-2", True)]


def test_a_homework_session_saved_without_a_category_is_still_homework() -> None:
    blocks = [
        {**block("essay-1", "flexible", [3], "18:45", 60, assignment_id="essay"), "category": None},
        {**block("vocab-1", "flexible", [4], "15:30", 30, assignment_id="essay"), "category": "study"},
        {**block("waits", "flexible", [], None, 30, assignment_id="essay"), "category": None},
        {**block("club", "locked", [2], "15:00", 60), "category": None},
    ]
    week = build_week(WEEK, blocks, HOMEWORK, None)
    assert [(item.block_id, item.category) for item in week.occurrences] == [
        ("club", ""),
        ("essay-1", "assignments"),
        ("vocab-1", "study"),
    ]
    assert [(item.block_id, item.category) for item in week.waiting] == [("waits", "assignments")]


def test_a_block_cannot_run_past_midnight() -> None:
    week = build_week(WEEK, [block("late", "locked", [0], "23:30", 90)], {}, None)
    assert [(clock_label(item.start), clock_label(item.end)) for item in week.occurrences] == [
        ("23:30", "24:00")
    ]


def test_labels_read_the_way_a_student_says_them() -> None:
    assert [length_label(value) for value in (30, 60, 90, 0)] == ["30 min", "1 h", "1 h 30 min", "0 min"]
    assert due_label("2026-09-17T23:59", WEEK) == "Thu 17 Sep"
    assert due_label("2026-09-27", WEEK) == "Sun 27 Sep"
    assert due_label("2026-09-27T09:00", WEEK) == "Sun 27 Sep, 09:00"
    assert due_label("2026-09-28T08:00", WEEK) == "Mon 28 Sep, 08:00"
    assert due_label("2026-09-20", WEEK) == "Sun 20 Sep"
    assert due_label(None, WEEK) == ""


def test_due_today_unplaced_is_homework_that_still_needs_a_time() -> None:
    blocks = [
        block("math-u", "flexible", [3], None, 45, assignment_id="math", title="Math worksheet"),
    ]
    homework = {
        "math": {
            "id": "math",
            "title": "Math worksheet",
            "due": "2026-09-17T21:00",
            "completed": False,
        }
    }
    week = build_week(WEEK, blocks, homework, None)
    assert [item.title for item in week.due_today_unplaced(3)] == ["Math worksheet"]
    assert week.due_today_unplaced(2) == ()
    assert week.leftover_kind(3) == "needs_time"
    assert week.leftover_words(3) == "Not placed yet"
    assert week.leftover_parts(3) == ("Not placed yet", "Math worksheet", "Due Thu 17 Sep, 21:00")
    assert week.minutes_left_today(3, 16 * 60) == 45


def test_waiting_homework_is_ordered_by_when_it_must_end() -> None:
    blocks = [
        block("all", "flexible", [], None, 30, assignment_id="all", title="All day"),
        block("am", "flexible", [], None, 30, assignment_id="am", title="Morning"),
    ]
    homework = {
        "all": {"id": "all", "title": "All day", "due": "2026-09-17", "completed": False},
        "am": {"id": "am", "title": "Morning", "due": "2026-09-17T09:00", "completed": False},
    }
    week = build_week(WEEK, blocks, homework, None)
    assert [item.title for item in week.waiting] == ["Morning", "All day"]


def test_leftover_kind_splits_the_four_empty_days() -> None:
    empty = build_week(WEEK, [], {}, None)
    assert empty.leftover_kind(3) == "no_homework"
    assert empty.leftover_words(3) == "No homework added"
    done = build_week(
        WEEK,
        [
            block(
                "math-1",
                "flexible",
                [3],
                "15:00",
                45,
                assignment_id="math",
                title="Math worksheet",
                completed=True,
                completed_day=3,
            )
        ],
        {"math": {**HOMEWORK["math"], "completed": True}},
        None,
    )
    assert done.leftover_kind(3) == "all_finished"
    assert done.leftover_words(3) == "All homework finished"
    school = build_week(WEEK, [block("school", "locked", [3], "08:00", 390)], {}, None)
    assert school.leftover_kind(3) == "calendar_only"
    assert school.leftover_words(3) == "Nothing else scheduled today"


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
