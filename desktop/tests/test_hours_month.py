"""Month as Daily Scheduler draws it, with chips that can be carried to another date.

These send Qt events, so they prove the rules; the rig (scripts/rig/drive.py) carries chips with a
real pointer on the real window and reads back what the server saved.
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
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QWidget

    from backend.month import build_month
    from desktop.native.hours.hand import Hand, MoveDate, Verdict
    from desktop.native.hours.month import MonthGrid, month_cells
    from desktop.native.weekmodel import build_week

MONDAY = "2026-09-21"
ESSAY = {
    "id": "essay-1",
    "title": "History essay",
    "kind": "flexible",
    "category": "homework",
    "assignment_id": "essay",
    "start": "19:00",
    "duration_min": 60,
    "days": [3],
    "pinned": True,
}
SCHOOL = {
    "id": "school",
    "title": "School",
    "kind": "locked",
    "category": "class",
    "start": "08:00",
    "duration_min": 390,
    "days": [0, 1, 2, 3, 4],
}


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-month-canvas-test"])


def september() -> dict:
    snapshot = build_month("2026-09", [], [])
    snapshot["deadlines"] = [
        {"id": "essay", "title": "History essay", "category": "assignments", "due": "2026-09-27"},
        {"id": "oral", "title": "French oral", "category": "assignments", "due": "2026-09-29T09:00"},
    ]
    for day in snapshot["days"]:
        day["due_ids"] = {"2026-09-27": ["essay"], "2026-09-29": ["oral"]}.get(day["date"], [])
    return snapshot


class Stage:
    """A month in a window inside the offscreen screen, and what its hand reported."""

    def __init__(self, qapp: QApplication, judge=None) -> None:
        self.window = QWidget()
        self.window.setGeometry(0, 0, 760, 720)
        self.said: list[object] = []
        self.hand = Hand(lambda block_id, from_day, span: Verdict(True, ""), self.window)
        self.hand.date_judge = judge
        self.hand.committed.connect(self.said.append)
        self.hand.refused.connect(lambda words: self.said.append(("refused", words)))
        self.grid = MonthGrid(self.window, hand=self.hand)
        self.grid.setGeometry(self.window.rect())
        self.opened: list[str] = []
        self.grid.day_activated.connect(self.opened.append)
        self.grid.set_week(build_week(MONDAY, [ESSAY, SCHOOL], {}, None))
        self.grid.set_month(september(), False)
        self.window.show()
        qapp.processEvents()
        self.canvas = self.grid.canvas

    def send(self, kind: QEvent.Type, at: QPoint, held: bool) -> None:
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        event = QMouseEvent(
            kind,
            QPointF(self.canvas.mapFromGlobal(at)),
            QPointF(at),
            Qt.MouseButton.LeftButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(self.canvas, event)

    def carry(self, start: QPoint, end: QPoint, held=None) -> None:
        self.send(QEvent.Type.MouseButtonPress, start, True)
        for step in range(1, 9):
            self.send(QEvent.Type.MouseMove, start + (end - start) * step / 8, True)
        if held is not None:
            held()
        self.send(QEvent.Type.MouseButtonRelease, end, False)


def test_a_date_lists_what_is_due_then_its_blocks_at_their_times() -> None:
    """The open week comes from what the student has now, saved or not; other weeks come from what
    the month reply says is on each date."""
    snapshot = september()
    next_monday = next(day for day in snapshot["days"] if day["date"] == "2026-09-28")
    next_monday["blocks"] = [
        {"id": "piano", "title": "Piano", "start": "18:00", "duration_min": 45, "category": "extra"},
        {"id": "run", "title": "Run", "start": "07:00", "duration_min": 30, "category": "exercise"},
    ]
    unsaved = {**ESSAY, "start": "20:15"}
    week = build_week(MONDAY, [unsaved, SCHOOL], {}, None)
    cells = {cell.iso: cell for cell in month_cells(snapshot, {MONDAY: week}, "")}
    assert [chip.words for chip in cells["2026-09-24"].chips] == ["08:00 School", "20:15 History essay"]
    assert [chip.words for chip in cells["2026-09-27"].chips] == ["Due History essay"]
    assert [chip.words for chip in cells["2026-09-28"].chips] == ["07:00 Run", "18:00 Piano"]
    assert [chip.words for chip in cells["2026-09-29"].chips] == ["Due 09:00 French oral"]
    assert [chip.carried for chip in cells["2026-09-29"].chips] == [False], "a deadline is not carried"


def test_a_week_left_unsaved_is_drawn_as_the_student_has_it() -> None:
    """A week the student changed and left without saving is drawn from those changes, as the open
    week is; a week with none still comes from the month reply."""
    snapshot = september()
    replied = {
        "2026-10-01": [{"id": "essay-1", "title": "History essay", "start": "19:00", "duration_min": 60}],
        "2026-09-24": [{"id": "essay-1", "title": "History essay", "start": "19:00", "duration_min": 60}],
        "2026-09-17": [{"id": "piano", "title": "Piano", "start": "18:00", "duration_min": 45}],
    }
    for day in snapshot["days"]:
        day["blocks"] = replied.get(day["date"], [])
    open_week = build_week(MONDAY, [ESSAY], {}, None)
    left = build_week("2026-09-28", [{**ESSAY, "start": "20:15"}], {}, None)
    cells = {cell.iso: cell for cell in month_cells(snapshot, {MONDAY: open_week, "2026-09-28": left}, "")}
    assert [chip.words for chip in cells["2026-10-01"].chips] == ["20:15 History essay"]
    assert [chip.words for chip in cells["2026-09-24"].chips] == ["19:00 History essay"]
    assert [chip.words for chip in cells["2026-09-17"].chips] == ["18:00 Piano"]


def test_the_grid_draws_the_open_week_and_the_weeks_left_unsaved(qapp: QApplication) -> None:
    snapshot = september()
    for day in snapshot["days"]:
        if day["date"] == "2026-10-01":
            day["blocks"] = [
                {"id": "essay-1", "title": "History essay", "start": "19:00", "duration_min": 60}
            ]
    grid = MonthGrid()
    grid.set_week(build_week(MONDAY, [ESSAY], {}, None))
    grid.set_month(snapshot, True)
    assert grid.canvas.chip_words("essay-1", "2026-10-01") == "19:00 History essay"
    grid.set_unsaved({"2026-09-28": build_week("2026-09-28", [{**ESSAY, "start": "20:15"}], {}, None)})
    assert grid.canvas.chip_words("essay-1", "2026-10-01") == "20:15 History essay"
    assert grid.canvas.chip_words("essay-1", "2026-09-24") == "19:00 History essay"


def test_a_chip_carried_to_another_date_is_one_date_move(qapp: QApplication) -> None:
    stage = Stage(qapp)
    stage.carry(stage.canvas.chip_point("essay-1", "2026-09-24"), stage.canvas.cell_point("2026-09-26"))
    assert stage.said == [MoveDate("essay-1", "2026-09-24", "2026-09-26")]
    assert stage.opened == []


def test_a_refused_date_shows_while_held_and_moves_nothing(qapp: QApplication) -> None:
    words = "That ends after it is due, so it stayed where it was."
    stage = Stage(qapp, lambda block_id, from_iso, to_iso: Verdict(to_iso < "2026-09-27", words))
    seen: list[tuple[str | None, bool | None]] = []

    def look() -> None:
        verdict = stage.hand.month_verdict
        seen.append((stage.hand.month_target, None if verdict is None else verdict.ok))

    stage.carry(stage.canvas.chip_point("essay-1", "2026-09-24"), stage.canvas.cell_point("2026-09-28"), look)
    assert seen == [("2026-09-28", False)]
    assert stage.said == [("refused", words)]
    stage.carry(stage.canvas.chip_point("essay-1", "2026-09-24"), stage.canvas.cell_point("2026-09-25"))
    assert stage.said[-1] == MoveDate("essay-1", "2026-09-24", "2026-09-25")


def test_a_chip_let_go_on_its_own_date_moves_nothing_and_a_clicked_one_opens_it(qapp: QApplication) -> None:
    stage = Stage(qapp)
    stage.carry(stage.canvas.chip_point("essay-1", "2026-09-24"), stage.canvas.cell_point("2026-09-24"))
    assert stage.said == []
    at = stage.canvas.chip_point("school", "2026-09-22")
    stage.send(QEvent.Type.MouseButtonPress, at, True)
    stage.send(QEvent.Type.MouseButtonRelease, at, False)
    assert stage.said == []
    assert stage.opened == ["2026-09-22"], "a chip clicked, not carried, opens its date as the date does"


def test_a_deadline_is_not_carried(qapp: QApplication) -> None:
    stage = Stage(qapp)
    box = next(
        box for chip, box in stage.canvas.chip_boxes(stage.canvas.index_of("2026-09-27"))[0] if chip.due
    )
    start = stage.canvas.mapToGlobal(box.center().toPoint())
    held: list[bool] = []
    stage.carry(start, stage.canvas.cell_point("2026-09-30"), lambda: held.append(stage.hand.busy))
    assert held == [False], "nothing is picked up: moving a deadline is editing the homework"
    assert stage.said == []


def test_a_dates_own_point_is_on_the_date_and_on_none_of_its_chips(qapp: QApplication) -> None:
    stage = Stage(qapp)
    canvas = stage.canvas
    for cell in canvas.cells:
        local = QPointF(canvas.mapFromGlobal(canvas.cell_point(cell.iso)))
        assert canvas.date_at(local) == cell.iso
        assert canvas._chip_at(local) is None, f"{cell.iso}'s point lands on a chip"


def test_the_words_held_over_a_refused_date_say_no_in_red(qapp: QApplication) -> None:
    words = "That ends after it is due, so it stayed where it was."
    stage = Stage(qapp, lambda block_id, from_iso, to_iso: Verdict(to_iso < "2026-09-27", words))
    seen: list[tuple[str, bool]] = []
    label = stage.window.findChild(QWidget, "heldChip")

    def look() -> None:
        seen.append((label.text(), bool(label.property("refused"))))

    stage.carry(stage.canvas.chip_point("essay-1", "2026-09-24"), stage.canvas.cell_point("2026-09-28"), look)
    stage.carry(stage.canvas.chip_point("essay-1", "2026-09-24"), stage.canvas.cell_point("2026-09-25"), look)
    assert seen == [(words, True), ("19:00 History essay → Fri 25", False)]


def test_a_month_with_no_window_is_freed_without_the_garbage_collector(qapp: QApplication) -> None:
    """A month drawn with no window gets a hand of its own. That hand once kept a reference back to
    the month, a cycle only the garbage collector could free, at a moment of its choosing."""
    import gc
    import weakref

    gc.collect()
    gc.disable()
    try:
        grid = MonthGrid()
        gone = weakref.ref(grid)
        del grid
        assert gone() is None
    finally:
        gc.enable()


def first_row_shown(grid: MonthGrid) -> int:
    """The row at the top of the view: the one whose top the scroll bar stands at."""
    canvas, value = grid.canvas, grid.scroll.verticalScrollBar().value()
    return next(row for row in range(canvas.rows()) if round(canvas.cell_rect(row * 7).top()) == value)


def test_month_opens_with_the_students_week_as_its_first_row(qapp: QApplication) -> None:
    """A whole month fits a laptop's screen, so it opened with the weeks already gone on top. It opens
    on the student's week now, the weeks after it filling the view and the ones before a scroll away;
    a week late in the month still shows the week after it."""
    from PySide6.QtTest import QTest

    from desktop.native.hours.month import LEAST_AHEAD

    grid = MonthGrid()
    grid.resize(900, 700)
    grid.set_month(september(), False)
    grid.show()
    qapp.processEvents()
    room = grid.scroll.viewport().height()
    canvas = grid.canvas
    assert canvas.rows() * canvas.least_row() < room, "the whole month fits, as on a laptop"
    shown = []
    for iso in ("2026-09-03", "2026-09-24", "2026-09-30"):
        grid.reveal(iso)
        QTest.qWait(50)
        row = canvas.index_of(iso) // 7
        top = first_row_shown(grid)
        below = canvas.height() - round(canvas.cell_rect(top * 7).top())
        shown.append((iso, top, below >= room, canvas.rows() - top >= LEAST_AHEAD, top == row))
    grid.close()
    assert shown == [
        ("2026-09-03", 0, True, True, True),
        ("2026-09-24", 3, True, True, True),
        # The month's last row: the week before it stays above, so two weeks show.
        ("2026-09-30", 3, True, True, False),
    ]
