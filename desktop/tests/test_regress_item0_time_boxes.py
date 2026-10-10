"""Regression for fix-specs.md item 0 (time boxes; was Sammy's findings 4 and 7).

`ClockField` is shared by every time box, so each guard runs on every box built from it (found by
grepping desktop/native for `ClockField(` / `QuarterTime(`):

  Setup school start/end and activity start/end (setup.py TimeRange -> QuarterTime), School hours
  start/end, the block editor start/end, Add homework's due time, Do it at, Choose a time, Study hours
  start/end (AvailabilityDialog picker) and the alarm time (SettingsPage).

All input goes through the window's QWindow (QTest on `window.windowHandle()`), the same path the
window system uses, so a key never reaches a box before the window's own focus/activation events.
Sending QTest events straight at a widget in a window that has not yet been activated loses the
first key ("15:15" -> "05:xx"); that came from the test tool, not the app, and is not tested here.
Tests never assert the withdrawn cases (Ctrl+A saving 01:00, Tab not saving, Tab leaving the form).

Required (item 0): 1 first click selects the whole time; 2 Ctrl+A selects the whole text; 3 with it
selected, Backspace and Delete clear it; 4 a typed time saves on Tab, Enter and Next/Save; 5 an
unreadable time stays in the box with an error that is the box's accessible description, never a
silent revert or 23:59. All of it passes since 0.18.5.
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QTime
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop.native.fields import ClockField
from desktop.native.settings import SettingsPage
from desktop.native.setup import SetupPage
from desktop.native.weekmodel import set_clock_24h
from desktop.native.widgets import (
    AvailabilityDialog,
    BlockDialog,
    ChooseTimeDialog,
    HomeworkDialog,
    SchoolHoursDialog,
)
from desktop.tests.test_setup_wizard import WEEK, state
from desktop.tests.window_support import free, qapp  # noqa: F401

CLICKS = ("click-start", "click-middle", "click-end")
ENTRIES = (*CLICKS, "ctrl-a", "tab-in")
LEAVES = ("tab", "enter", "next")
CLOCKS = {"24h": True, "12h": False}
TYPED = {"24h": "15:15", "12h": "3:15 PM"}
CTRL = Qt.KeyboardModifier.ControlModifier
NONE = Qt.KeyboardModifier.NoModifier


# Input through the window system's path -------------------------------------------------------


def press(field: ClockField, key, mods=NONE) -> None:
    QTest.keyClick(field.window().windowHandle(), key, mods)
    QApplication.processEvents()


def type_text(field: ClockField, text: str) -> None:
    for char in text:
        press(field, char)


def click_at(field: ClockField, fraction: float) -> None:
    line = field.lineEdit()
    keep = line.cursorPosition()
    line.setCursorPosition(round(len(line.text()) * fraction))
    at = line.cursorRect().center()
    line.setCursorPosition(keep)
    window = field.window()
    QTest.mouseClick(window.windowHandle(), Qt.MouseButton.LeftButton, NONE, line.mapTo(window, at))
    QApplication.processEvents()


def enter(field: ClockField, how: str) -> None:
    """Get the keyboard into the box the way a student does."""
    if how == "tab-in":
        # A real Tab from the widget before the box in the focus chain.
        before = field.previousInFocusChain()
        while before is not None and not (
            before.isVisible() and before.isEnabled() and before.focusPolicy() & Qt.FocusPolicy.TabFocus
            and before is not field.lineEdit()
        ):
            before = before.previousInFocusChain()
        assert before is not None
        before.setFocus(Qt.FocusReason.OtherFocusReason)
        QApplication.processEvents()
        press(field, Qt.Key.Key_Tab)
    elif how == "ctrl-a":
        click_at(field, 0.5)
        press(field, Qt.Key.Key_A, CTRL)
    else:
        click_at(field, {"click-start": 0.0, "click-middle": 0.5, "click-end": 1.0}[how])
    assert field.hasFocus() or field.lineEdit().hasFocus(), f"{how} did not give the box the keyboard"


# Every box -------------------------------------------------------------------------------------


@dataclass
class Box:
    top: QWidget
    field: ClockField
    read: Callable[[], str]  # the time the place would save, "HH:MM"
    forward: QPushButton  # Next / Save / Add: what the student presses to go on
    owned: list


def _up(qapp: QApplication, widget: QWidget) -> QWidget:
    widget.show()
    assert QTest.qWaitForWindowExposed(widget)
    widget.activateWindow()
    qapp.processEvents()
    return widget


def _end(start: str, minutes: int) -> str:
    h, m = map(int, start.split(":"))
    total = h * 60 + m + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


def _ancestors(widget: QWidget) -> list[QWidget]:
    out = []
    while (widget := widget.parentWidget()) is not None:
        out.append(widget)
    return out


def _default_button(top: QWidget) -> QPushButton:
    return next(b for b in top.findChildren(QPushButton) if b.isDefault() and b.isVisible())


def _accepted(dialog: QDialog) -> None:
    if dialog.result() != QDialog.DialogCode.Accepted:
        dialog.accept()


def _setup(qapp, which: str) -> Box:
    setup = SetupPage()
    setup.motion = "off"
    setup.resize(1100, 720)
    setup.open(state())
    setup._show(WEEK)
    _up(qapp, setup)
    if which.startswith("school"):
        times = setup.school_times
        title = "School"
    else:
        row = setup.activities[0]
        row.name.setText("Soccer")
        row.days.set_days([1])
        times = row.times
        title = "Soccer"
    if which.endswith("start"):
        times.end.setTime(QTime(18, 0))
    else:
        times.start.setTime(QTime(8, 0))

    def read() -> str:
        block = next(b for b in setup.week_blocks() if b["title"] == title)
        return block["start"] if which.endswith("start") else _end(block["start"], block["duration_min"])

    field = times.start if which.endswith("start") else times.end
    return Box(setup, field, read, setup.next, [setup])


def setup_school_start(qapp, host):
    return _setup(qapp, "school-start")


def setup_school_end(qapp, host):
    return _setup(qapp, "school-end")


def setup_activity_start(qapp, host):
    return _setup(qapp, "activity-start")


def setup_activity_end(qapp, host):
    return _setup(qapp, "activity-end")


def _school_hours(qapp, host, end: bool) -> Box:
    dialog = _up(qapp, SchoolHoursDialog(host))
    (dialog.times.start if end else dialog.times.end).setTime(QTime(8, 0) if end else QTime(18, 0))

    def read() -> str:
        _accepted(dialog)
        school = dialog.block()
        return _end(school["start"], school["duration_min"]) if end else school["start"]

    field = dialog.times.end if end else dialog.times.start
    return Box(dialog, field, read, _default_button(dialog), [dialog])


def school_hours_start(qapp, host):
    return _school_hours(qapp, host, False)


def school_hours_end(qapp, host):
    return _school_hours(qapp, host, True)


def _block_editor(qapp, host, end: bool) -> Box:
    dialog = _up(qapp, BlockDialog(host, day=3, start="16:00", duration_min=60))
    dialog.title.setText("Club")
    if end:
        dialog.start.setTime(QTime(14, 0))

    def read() -> str:
        _accepted(dialog)
        block = dialog.block()
        return _end(block["start"], block["duration_min"]) if end else block["start"]

    return Box(dialog, dialog.end if end else dialog.start, read, _default_button(dialog), [dialog])


def block_editor_start(qapp, host):
    return _block_editor(qapp, host, False)


def block_editor_end(qapp, host):
    return _block_editor(qapp, host, True)


def homework_due_time(qapp, host):
    dialog = HomeworkDialog(host, today="2026-10-05", category="assignments", due="2026-10-07",
                            now=datetime(2026, 10, 5, 7, 0))
    dialog.title.setText("Essay")
    dialog.due.timed.setChecked(True)
    dialog.due.time.setTime(QTime(9, 0))
    _up(qapp, dialog)

    def read() -> str:
        _accepted(dialog)
        return dialog.assignment()["due"][11:16]

    return Box(dialog, dialog.due.time, read, _default_button(dialog), [dialog])


def do_it_at_time(qapp, host):
    dialog = HomeworkDialog(host, today="2026-10-05", category="assignments", due="2026-10-11",
                            now=datetime(2026, 10, 5, 7, 0))
    dialog.title.setText("Essay")
    dialog.when.setCurrentIndex(1)  # Do it at
    _up(qapp, dialog)

    def read() -> str:
        _accepted(dialog)
        return dialog.assignment()["fixed_at"]["start"]

    return Box(dialog, dialog.when_time, read, _default_button(dialog), [dialog])


def choose_a_time_start(qapp, host):
    waiting = {"id": "h1", "title": "Essay", "duration_min": 60, "days": list(range(7))}
    waiting["assignment_id"] = "a1"
    dialog = _up(qapp, ChooseTimeDialog(host, waiting, "2026-10-05", list(range(7)), [], None))
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    return Box(dialog, dialog.start, lambda: f"{dialog.choice()[1] // 60:02d}:{dialog.choice()[1] % 60:02d}",
               ok, [dialog])


def _study_hours(qapp, host, end: bool) -> Box:
    dialog = AvailabilityDialog(host, {})
    _up(qapp, dialog)
    dialog._open_picker(kind="study", day=4)
    field = dialog.picker_end if end else dialog.picker_start
    for _ in range(200):  # the picker slides open
        qapp.processEvents()
        if field.height() >= field.minimumSizeHint().height():
            break
        QTest.qWait(10)
    (dialog.picker_start if end else dialog.picker_end).setTime(QTime(14, 0) if end else QTime(18, 0))

    def read() -> str:
        if not dialog.work_windows():
            dialog.picker_add.click()
        window = dialog.work_windows()[-1]
        return window["end"] if end else window["start"]

    return Box(dialog, dialog.picker_end if end else dialog.picker_start, read, dialog.picker_add, [dialog])


def study_hours_start(qapp, host):
    return _study_hours(qapp, host, False)


def study_hours_end(qapp, host):
    return _study_hours(qapp, host, True)


def alarm_time(qapp, host):
    page = SettingsPage(host, {"reminders_enabled": True, "alarms": []}, {}, {})
    QVBoxLayout(host).addWidget(page)
    host.resize(1000, 900)
    _up(qapp, host)
    for row in range(page.nav.count()):
        page.nav.setCurrentRow(row)
        qapp.processEvents()
        if page.alarm_time.isVisible():
            break
    page.alarm_name.setText("Wake up")
    add = page.findChild(QPushButton, "addAlarm")
    page._scroll_to = None
    page.alarm_time.setTime(QTime(7, 0))

    def read() -> str:
        if not page.updates()["alarms"]:
            add.click()
        return page.updates()["alarms"][-1]["time"]

    return Box(host, page.alarm_time, read, add, [])


BOXES: dict[str, Callable] = {
    "setup-school-start": setup_school_start,
    "setup-school-end": setup_school_end,
    "setup-activity-start": setup_activity_start,
    "setup-activity-end": setup_activity_end,
    "school-hours-start": school_hours_start,
    "school-hours-end": school_hours_end,
    "block-editor-start": block_editor_start,
    "block-editor-end": block_editor_end,
    "homework-due-time": homework_due_time,
    "do-it-at": do_it_at_time,
    "choose-a-time": choose_a_time_start,
    "study-hours-start": study_hours_start,
    "study-hours-end": study_hours_end,
    "alarm-time": alarm_time,
}


@pytest.fixture()
def opened(qapp):
    made: list = []
    host = QWidget()

    def open_box(name: str) -> Box:
        box = BOXES[name](qapp, host)
        made.extend(box.owned)
        # The student scrolls the box into view before clicking it.
        for scroll in (w for w in _ancestors(box.field) if isinstance(w, QScrollArea)):
            scroll.ensureWidgetVisible(box.field)
        qapp.processEvents()
        return box

    yield open_box
    # Let deferred work run first (Dialog.refit's singleShot calls _refit_now on the dialog): freeing
    # the dialog in the same turn made it run on a deleted HomeworkDialog (widgets.py:2501). That bug is
    # item 0b's (pinned in test_regress_item0b_plan_bar.py); waiting keeps it out of item 0's results.
    QTest.qWait(20)
    for widget in made:
        widget.hide()
        free(widget)
    host.hide()
    free(host)


@pytest.fixture(params=list(CLOCKS))
def clock(request):
    set_clock_24h(CLOCKS[request.param])
    yield request.param
    set_clock_24h(True)


def leave(box: Box, how: str) -> None:
    if how == "tab":
        press(box.field, Qt.Key.Key_Tab)
    elif how == "enter":
        press(box.field, Qt.Key.Key_Return)
    else:  # Next / Save / Add, with the mouse, keyboard still in the box
        window = box.forward.window()
        at = box.forward.mapTo(window, box.forward.rect().center())
        QTest.mouseClick(window.windowHandle(), Qt.MouseButton.LeftButton, NONE, at)
        QApplication.processEvents()


def retype_cases() -> list:
    return [
        pytest.param(name, entry, way, id=f"{name}-{entry}-{way}")
        for name in BOXES
        for entry in ENTRIES
        for way in LEAVES
    ]


# Item 0.1, 0.2, 0.4: retyping 15:15 saves exactly 15:15, everywhere --------------------------


@pytest.mark.parametrize(("name", "entry", "way"), retype_cases())
def test_retyping_15_15_saves_exactly_15_15(opened, clock, name, entry, way) -> None:
    box = opened(name)
    assert box.field.time() != QTime(15, 15)
    enter(box.field, entry)
    type_text(box.field, TYPED[clock])
    leave(box, way)
    assert box.read() == "15:15", f"box shows {box.field.lineEdit().text()!r}"


@pytest.mark.parametrize("name", list(BOXES))
@pytest.mark.parametrize("entry", ENTRIES)
def test_any_way_in_selects_the_whole_time(opened, name, entry) -> None:
    box = opened(name)
    enter(box.field, entry)
    line = box.field.lineEdit()
    assert line.selectedText() == line.text() != ""


ENTER_PROBE = """
import sys
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QTime
from PySide6.QtTest import QTest
app = QApplication([])
from desktop.native.fields import ClockField
top = QWidget(); column = QVBoxLayout(top); before = QLineEdit(); column.addWidget(before)
field = ClockField(QTime(16, 0)); column.addWidget(field); top.show(); QTest.qWaitForWindowExposed(top)
top.activateWindow(); app.processEvents(); before.setFocus(); app.processEvents()
window = top.windowHandle()
typed = sys.argv[1]
for key in [Qt.Key.Key_Tab, *typed, Qt.Key.Key_Return]:
    QTest.keyClick(window, key); app.processEvents()
print(field.time().toString("HH:mm"))
"""


@pytest.mark.parametrize("typed", ["15:15", "17:30"])
@pytest.mark.parametrize("zone", ["UTC", "America/Los_Angeles", "Asia/Kolkata"])
def test_enter_keeps_a_typed_time_in_every_time_zone(zone, typed) -> None:
    """Item 0 step 4, the Enter UTC-offset bug: in a fresh app per zone (Qt reads the zone at start), so it
    fails on any machine. Asserts the exact typed time is kept, not any particular wrong value (Coder saw
    15:15 become 23:00, this box 23:15)."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, TZ=zone, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(root))
    done = subprocess.run([sys.executable, "-c", ENTER_PROBE, typed], cwd=root, env=env, capture_output=True,
                          text=True, timeout=60, check=True)
    assert done.stdout.strip().splitlines()[-1] == typed


# Item 0 step 3: Backspace and Delete clear a selected time (both work today; a passing guard) ---


@pytest.mark.parametrize("name", list(BOXES))
@pytest.mark.parametrize("entry", ["ctrl-a", "tab-in"])
@pytest.mark.parametrize(
    "key",
    [
        pytest.param(Qt.Key.Key_Backspace, id="backspace"),
        pytest.param(Qt.Key.Key_Delete, id="delete"),
    ],
)
def test_backspace_and_delete_clear_the_selected_time(opened, name, entry, key) -> None:
    box = opened(name)
    enter(box.field, entry)
    press(box.field, key)
    assert box.field.lineEdit().text() == ""
    type_text(box.field, "17:30")
    press(box.field, Qt.Key.Key_Tab)
    assert box.read() == "17:30"


# Item 0's guard on bare boxes: start/end, with and without limits, three spellings ------------


BARE = {
    "start": lambda: ClockField(QTime(19, 0)),
    "end": lambda: ClockField(QTime(19, 0), end=True),
    "start-limited": lambda: _limited(ClockField(QTime(19, 0))),
    "end-limited": lambda: _limited(ClockField(QTime(19, 0), end=True)),
}


def _limited(field: ClockField) -> ClockField:
    field.setMinimumTime(QTime(6, 0))
    field.setMaximumTime(QTime(23, 0))
    return field


@pytest.mark.parametrize("typed", ["17:30", "1730", "5:30p"])
@pytest.mark.parametrize("entry", ENTRIES)
@pytest.mark.parametrize("bare", list(BARE))
def test_a_bare_box_takes_half_past_five_however_typed(qapp, bare, entry, typed) -> None:
    top = QWidget()
    column = QVBoxLayout(top)
    column.addWidget(QLineEdit())
    field = BARE[bare]()
    column.addWidget(field)
    column.addWidget(QLineEdit())
    _up(qapp, top)
    try:
        enter(field, entry)
        type_text(field, typed)
        press(field, Qt.Key.Key_Tab)
        assert field.time().toString("HH:mm") == "17:30", f"box shows {field.lineEdit().text()!r}"
    finally:
        top.hide()
        free(top)


# Item 0.5: an unreadable time stays, with an error that is the accessible description --------


@pytest.mark.parametrize("text", ["abc", "25:00", "8::00"])
@pytest.mark.parametrize("name", list(BOXES))
def test_an_unreadable_time_stays_with_an_error_never_23_59(opened, name, text) -> None:
    box = opened(name)
    enter(box.field, "tab-in")
    type_text(box.field, text)
    press(box.field, Qt.Key.Key_Tab)
    assert box.field.lineEdit().text() == text, "the unreadable text was quietly replaced"
    assert box.field.time() != QTime(23, 59)
    said = box.field.accessibleDescription()
    shown = [label.text() for label in box.field.window().findChildren(QLabel) if label.isVisible()]
    assert said and said in shown, f"accessibleDescription {said!r}; visible labels {shown}"


# The line under a box that says no time -----------------------------------------------------


@pytest.mark.parametrize(
    ("clock_24h", "words"), [(True, "Type a time like 17:30."), (False, "Type a time like 5:30 PM.")]
)
def test_the_unreadable_time_line_follows_the_clock(opened, monkeypatch, clock_24h, words) -> None:
    set_clock_24h(clock_24h)
    try:
        box = opened("block-editor-start")
        said: list[str] = []
        monkeypatch.setattr("desktop.native.fields.announce", lambda widget, text, **_: said.append(text))
        enter(box.field, "tab-in")
        type_text(box.field, "abc")
        press(box.field, Qt.Key.Key_Tab)
        assert box.field.accessibleDescription() == words
        assert box.field.problem() == words
        assert box.field.property("invalid") is True
        assert said == [words], "announced once, when it appeared"
        # Back in, fixed: the line, the outline and the description go.
        enter(box.field, "tab-in")
        type_text(box.field, "17:30")
        assert box.field.time() == QTime(17, 30)
        press(box.field, Qt.Key.Key_Tab)
        assert box.field.accessibleDescription() == ""
        assert box.field.property("invalid") is False
        shown = [label.text() for label in box.field.window().findChildren(QLabel) if label.isVisible()]
        assert words not in shown
    finally:
        set_clock_24h(True)


def test_an_empty_box_is_unreadable_not_put_back(opened) -> None:
    box = opened("school-hours-start")
    enter(box.field, "tab-in")
    press(box.field, Qt.Key.Key_Backspace)
    press(box.field, Qt.Key.Key_Tab)
    assert box.field.lineEdit().text() == ""
    assert box.field.problem()


def test_a_time_outside_the_limits_stays_with_a_line_naming_them(qapp) -> None:
    top = QWidget()
    column = QVBoxLayout(top)
    column.addWidget(QLineEdit())
    field = _limited(ClockField(QTime(19, 0)))
    column.addWidget(field)
    _up(qapp, top)
    try:
        enter(field, "tab-in")
        type_text(field, "23:30")
        press(field, Qt.Key.Key_Tab)
        assert field.lineEdit().text() == "23:30"
        assert field.time() == QTime(19, 0)
        assert field.problem() == "Type a time from 06:00 to 23:00."
    finally:
        top.hide()
        free(top)


# Save, Enter and Add do not save the old time while a box says its text is no time ---------------

DIALOGS = ("school-hours-start", "school-hours-end", "block-editor-start", "block-editor-end",
           "homework-due-time", "do-it-at", "choose-a-time")


def _saved_anything(name: str, box: Box) -> bool:
    if name in DIALOGS:
        return box.top.result() == QDialog.DialogCode.Accepted or not box.top.isVisible()
    if name.startswith("study-hours"):
        return bool(box.top.work_windows())
    return bool(box.top.findChild(SettingsPage).updates()["alarms"])


@pytest.mark.parametrize("way", ["next", "enter"])
@pytest.mark.parametrize("name", [*DIALOGS, "study-hours-start", "study-hours-end", "alarm-time"])
def test_save_with_an_unreadable_time_saves_nothing_and_goes_back_to_the_box(opened, name, way) -> None:
    if way == "enter" and name not in DIALOGS:
        pytest.skip("Enter in a picker or Settings box presses no Add button")
    box = opened(name)
    enter(box.field, "tab-in")
    type_text(box.field, "25:00")
    leave(box, way)
    assert not _saved_anything(name, box), "the box's last good time was saved under a box saying 25:00"
    assert box.field.hasFocus() or box.field.lineEdit().hasFocus(), "the keyboard did not go back to the box"
    assert box.field.problem()
