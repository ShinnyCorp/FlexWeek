"""A clock time box is typed into like any text box: typing replaces what is selected, Backspace clears,
and every way of writing a time means the same time on either clock (finding 1 of the 0.18.1 time lane)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt, QTime
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from desktop.native.fields import ClockField
from desktop.native.weekmodel import set_clock_24h
from desktop.tests.window_support import free, host, qapp  # noqa: F401

CTRL, SHIFT = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier
# What a student can write for a quarter past three in the afternoon.
WAYS = ["1515", "15:15", "3:15 pm", "3:15pm", "315p", "3:15 PM"]
CLOCKS = [True, False]


def shown(field: ClockField, qapp: QApplication, host: QWidget) -> ClockField:  # noqa: F811
    """The box on screen with the keyboard, as it is when a student starts typing."""
    layout = host.layout()
    if layout is None:
        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(host)
    layout.addWidget(field)
    host.show()
    assert QTest.qWaitForWindowExposed(host)
    host.activateWindow()
    field.setFocus()
    qapp.processEvents()
    return field


def line_of(field: ClockField) -> QLineEdit:
    line = field.lineEdit()
    assert line is not None
    return line


def select_with_ctrl_a(field: ClockField) -> None:
    QTest.keyClick(field, Qt.Key.Key_A, CTRL)


def select_with_shift_end(field: ClockField) -> None:
    QTest.keyClick(field, Qt.Key.Key_Home)
    QTest.keyClick(field, Qt.Key.Key_End, SHIFT)


def select_with_the_mouse(field: ClockField) -> None:
    line = line_of(field)
    middle = line.height() // 2
    QTest.mousePress(line, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(2, middle))
    QTest.mouseMove(line, QPoint(line.width() - 2, middle))
    QTest.mouseRelease(
        line, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(line.width() - 2, middle)
    )


def select_with_a_double_click(field: ClockField) -> None:
    line = line_of(field)
    where = QPoint(6, line.height() // 2)
    none, left = Qt.KeyboardModifier.NoModifier, Qt.MouseButton.LeftButton
    # QTest sends a double click as one event, with no press before it and no release after it.
    QTest.mouseClick(line, left, none, where)
    QTest.mouseDClick(line, left, none, where)
    QTest.mouseRelease(line, left, none, where)


def clear_with_backspace(field: ClockField) -> None:
    QTest.keyClick(field, Qt.Key.Key_End)
    for _ in range(len(line_of(field).text()) + 2):
        QTest.keyClick(field, Qt.Key.Key_Backspace)


def clear_a_selection_with_backspace(field: ClockField) -> None:
    select_with_ctrl_a(field)
    QTest.keyClick(field, Qt.Key.Key_Backspace)


SELECTIONS: dict[str, Callable[[ClockField], None]] = {
    "ctrl-a": select_with_ctrl_a,
    "shift-end": select_with_shift_end,
    "mouse-drag": select_with_the_mouse,
    "double-click": select_with_a_double_click,
    "backspace": clear_with_backspace,
    "select-then-backspace": clear_a_selection_with_backspace,
}


def start_of(twenty_four: bool) -> QTime:
    """A time whose hour, minute and half of the day all differ from 15:15."""
    return QTime(14, 30) if twenty_four else QTime(23, 5)


@pytest.mark.parametrize("twenty_four", CLOCKS)
@pytest.mark.parametrize("how", SELECTIONS)
@pytest.mark.parametrize("way", WAYS)
def test_typing_a_time_over_a_selected_one_replaces_it(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
    twenty_four: bool,
    how: str,
    way: str,
) -> None:
    set_clock_24h(twenty_four)
    field = shown(ClockField(start_of(twenty_four)), qapp, host)
    SELECTIONS[how](field)
    QTest.keyClicks(field, way)
    assert field.time() == QTime(15, 15), f"{way!r} after {how} read as {field.time().toString('HH:mm')}"
    field.clearFocus()
    qapp.processEvents()
    assert field.time() == QTime(15, 15)
    assert line_of(field).text() == ("15:15" if twenty_four else "3:15 PM")
    free(field)


@pytest.mark.parametrize("how", SELECTIONS)
def test_twelve_thirty_am_typed_over_eleven_pm_is_half_past_midnight(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
    how: str,
) -> None:
    set_clock_24h(False)
    field = shown(ClockField(QTime(23, 0)), qapp, host)
    SELECTIONS[how](field)
    QTest.keyClicks(field, "12:30 AM")
    field.clearFocus()
    assert field.time() == QTime(0, 30)
    assert line_of(field).text() == "12:30 AM"
    free(field)


@pytest.mark.parametrize("twenty_four", CLOCKS)
@pytest.mark.parametrize("junk", ["99:99", "abc", "25:00", "12:75", "1:2:3", "15:15x", "", "24:00"])
def test_junk_is_refused_and_the_box_shows_the_last_good_time(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
    twenty_four: bool,
    junk: str,
) -> None:
    set_clock_24h(twenty_four)
    field = shown(ClockField(start_of(twenty_four)), qapp, host)
    good = field.time()
    select_with_ctrl_a(field)
    QTest.keyClicks(field, junk)
    field.clearFocus()
    qapp.processEvents()
    assert field.time() == good
    assert line_of(field).text() == good.toString("HH:mm" if twenty_four else "h:mm AP")
    free(field)


@pytest.mark.parametrize("twenty_four", CLOCKS)
def test_a_good_time_typed_past_into_junk_is_refused_whole(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
    twenty_four: bool,
) -> None:
    """15:155 is not a time, so the box goes back to what it held before, not to its 15:15."""
    set_clock_24h(twenty_four)
    field = shown(ClockField(start_of(twenty_four)), qapp, host)
    before = field.time()
    select_with_ctrl_a(field)
    QTest.keyClicks(field, "15:155")
    field.clearFocus()
    assert field.time() == before
    free(field)


@pytest.mark.parametrize("twenty_four", CLOCKS)
def test_the_arrow_keys_step_a_quarter_hour(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
    twenty_four: bool,
) -> None:
    set_clock_24h(twenty_four)
    field = shown(ClockField(QTime(8, 7)), qapp, host)
    QTest.keyClick(field, Qt.Key.Key_Up)
    assert field.time() == QTime(8, 15), "up from 08:07 is the quarter hour above"
    QTest.keyClick(field, Qt.Key.Key_Up)
    assert field.time() == QTime(8, 30)
    QTest.keyClick(field, Qt.Key.Key_Down)
    QTest.keyClick(field, Qt.Key.Key_Down)
    assert field.time() == QTime(8, 0)
    field.setTime(QTime(8, 7))
    QTest.keyClick(field, Qt.Key.Key_Down)
    assert field.time() == QTime(8, 0), "down from 08:07 is the quarter hour below"
    free(field)


@pytest.mark.parametrize("twenty_four", CLOCKS)
def test_the_wheel_steps_a_quarter_hour(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
    twenty_four: bool,
) -> None:
    set_clock_24h(twenty_four)
    field = shown(ClockField(QTime(8, 0)), qapp, host)
    for delta, expected in ((120, QTime(8, 15)), (120, QTime(8, 30)), (-120, QTime(8, 15))):
        centre = QPointF(field.width() / 2, field.height() / 2)
        event = QWheelEvent(
            centre,
            field.mapToGlobal(centre),
            QPoint(),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(field, event)
        assert field.time() == expected
    free(field)
