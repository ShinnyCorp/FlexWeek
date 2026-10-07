"""The date picker in the look (T19 of the 0.17.0 audit, 5.2 A of 0.17.2). Qt's stock month drew
Saturday and Sunday in red, the picked day as a square, and no edge, so it bled into the sheet."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, QModelIndex, QPoint, QRect
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QLabel, QTableView, QWidget

from desktop.native.fields import LookCalendar
from desktop.native.look import pack_stylesheet, resolved_palette
from desktop.native.tokens import contrast
from desktop.native.widgets import HomeworkDialog, RoutineDialog, SpreadDialog, control_art
from desktop.tests.window_support import free, qapp  # noqa: F401

WEEK = "2026-09-21"


def dressed(pack: str) -> tuple[QWidget, dict]:
    palette = resolved_palette(pack, False, None, "default")
    made = QWidget()
    made.setStyleSheet(pack_stylesheet(pack, False, None, "default", palette, control_art(palette)))
    made.resize(1280, 800)
    made.show()
    return made, palette


def picked_near_today() -> QDate:
    """A day in this month that is not today, so the month shows both."""
    today = QDate.currentDate()
    tomorrow = today.addDays(1)
    return tomorrow if tomorrow.month() == today.month() else today.addDays(-1)


def opened(qapp: QApplication, parent: QWidget, day: QDate) -> tuple[HomeworkDialog, QWidget, LookCalendar]:  # noqa: F811
    dialog = HomeworkDialog(parent, today=day.toString("yyyy-MM-dd"), due=day.toString("yyyy-MM-dd"))
    dialog.show()
    month = dialog.due.date.calendarWidget()
    popup = month.parentWidget()
    popup.show()
    for _ in range(6):
        qapp.processEvents()
    return dialog, popup, month


def cells(month: LookCalendar) -> tuple[QTableView, dict[QDate, QRect]]:
    """Each date shown and where it is, read off the month's own grid."""
    view = month.findChild(QTableView, "qt_calendar_calendarview")
    model = view.model()
    shown: dict[QDate, QRect] = {}
    first = QDate(month.yearShown(), month.monthShown(), 1)
    for row in range(1, model.rowCount()):
        for column in range(model.columnCount()):
            index = model.index(row, column, QModelIndex())
            number = int(index.data())
            # Rows before the 1st are the month before; a small number late on is the month after.
            if row <= 2 and number > 20:
                day = first.addMonths(-1)
            elif row >= 4 and number < 15:
                day = first.addMonths(1)
            else:
                day = first
            shown[QDate(day.year(), day.month(), number)] = view.visualRect(index)
    return view, shown


def ink(picture: QImage, rect: QRect, ground: str) -> str:
    """The colour in `rect` that stands out most from `ground`: the number's."""
    colours = {
        picture.pixelColor(x, y).name()
        for x in range(rect.left(), rect.right())
        for y in range(rect.top(), rect.bottom())
    }
    return max(colours, key=lambda colour: contrast(colour, ground))


def same(first: str, second: str) -> bool:
    """One colour, give or take the last bit of each channel that drawing text can change."""
    pairs = zip(QColor(first).getRgb()[:3], QColor(second).getRgb()[:3], strict=True)
    return all(abs(one - two) <= 3 for one, two in pairs)


def accent_pixels(picture: QImage, rect: QRect, accent: str) -> int:
    """How much of a cell is the accent, give or take its antialiased edge. By hue, not by contrast: a
    grey edge of a number can have the accent's contrast without being the accent."""
    wanted = QColor(accent).getRgb()[:3]

    def close(x: int, y: int) -> bool:
        got = picture.pixelColor(x, y).getRgb()[:3]
        return sum((one - two) ** 2 for one, two in zip(got, wanted, strict=True)) < 50**2

    across, down = range(rect.left(), rect.right()), range(rect.top(), rect.bottom())
    return sum(close(x, y) for x in across for y in down)


def test_numbers_are_drawn_in_grey_shades(qapp: QApplication) -> None:  # noqa: F811
    """`ink` reads a number's colour off its darkest pixel. Drawn in coloured subpixel stripes, a 10 had
    no pixel in the text's colour, so the weekend test failed in a worker on a day whose first
    Saturday was the 10th; conftest keeps text in grey shades on every computer."""
    number = QLabel("10")
    number.setStyleSheet("background: white; color: black; font: 13pt 'Inter'")
    number.resize(60, 30)
    picture = number.grab().toImage()
    across, down = range(picture.width()), range(picture.height())
    shades = {picture.pixelColor(x, y).getRgb()[:3] for x in across for y in down}
    assert len(shades) > 2, "the number was drawn"
    assert all(red == green == blue for red, green, blue in shades), "coloured subpixel stripes"
    free(number)


@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_weekends_are_plain_the_pick_is_round_and_today_is_ringed(
    qapp: QApplication,  # noqa: F811
    pack: str,
) -> None:
    parent, palette = dressed(pack)
    day = picked_near_today()
    today = QDate.currentDate()
    dialog, _popup, month = opened(qapp, parent, day)
    view, shown = cells(month)
    picture = view.viewport().grab().toImage()
    ground, accent = palette["panel"], palette["accent"]
    plain = [date for date in shown if date.month() == month.monthShown() and date not in (day, today)]
    saturday = next(date for date in plain if date.dayOfWeek() == 6)
    sunday = next(date for date in plain if date.dayOfWeek() == 7)
    wednesday = next(date for date in plain if date.dayOfWeek() == 3)
    weekday = ink(picture, shown[wednesday], ground)
    assert same(weekday, palette["text"])
    weekend = [ink(picture, shown[saturday], ground), ink(picture, shown[sunday], ground)]
    assert all(same(colour, weekday) for colour in weekend), f"not red: {weekend} beside {weekday}"
    header = [view.model().index(0, column, QModelIndex()) for column in range(7)]
    assert [index.data() for index in header] == list("MTWTFSS")
    letters = [ink(picture, view.visualRect(index), ground) for index in header]
    assert all(same(colour, letters[0]) for colour in letters), f"S and S are coloured as M to F: {letters}"
    picked, ringed = shown[day], shown[today]
    radius = (min(picked.width(), picked.height()) - 4) / 2
    disc = 3.14 * radius * radius
    # The disc, less the number written on it.
    assert accent_pixels(picture, picked, accent) > 0.45 * disc, "the pick is filled in the accent"
    assert picture.pixelColor(picked.topLeft() + QPoint(1, 1)).name() == ground, "round, not a square"
    ring = accent_pixels(picture, ringed, accent)
    assert 3 * radius < ring < 0.4 * disc, f"today is ringed, not filled: {ring} accent pixels"
    free(dialog)
    free(parent)


@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_the_month_drops_on_a_rounded_card_with_an_edge(qapp: QApplication, pack: str) -> None:  # noqa: F811
    parent, palette = dressed(pack)
    dialog, popup, _month = opened(qapp, parent, picked_near_today())
    picture = popup.grab().toImage()
    assert picture.pixelColor(0, 0).alpha() == 0, "rounded: nothing in the corner"
    middle = picture.height() // 2
    assert picture.pixelColor(0, middle).name() != palette["panel"], "an edge"
    assert picture.pixelColor(4, middle).name() == palette["panel"], "the card's colour inside it"
    free(dialog)
    free(parent)


def test_every_date_in_a_sheet_is_picked_on_the_look_s_month(qapp: QApplication) -> None:  # noqa: F811
    parent, _palette = dressed("light-frost")
    homework = HomeworkDialog(parent, today=WEEK)
    routines = RoutineDialog(parent, {}, [], WEEK)
    essay = {"id": "e", "title": "Essay", "due": "2026-09-27", "estimate_min": 60}
    spread = SpreadDialog(parent, essay, WEEK)
    fields = (homework.due.date, routines.findChild(QWidget, "routineDestination"), spread.from_date)
    assert [type(field.calendarWidget()) for field in fields] == [LookCalendar] * 3
    assert all(field.calendarWidget().firstDayOfWeek().name == "Monday" for field in fields)
    for made in (homework, routines, spread):
        free(made)
    free(parent)
