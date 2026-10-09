"""What the solver said has to reach the student.

spec.md: FlexWeek "explains in plain English every time something could not be placed or had to
move". The client took one explanation out of however many the solver gave, dropped it in the status
line, and never mentioned a move outside Running late.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    from desktop.native.widgets import PlanReview

WEEK = "2026-09-14"
TITLES = {"poster": "Science fair poster", "essay": "History essay", "chem": "Chem lab report"}
TRACE = {
    "placed": [{"id": "essay"}, {"id": "chem"}],
    "unplaced": [{"id": "poster", "title": "Science fair poster"}],
    "moves": [
        {
            "block_id": "essay",
            "reason": "RESHUFFLE_AFTER_MISS",
            "from_day": 3,
            "from_start": "18:45",
            "to_day": 4,
            "to_start": "10:00",
        }
    ],
    "explanations": [
        {
            "block_id": "poster",
            "reason": "DEADLINE_MISS",
            "message": "There is not enough time left before it is due, even with nothing else planned.",
        },
        {
            "block_id": "chem",
            "message": "Finishes only 29 min before it is due.",
            "slack_min": 29,
            "slack_status": "danger",
        },
        {
            "block_id": "essay",
            "message": "Finishes 5 h before it is due.",
            "slack_min": 300,
            "slack_status": "ok",
        },
    ],
}


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-plan-review-test"])
    yield application


def test_it_says_what_could_not_be_placed_and_why(qapp: QApplication) -> None:
    said = PlanReview().rows_for(TRACE, TITLES, WEEK)
    assert (
        "Science fair poster has no time yet."
        " There is not enough time left before it is due, even with nothing else planned."
    ) in said


def test_it_says_what_moved_and_why(qapp: QApplication) -> None:
    said = PlanReview().rows_for(TRACE, TITLES, WEEK)
    moved = [line for line in said if "moved" in line]
    assert moved == [
        "History essay moved from Thu 18:45 to Fri 10:00."
        " Moved because you missed a day, so the rest of the week still fits."
    ]


def test_a_move_after_running_late_says_so_not_that_a_day_was_missed(qapp: QApplication) -> None:
    """Running late files its moves under the missed-day code, with a sentence of its own."""
    from backend.availability import LATE_COPY

    late = {
        **TRACE,
        "explanations": [
            *TRACE["explanations"],
            {"block_id": "essay", "reason": "RESHUFFLE_AFTER_MISS", "message": LATE_COPY},
        ],
    }
    moved = [line for line in PlanReview().rows_for(late, TITLES, WEEK) if "moved" in line]
    assert moved == ["History essay moved from Thu 18:45 to Fri 10:00. " + LATE_COPY]


def test_it_warns_about_a_tight_deadline_but_not_a_comfortable_one(qapp: QApplication) -> None:
    said = PlanReview().rows_for(TRACE, TITLES, WEEK)
    assert "Chem lab report: Finishes only 29 min before it is due." in said
    assert not any(line.startswith("History essay: ") for line in said)


def test_every_explanation_survives_not_just_the_first(qapp: QApplication) -> None:
    """The old status line showed notes[0] and dropped the rest."""
    assert len(PlanReview().rows_for(TRACE, TITLES, WEEK)) == 3


def test_a_clean_plan_says_nothing(qapp: QApplication) -> None:
    panel = PlanReview()
    panel.set_trace(
        {"placed": [{"id": "essay"}], "unplaced": [], "moves": [], "explanations": []}, TITLES, WEEK, (1, 0)
    )
    assert panel.isVisible() is False
    assert panel.rows_for({"placed": [], "unplaced": [], "moves": [], "explanations": []}, TITLES, WEEK) == []


def test_the_panel_shows_the_count_and_can_be_dismissed(qapp: QApplication) -> None:
    from PySide6.QtWidgets import QPushButton

    panel = PlanReview()
    panel.show()
    # The plan's own counts, not the trace's lists, which hold every block with a time.
    panel.set_trace(TRACE, TITLES, WEEK, (1, 1))
    qapp.processEvents()
    assert panel.isVisible() is True
    from desktop.native.controller import plan_sentence

    assert panel.heading.text() == plan_sentence(1, 1)
    assert panel.list.count() == 3
    # Something has no time, so why is open already; Details folds it away.
    assert panel.list.isVisible()
    panel.findChild(QPushButton, "planReviewDetails").click()
    assert not panel.list.isVisible()
    panel.set_trace({**TRACE, "unplaced": []}, TITLES, WEEK, (2, 0))
    assert panel.heading.text() == plan_sentence(2, 0) and not panel.list.isVisible()
    seen: list[str] = []
    panel.dismissed.connect(lambda: seen.append("dismissed"))
    panel.findChild(QPushButton, "planReviewDismiss").click()
    assert seen == ["dismissed"] and panel.isVisible() is False


def test_an_unplaced_task_with_no_explanation_still_says_something(qapp: QApplication) -> None:
    bare = {
        "placed": [],
        "unplaced": [{"id": "poster", "title": "Science fair poster"}],
        "moves": [],
        "explanations": [],
    }
    assert PlanReview().rows_for(bare, TITLES, WEEK) == [
        "Science fair poster has no time yet. There was no room for it this week."
    ]


def test_a_block_that_never_moved_is_not_announced_as_moving(qapp: QApplication) -> None:
    """The solver records a move with no times for work that stayed unplaced. Said out loud that
    read "moved from no time to no time", under a line that had already explained the same block."""
    trace = {
        "placed": [],
        "unplaced": [{"id": "poster", "title": "Science fair poster"}],
        "moves": [
            {
                "block_id": "poster",
                "reason": "DEADLINE_MISS",
                "from_day": None,
                "from_start": None,
                "to_day": None,
                "to_start": None,
            }
        ],
        "explanations": [
            {
                "block_id": "poster",
                "reason": "DEADLINE_MISS",
                "message": "There is not enough time left before it is due, even with nothing else planned.",
            }
        ],
    }
    said = PlanReview().rows_for(trace, TITLES, WEEK)
    assert said == [
        "Science fair poster has no time yet."
        " There is not enough time left before it is due, even with nothing else planned."
    ]
    assert not any("no time to no time" in line for line in said)


def test_a_half_known_move_is_not_announced_either(qapp: QApplication) -> None:
    trace = {
        "placed": [{"id": "essay"}],
        "unplaced": [],
        "moves": [
            {
                "block_id": "essay",
                "reason": "NO_SLOT_LEFT",
                "from_day": 3,
                "from_start": "18:45",
                "to_day": None,
                "to_start": None,
            }
        ],
        "explanations": [],
    }
    assert PlanReview().rows_for(trace, TITLES, WEEK) == []


def test_the_box_is_as_tall_as_it_needs_and_no_taller(qapp: QApplication) -> None:
    """One line in a box four lines deep reads as an error."""
    one = PlanReview()
    one.show()
    one.set_trace(
        {
            "placed": [],
            "unplaced": [{"id": "poster", "title": "Science fair poster"}],
            "moves": [],
            "explanations": [],
        },
        TITLES,
        WEEK,
        (0, 1),
    )
    qapp.processEvents()
    many = PlanReview()
    many.show()
    many.set_trace(TRACE, TITLES, WEEK, (1, 1))
    qapp.processEvents()
    assert one.list.height() < many.list.height()
    assert many.list.height() <= 132


def sessions(*per_day: tuple[int, int]) -> list[dict]:
    """Homework sessions as the solver's trace lists them: (day, minutes) each."""
    return [
        {
            "id": f"hw-{index}",
            "kind": "flexible",
            "assignment_id": f"a-{index}",
            "start": "16:00",
            "days": [day],
            "duration_min": minutes,
        }
        for index, (day, minutes) in enumerate(per_day)
    ]


def overfull_lines(placed: list[dict]) -> list[str]:
    trace = {"placed": placed, "unplaced": [], "moves": [], "explanations": []}
    return PlanReview().rows_for(trace, {}, WEEK)


def test_a_day_with_more_than_three_hours_of_homework_is_named_with_its_total(qapp: QApplication) -> None:
    # Thursday: 2 h + 2 h 30 min. Monday stays under: 1 h 30 min + 1 h 30 min is exactly 3 h.
    placed = sessions((3, 120), (3, 150), (0, 90), (0, 90))
    assert overfull_lines(placed) == ["Thursday has 4 h 30 min of homework."]


def test_exactly_three_hours_on_a_day_is_not_overfull(qapp: QApplication) -> None:
    assert overfull_lines(sessions((1, 100), (1, 80))) == []


def test_one_minute_over_three_hours_is_overfull(qapp: QApplication) -> None:
    assert overfull_lines(sessions((2, 181))) == ["Wednesday has 3 h 1 min of homework."]


def test_only_homework_counts_toward_a_full_day(qapp: QApplication) -> None:
    school = {"id": "school", "kind": "locked", "start": "08:00", "days": [0], "duration_min": 390}
    assert overfull_lines([school, *sessions((0, 60))]) == []


def test_each_overfull_day_gets_its_own_sentence_in_week_order(qapp: QApplication) -> None:
    placed = sessions((4, 200), (1, 190))
    assert overfull_lines(placed) == [
        "Tuesday has 3 h 10 min of homework.",
        "Friday has 3 h 20 min of homework.",
    ]


def test_an_overfull_day_opens_the_panel_even_when_everything_has_a_time(qapp: QApplication) -> None:
    panel = PlanReview()
    panel.show()
    trace = {"placed": sessions((3, 330)), "unplaced": [], "moves": [], "explanations": []}
    panel.set_trace(trace, {}, WEEK, (1, 0))
    qapp.processEvents()
    assert panel.isVisible() and panel.list.isVisible()
    assert [panel.list.item(i).text() for i in range(panel.list.count())] == [
        "Thursday has 5 h 30 min of homework."
    ]
