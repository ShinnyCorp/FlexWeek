"""Regression for fix-specs.md items 0f-0k (Accessibility Tester items 2-7), each with the spec's guard.

0f field names (buddy labels), 0g account errors on the field and announced, 0h Tab leaves Notes,
0i Setup's Tab order follows the screen, 0j focus after removing an activity, 0k a readable week list.
Keys go through the window system's path (QTest on the window's QWindow). Known failures are
xfail(strict=True).
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from desktop.native.widgets import BlockDialog, HomeworkDialog, Segmented
from desktop.tests.test_regress_item0_time_boxes import _setup, _up
from desktop.tests.window_support import free, qapp, server, settled, signed_out, window  # noqa: F401


def press(widget: QWidget, key, mods=Qt.KeyboardModifier.NoModifier) -> None:
    QTest.keyClick(widget.window().windowHandle(), key, mods)
    QApplication.processEvents()


def a11y_name(widget: QWidget) -> str:
    face = QAccessible.queryAccessibleInterface(widget)
    return face.text(QAccessible.Text.Name) if face is not None else ""


@pytest.fixture()
def made(qapp):
    owned: list[QWidget] = []
    yield owned
    for widget in owned:
        widget.hide()
        free(widget)


# 0f ---------------------------------------------------------------------------------------------

def fields_of(root: QWidget) -> list[QWidget]:
    out: list[QWidget] = []
    for widget in root.findChildren(QWidget):
        if not widget.isVisible():
            continue
        if isinstance(widget, QLineEdit) and isinstance(widget.parentWidget(), (QAbstractSpinBox, QComboBox)):
            continue  # the inside of a spin box or combo box, named through its owner
        if isinstance(widget, (QLineEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox, Segmented)):
            out.append(widget)
    return out


def unnamed(root: QWidget) -> list[str]:
    bad = []
    buddies = {label.buddy() for label in root.findChildren(QLabel) if label.buddy() is not None}
    for field in fields_of(root):
        label = f"{type(field).__name__}:{field.objectName()}"
        if isinstance(field, QComboBox):
            # Qt 6.11 answers a combo box's accessible Name with its current text whatever is set, so
            # a screen reader takes its label from the "labelled by" relation that a buddy creates.
            # A combo with no visible label carries its own accessible name instead.
            own = field.accessibleName().strip()
            if field not in buddies and (not own or own == field.currentText()):
                bad.append(f"{label} has no buddy label and no name of its own")
            continue
        name = a11y_name(field).strip()
        value = field.currentText() if isinstance(field, Segmented) else ""
        if isinstance(field, QLineEdit):
            value = field.text()
        placeholder = getattr(field, "placeholderText", lambda: "")()
        if not name or name in (value, placeholder):
            bad.append(f"{label} named {name!r}")
    return bad


def open_add_homework(qapp, made) -> QWidget:
    host = QWidget()
    made.append(host)
    dialog = HomeworkDialog(host, today="2026-10-05", category="assignments")
    made.insert(0, dialog)
    _up(qapp, dialog)
    dialog.more_details.setChecked(True)
    qapp.processEvents()
    return dialog


def open_block_editor(qapp, made) -> QWidget:
    host = QWidget()
    made.append(host)
    dialog = BlockDialog(host, day=2, start="16:00", duration_min=60)
    made.insert(0, dialog)
    _up(qapp, dialog)
    dialog.more_details.setChecked(True)
    qapp.processEvents()
    return dialog


def open_setup_week(qapp, made) -> QWidget:
    box = _setup(qapp, "school-start")
    made.extend(box.owned)
    return box.top


SHEETS = {"add-homework": open_add_homework, "block-editor": open_block_editor, "setup-week": open_setup_week}


@pytest.mark.parametrize("sheet", list(SHEETS))
def test_0f_every_field_has_a_name_that_is_not_its_value_and_combos_have_a_buddy(qapp, made, sheet) -> None:
    root = SHEETS[sheet](qapp, made)
    assert fields_of(root), "found no fields"
    assert unnamed(root) == []


# 0g ---------------------------------------------------------------------------------------------

def test_0g_a_bad_username_moves_focus_to_username_with_the_message_under_it(qapp, signed_out) -> None:
    w = signed_out
    w.resize(1280, 860)
    _up(qapp, w)
    w.findChild(QPushButton, "authSwitch").click()
    qapp.processEvents()
    w.username.setText("jo")
    w.password.setText("short")
    create = w.findChild(QPushButton, "createAccount")
    create.setFocus()
    press(create, Qt.Key.Key_Space)
    for _ in range(5):
        qapp.processEvents()
    assert QApplication.focusWidget() is w.username, f"focus on {QApplication.focusWidget()}"
    said = w.username.accessibleDescription()
    assert said.startswith("Use 3 to 32")
    shown = [lab for lab in w.findChildren(QLabel) if lab.isVisible() and lab.text() == said]
    assert shown, "the description is not the message on screen"
    below = w.username.mapTo(w, w.username.rect().bottomLeft()).y()
    top = w.username_problem.mapTo(w, w.username_problem.rect().topLeft()).y()
    assert 0 <= top - below <= 24, f"message {top - below}px under Username"


def test_0g_after_fixing_the_username_focus_goes_to_password(qapp, signed_out) -> None:
    w = signed_out
    _up(qapp, w)
    w.findChild(QPushButton, "authSwitch").click()
    qapp.processEvents()
    w.username.setText("jo")
    w.password.setText("short")
    create = w.findChild(QPushButton, "createAccount")
    create.setFocus()
    press(create, Qt.Key.Key_Space)
    qapp.processEvents()
    assert QApplication.focusWidget() is w.username
    w.username.setFocus()
    w.username.selectAll()
    QTest.keyClicks(w.username, "good_name")
    qapp.processEvents()
    assert QApplication.focusWidget() is w.password or w.password.isAncestorOf(QApplication.focusWidget())
    assert "password" in w.password.accessibleDescription().lower()


def test_0g_reset_password_validation_is_announced_under_the_password(qapp, signed_out, monkeypatch) -> None:
    w = signed_out
    _up(qapp, w)
    announced = []
    monkeypatch.setattr(
        "desktop.native.window.announce",
        lambda field, words, assertive=False: announced.append((field, words, assertive)),
    )
    w.findChild(QPushButton, "forgotPassword").click()
    w.username.setText("student_1")
    w.recovery_code.setText("one-time-code")
    w._recover_account()
    assert QApplication.focusWidget() is w.new_recovery_password
    assert w.new_recovery_password.accessibleDescription() == "Choose a password with at least 12 characters."
    assert w.recovery_password_problem.isVisibleTo(w)
    assert announced == [
        (w.new_recovery_password, "Error: Choose a password with at least 12 characters.", True)
    ]


# 0h ---------------------------------------------------------------------------------------------

def test_0h_tab_leaves_notes_and_shift_tab_comes_back(qapp, made) -> None:
    dialog = open_add_homework(qapp, made)
    notes = dialog.findChild(QPlainTextEdit, "homeworkNotes")
    notes.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    press(notes, Qt.Key.Key_Tab)
    assert notes.toPlainText() == "" and QApplication.focusWidget() is not notes
    press(notes, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    assert QApplication.focusWidget() is notes


# 0i / 0j ----------------------------------------------------------------------------------------



def tab_walk(setup, start: QWidget, limit: int = 120) -> list[QWidget]:
    start.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()
    seen = [QApplication.focusWidget()]
    for _ in range(limit):
        press(setup, Qt.Key.Key_Tab)
        now = QApplication.focusWidget()
        if now is setup.next or now in seen:
            seen.append(now)
            break
        seen.append(now)
    return seen


@pytest.mark.parametrize("rows", [1, 2], ids=["one-activity", "two-activities"])
def test_0i_tab_from_school_reaches_every_activity_before_next(qapp, made, rows) -> None:
    setup = open_setup_week(qapp, made)
    while len(setup.activities) < rows:
        setup._add_activity("Band", [2])
    qapp.processEvents()
    first_day = next(b for b in setup.school_days.findChildren(QPushButton) if b.isVisible())
    walked = tab_walk(setup, first_day)
    names = [row.name for row in setup.activities]
    assert walked[-1] is setup.next, "Tab never reached Next"
    missing = [n.text() or "(empty)" for n in names if n not in walked]
    assert missing == [], f"reached Next before activity rows {missing}"


def remove_by_keyboard(setup, row) -> None:
    remove = next(b for b in row.findChildren(QPushButton) if b.accessibleName() == "Remove this activity")
    remove.setFocus(Qt.FocusReason.TabFocusReason)
    QApplication.processEvents()
    press(remove, Qt.Key.Key_Space)
    for _ in range(3):
        QApplication.processEvents()


def test_0j_removing_activities_keeps_focus_in_the_list(qapp, made) -> None:
    setup = open_setup_week(qapp, made)
    while len(setup.activities) < 3:
        setup._add_activity(f"Club {len(setup.activities)}", [2])
    qapp.processEvents()
    first, middle, last = setup.activities[:3]
    remove_by_keyboard(setup, middle)
    assert QApplication.focusWidget() is last.name, "after removing the middle row"
    remove_by_keyboard(setup, last)
    assert QApplication.focusWidget() is first.name, "after removing the last row"
    remove_by_keyboard(setup, first)
    assert QApplication.focusWidget() is setup.add_activity, "after removing the only row"


# 0k ---------------------------------------------------------------------------------------------

def test_0k_a_week_list_names_each_block_with_its_day_and_times(qapp, window) -> None:
    session = window.session
    session.add_block({"id": "school", "title": "School", "kind": "locked", "category": "class",
                       "start": "08:30", "duration_min": 405, "days": [0, 1, 2, 3, 4]})
    session.save()
    settled(qapp, window)
    rows = []
    for listing in window.findChildren(QListWidget):
        if listing.isVisible() or listing.isVisibleTo(window):
            for i in range(listing.count()):
                item = listing.item(i)
                rows.append(f"{item.text()} {item.data(Qt.ItemDataRole.AccessibleTextRole) or ''}")
    school = [r for r in rows if "School" in r]
    assert school and any("Monday" in r and "8:30 AM" in r and "3:15 PM" in r for r in school), rows[:10]


def test_0k_the_grid_is_named_week_view_hours(qapp, window) -> None:
    from desktop.native.hours.canvas import HoursCanvas

    canvases = window.findChildren(HoursCanvas)
    assert canvases and all(c.accessibleName() == "Week view, hours" for c in canvases)


def test_0k_the_week_list_precedes_the_grid_and_enter_opens_a_block(qapp, window, monkeypatch) -> None:
    session = window.session
    session.add_block({"id": "school", "title": "School", "kind": "locked", "category": "class",
                       "start": "08:30", "duration_min": 405, "days": [0, 1, 2, 3, 4]})
    settled(qapp, window)
    listing = window.week_access_list
    canvas = window.week_table.hours
    assert listing.isVisible()
    cursor = listing.nextInFocusChain()
    seen: list[QWidget] = []
    while cursor is not listing and cursor not in seen:
        seen.append(cursor)
        if cursor is canvas:
            break
        cursor = cursor.nextInFocusChain()
    assert canvas in seen, "week grid is not after the list in Tab order"
    row = next(
        listing.item(index)
        for index in range(listing.count())
        if listing.item(index).data(Qt.ItemDataRole.UserRole) == ("school", 0)
    )
    opened: list[str] = []
    monkeypatch.setattr(window, "_edit_block", opened.append)
    listing.setCurrentItem(row)
    listing.setFocus(Qt.FocusReason.OtherFocusReason)
    session.add_block({"id": "club", "title": "Club", "kind": "locked", "category": "exercise",
                       "start": "16:00", "duration_min": 60, "days": [0]})
    settled(qapp, window)
    assert QApplication.focusWidget() is listing
    assert listing.currentItem().data(Qt.ItemDataRole.UserRole) == ("school", 0)
    assert any("Club" in listing.item(index).text() for index in range(listing.count()))
    press(listing, Qt.Key.Key_Return)
    assert opened == ["school"]


def test_0k_week_shortcut_and_mini_month_have_accessible_names(qapp, window) -> None:
    from desktop.native.hours.rail import MonthCard

    window.week_table.hours.setFocus(Qt.FocusReason.OtherFocusReason)
    mods = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    press(window.week_table.hours, Qt.Key.Key_L, mods)
    assert QApplication.focusWidget() is window.week_access_list
    month = window.findChild(MonthCard).dates
    assert month.accessibleName().startswith("Month, ")
    assert "week beginning" in month.accessibleDescription().lower()
