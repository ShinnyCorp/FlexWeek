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


def test_a_month_chip_puts_its_date_on_held_from_iso_not_category(qapp: QApplication) -> None:
    """Month's press builds Held with the cell ISO as the eighth positional value, after grab.
    That slot is from_iso. Category is empty here because Month does not pass one. If category
    sits before from_iso, the ISO fills category and the drop has no origin date."""
    stage = Stage(qapp)
    seen: list[tuple[str, str]] = []

    def look() -> None:
        held = stage.hand.preview_held()
        assert held is not None
        seen.append((held.from_iso, held.category))

    stage.carry(stage.canvas.chip_point("essay-1", "2026-09-24"), stage.canvas.cell_point("2026-09-26"), look)
    assert seen == [("2026-09-24", "")]


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
    assert seen == [(words, True), ("19:00 History essay → Fri 25 Sep", False)]


def painted_colours(qapp: QApplication, draw, palette: dict | None = None) -> set[str]:
    """Every colour a painter call leaves on a small picture, in Light unless told."""
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    from desktop.native.hours.month import MonthPainter
    from desktop.native.look import resolved_palette

    palette = palette or resolved_palette("light-frost", False, None)
    image = QImage(240, 40, QImage.Format.Format_ARGB32)
    image.fill(QColor("#123456"))
    painter = QPainter(image)
    painter.setFont(QFont("Inter", 10))
    draw(MonthPainter(palette), painter)
    painter.end()
    return {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}


def test_a_deadline_is_a_quiet_chip_led_by_due_and_red_only_once_its_date_has_gone(
    qapp: QApplication,
) -> None:
    """A column of red boxes down a Sunday was the most alarming thing in the app for its most
    ordinary fact. A deadline is a neutral chip led by a bold "Due", and red is kept for past due."""
    from PySide6.QtCore import QRectF

    from desktop.native.calendar import CATEGORIES
    from desktop.native.look import resolved_palette

    palette = resolved_palette("light-frost", False, None)
    cells = {cell.iso: cell for cell in month_cells(september(), {}, "2026-09-28")}
    gone, coming = cells["2026-09-27"].chips[0], cells["2026-09-29"].chips[0]
    assert (gone.late, coming.late) == (True, False)
    assert (gone.flag, coming.flag) == ("Due", "Due 09:00")

    box = QRectF(0, 0, 240, 40)

    def chip(shown) -> set[str]:
        return painted_colours(qapp, lambda month, painter: month.chip(painter, box, shown, False, False))

    for shown in (gone, coming):
        assert CATEGORIES["assignments"]["mark"] not in chip(shown), "outlined in homework's colour"
    assert palette["error"] in chip(gone)
    assert palette["error"] not in chip(coming)


def test_a_block_on_month_is_its_category_as_the_week_fills_it(qapp: QApplication) -> None:
    """One family (decision 9 of 0.17): a chip is the category's fill for the look, pale on Light and
    sunk into the card on Dark, not the strong mark washed over the card."""
    from PySide6.QtCore import QRectF

    from desktop.native.hours.month import MonthChip
    from desktop.native.look import category_paint, resolved_palette

    box = QRectF(0, 0, 240, 40)
    for pack, dark in (("light-frost", False), ("dark-frost", True)):
        palette = resolved_palette(pack, dark, None)
        for category in ("class", "assignments"):
            chip = MonthChip(f"block:{category}", "Block", category, block_id=category, start=8 * 60)
            seen = painted_colours(
                qapp, lambda month, painter, chip=chip: month.chip(painter, box, chip, False, False), palette
            )
            assert category_paint(category, palette)[0] in seen, (pack, category)


def test_a_done_or_held_chip_keeps_its_words_at_full_strength_and_only_its_fill_is_lighter(
    qapp: QApplication,
) -> None:
    """#93: dimming the words of a done chip to 47 % made them hard to read. The fill carries "done"."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    from desktop.native.hours.month import MonthChip, MonthPainter
    from desktop.native.look import category_paint, resolved_palette

    palette = resolved_palette("light-frost", False, None)
    chip = MonthChip("block:class", "School", "class", block_id="class", start=8 * 60)
    box = QRectF(0, 0, 240, 40)
    ground = QColor("#123456")

    def draw(faded: bool, held: bool, done: bool) -> QImage:
        image = QImage(240, 40, QImage.Format.Format_ARGB32)
        image.fill(ground)
        painter = QPainter(image)
        painter.setFont(QFont("Inter", 12))
        shown = MonthChip("block:class", "School", "class", block_id="class", start=8 * 60, done=done)
        MonthPainter(palette).chip(painter, box, shown, faded, held)
        painter.end()
        return image

    def seen(image: QImage) -> set[str]:
        return {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}

    fill = QColor(category_paint(chip.category, palette)[0])
    half = 127 / 255
    # The fill at half strength over the ground, worked out from the requirement, per channel.
    rgb = fill.getRgb()[:3], ground.getRgb()[:3]
    lighter = [round(c * half + g * (1 - half)) for c, g in zip(*rgb, strict=True)]
    for faded, held, done in ((True, False, False), (False, True, False), (False, False, True)):
        image = draw(faded, held, done)
        assert palette["text"] in seen(image), "the words keep the text colour at full strength"
        corner = image.pixelColor(3, 20).getRgb()[:3]
        close = all(abs(a - b) <= 2 for a, b in zip(corner, lighter, strict=True))
        assert close, (faded, held, done, corner, lighter)
    plain = draw(False, False, False).pixelColor(3, 20).getRgb()[:3]
    assert plain == fill.getRgb()[:3], "a chip not done keeps its full fill"


def test_a_date_outside_the_month_is_told_by_its_dimmed_number_not_a_tint(qapp: QApplication) -> None:
    """Outside dates took the page's tint, the same as today's wash, so 1 to 4 September looked like
    today. They are cards like the rest, with the number in the muted colour."""
    from PySide6.QtCore import QRectF

    from desktop.native.look import resolved_palette

    palette = resolved_palette("light-frost", False, None)
    outside = next(cell for cell in month_cells(september(), {}, "2026-09-28") if not cell.in_month)
    box = QRectF(0, 0, 240, 40)
    card = painted_colours(qapp, lambda month, painter: month.cell(painter, box, outside))
    assert palette["panel"] in card and palette["window"] not in card
    numbers = painted_colours(qapp, lambda month, painter: month.day_number(painter, box, outside))
    assert palette["muted"] in numbers and palette["text"] not in numbers


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


def test_a_month_revealed_before_its_first_layout_still_opens_on_the_week(qapp: QApplication) -> None:
    """The window asks as the month is switched to, before it has a height of its own. Rows sized to
    that height put another week on top once the month was laid out."""
    from PySide6.QtTest import QTest

    grid = MonthGrid()
    grid.resize(900, 700)
    grid.set_month(september(), False)
    grid.reveal("2026-09-24")
    grid.show()
    QTest.qWait(50)
    shown = first_row_shown(grid)
    below = grid.canvas.height() - grid.scroll.verticalScrollBar().value()
    room = grid.scroll.viewport().height()
    grid.close()
    assert (shown, below >= room) == (3, True)


def test_a_weeks_row_is_as_tall_as_its_busiest_date_and_this_week_is_banded(qapp: QApplication) -> None:
    """Decision 17 of 0.17: not six even rows with empty space in the quiet weeks. A week's row grows
    with its busiest date, up to six chips, and the week with today is banded in a little of the text
    colour, not the accent."""
    from PySide6.QtGui import QColor

    from desktop.native.hours.month import MOST_CHIPS
    from desktop.native.look import mix, resolved_palette

    snapshot = build_month("2026-09", [], [])
    busy = next(day for day in snapshot["days"] if day["date"] == "2026-09-16")
    busy["blocks"] = [
        {"id": f"b{hour}", "title": f"Club {hour}", "start": f"{hour:02d}:00", "duration_min": 60}
        for hour in range(8, 17)
    ]
    grid = MonthGrid()
    palette = resolved_palette("light-frost", False, None)
    grid.set_palette(palette)
    grid.resize(900, 300)
    grid.set_month(snapshot, False)
    canvas = grid.canvas
    canvas.set_cells(month_cells(snapshot, {}, "2026-09-16"))
    grid.show()
    qapp.processEvents()
    quiet, busy_row = canvas.cell_rect(0).height(), canvas.cell_rect(16).height()
    assert busy_row > quiet, f"the busy week's row is {busy_row:.0f} px, a quiet one {quiet:.0f}"
    shown, more = canvas.chip_boxes(16)
    assert (len(shown), more) == (MOST_CHIPS, 9 - MOST_CHIPS)
    image = canvas.grab().toImage()

    def ground(index: int) -> str:
        box = canvas.cell_rect(index)
        return QColor(image.pixel(int(box.right()) - 4, int(box.bottom()) - 4)).name()

    band = mix(palette["text"], palette["panel"], 0.04)
    assert ground(16) != palette["panel"] and ground(16) == ground(20)
    assert abs(QColor(ground(16)).lightness() - QColor(band).lightness()) <= 2
    assert ground(0) == palette["panel"], "only this week is banded"
    grid.close()


def test_a_month_on_its_way_keeps_the_last_one_drawn_under_loading_month(qapp: QApplication) -> None:
    """0.18.5 #96: Week to Month flashed an empty grid while the new month was fetched. The grid the
    student last had stays, with "Loading month…", until the new one arrives."""
    grid = MonthGrid()
    grid.set_week(build_week(MONDAY, [ESSAY], {}, None))
    grid.set_month(september(), False, "2026-09-16", "ana")
    kept = [cell.iso for cell in grid.canvas.cells]
    assert kept and "2026-09-16" in kept
    grid.set_month(None, False, "2026-09-16", "ana")
    assert [cell.iso for cell in grid.canvas.cells] == kept, "the old grid is still drawn"
    assert grid.warning.text() == "Loading month…" and not grid.warning.isHidden()
    # A change to the open week while it waits redraws the kept grid, not an empty one.
    grid.set_unsaved({})
    assert [cell.iso for cell in grid.canvas.cells] == kept
    november = build_month("2026-11", [], [])
    grid.set_month(november, False, "2026-09-16", "ana")
    assert grid.canvas.cells and grid.canvas.cells[10].iso in {day["date"] for day in november["days"]}
    assert [cell.iso for cell in grid.canvas.cells] != kept, "the new month replaces it"
    assert grid.warning.text() == "" and grid.warning.isHidden()


def test_a_month_never_shows_another_students_grid_while_it_loads(qapp: QApplication) -> None:
    """The kept grid is the same student's: after another one signs in, loading shows nothing."""
    grid = MonthGrid()
    grid.set_week(build_week(MONDAY, [ESSAY], {}, None))
    grid.set_month(september(), False, "2026-09-16", "ana")
    assert grid.canvas.cells
    grid.set_month(None, False, "2026-09-16", "ben")
    assert grid.canvas.cells == []
    assert grid.warning.text() == "Loading month…"
    grid.set_month(september(), False, "2026-09-16", "ana")
    grid.set_month(None, False, "2026-09-16", None)
    assert grid.canvas.cells == [], "with nobody named there is nothing to be sure of"


def busy_september() -> dict:
    """September with a quiet week, a date with one chip and a date with five."""
    snapshot = build_month("2026-09", [], [])
    for day in snapshot["days"]:
        if day["date"] == "2026-09-16":
            day["blocks"] = [
                {"id": f"b{hour}", "title": f"Club {hour}", "start": f"{hour:02d}:00", "duration_min": 60}
                for hour in range(8, 13)
            ]
        if day["date"] == "2026-09-09":
            day["blocks"] = [{"id": "solo", "title": "Piano", "start": "17:00", "duration_min": 60}]
    return snapshot


def tight_grid(qapp: QApplication, height: int, tight: bool) -> MonthGrid:
    grid = MonthGrid()
    grid.resize(1024, height)
    grid.set_tight(tight)
    snapshot = busy_september()
    grid.set_month(snapshot, False, "2026-09-16")
    grid.show()
    qapp.processEvents()
    return grid


def test_with_panels_open_every_week_fits_the_view_and_a_date_still_shows_a_chip(qapp: QApplication) -> None:
    """#28: at 1024 x 640 the plan and Unfinished panels left Month about 300 px, so its last row was half
    cut and a scroll bar came. Tight, the five rows share the view; each keeps its number and a chip."""
    grid = tight_grid(qapp, 360, True)
    canvas, view = grid.canvas, grid.scroll.viewport().height()
    assert canvas.rows() == 5
    assert grid.scroll.verticalScrollBar().maximum() == 0, "no scroll bar"
    last = canvas.cell_rect(7 * 4)
    assert last.bottom() <= view, f"the last row ends at {last.bottom():.0f} in a view of {view}"
    for row in range(5):
        assert canvas.cell_rect(row * 7).height() >= canvas.tight_row(), row
    shown, more = canvas.chip_boxes(canvas.index_of("2026-09-09"))
    assert [chip.words for chip, _box in shown] == ["17:00 Piano"] and more == 0
    shown, more = canvas.chip_boxes(canvas.index_of("2026-09-16"))
    assert len(shown) == 1 and more == 4, "a busy date shows one chip and counts the rest"
    cell = canvas.cell_rect(canvas.index_of("2026-09-16"))
    count = canvas.more_box(canvas.index_of("2026-09-16"), len(shown))
    assert cell.contains(shown[0][1]) and cell.contains(count)
    assert not count.intersects(shown[0][1]), "the count does not cover the chip"
    grid.close()


def test_a_row_with_one_line_keeps_its_chip_and_writes_the_count_by_the_number(qapp: QApplication) -> None:
    grid = tight_grid(qapp, 360, True)
    canvas = grid.canvas
    overhead = grid.height() - grid.scroll.viewport().height()
    grid.resize(1024, 5 * canvas.tight_row() + overhead + 2)
    qapp.processEvents()
    index = canvas.index_of("2026-09-16")
    shown, more = canvas.chip_boxes(index)
    assert len(shown) == 1 and more == 4
    count = canvas.more_box(index, 1)
    assert count.bottom() <= shown[0][1].top() and canvas.cell_rect(index).contains(count)
    grid.close()


def test_without_panels_the_month_still_scrolls_rather_than_squeezing(qapp: QApplication) -> None:
    """Decision 17 of 0.17 stands when nothing is open: the same view that fits when tight scrolls."""
    grid = tight_grid(qapp, 360, False)
    assert grid.scroll.verticalScrollBar().maximum() > 0
    assert grid.canvas.cell_rect(0).height() >= grid.canvas.least_row()
    grid.close()


def test_a_view_too_short_for_the_tight_rows_scrolls_as_before(qapp: QApplication) -> None:
    grid = tight_grid(qapp, 180, True)
    assert grid.scroll.verticalScrollBar().maximum() > 0
    assert grid.canvas.cell_rect(0).height() >= grid.canvas.tight_row()
    grid.close()
