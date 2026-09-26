"""What a drag on the hours makes, and what it says once it is saved."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QEvent, QPoint, QPointF, QStandardPaths, Qt
    from PySide6.QtGui import QAction, QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLabel, QPushButton, QWidget

    from desktop.native.calendar import sunday_due
    from desktop.native.hours.canvas import HoursCanvas
    from desktop.native.widgets import BlockDialog
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup

    LEFT = Qt.MouseButton.LeftButton

PASSWORD = "a-long-test-password"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-drag-results-test"])


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def settled(qapp: QApplication, window: NativeWindow) -> None:
    """The save and the refreshes it starts have all landed."""
    session = window.session
    wait_until(
        qapp, lambda: not session.busy and not session.dirty and not any(session.client._replies.values())
    )
    for _ in range(5):
        qapp.processEvents()


def look_file() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(root) / "flexweek-look.json"


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path) -> Iterator[NativeWindow]:
    """Today's app's Week: School on weekdays 08:00-14:30, Piano on Thursday 17:00-17:30, the History
    essay on Thursday 19:00-20:00 and a Math worksheet with no time yet. The clock is held at Thursday
    10:00."""
    look_file().unlink(missing_ok=True)
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    made.resize(1280, 860)
    made.show()
    try:
        made.username.setText("drag_results_student")
        made.password.setText(PASSWORD)
        made.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
        made.recovery_ack.setChecked(True)
        made.recovery_continue.click()
        past_setup(qapp, made)
        session = made.session
        thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=10)
        session.now_ms = lambda: int(thursday.timestamp() * 1000)
        session.add_block(
            {"id": "school", "title": "School", "kind": "locked", "category": "class",
             "start": "08:00", "duration_min": 390, "days": [0, 1, 2, 3, 4]}
        )
        session.add_block(
            {"id": "piano", "title": "Piano", "kind": "locked", "category": "extra",
             "start": "17:00", "duration_min": 30, "days": [3]}
        )
        due = sunday_due(session.week_start)
        for key, title in (("essay", "History essay"), ("math", "Math worksheet")):
            session.add_homework({"id": key, "title": title, "due": due, "estimate_min": 60, "revision": 0})
        session.save()
        settled(qapp, made)
        essay = session_of(made, "essay")
        session.add_block({**essay, "start": "19:00", "days": [3], "pinned": True})
        session.save()
        settled(qapp, made)
        made.findChild(QPushButton, "viewWeek").click()
        settled(qapp, made)
        yield made
    finally:
        with contextlib.suppress(RuntimeError):
            made.session.client.reset()
        made.hide()
        qapp.processEvents()
        server.stop()
        look_file().unlink(missing_ok=True)


def session_of(window: NativeWindow, assignment_id: str) -> dict:
    return next(block for block in window.session.blocks if block.get("assignment_id") == assignment_id)


def minute(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def send(widget: QWidget, kind: QEvent.Type, at: QPoint, held: bool) -> None:
    buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
    event = QMouseEvent(
        kind, QPointF(widget.mapFromGlobal(at)), QPointF(at), Qt.MouseButton.LeftButton, buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, event)


def drag(qapp: QApplication, source: QWidget, hours: HoursCanvas, start: QPoint, end: QPoint) -> None:
    """Press on `source`, move over `hours` and let go, as a mouse does."""
    send(source, QEvent.Type.MouseButtonPress, start, True)
    for step in range(1, 9):
        send(hours, QEvent.Type.MouseMove, start + (end - start) * step / 8, True)
    send(hours, QEvent.Type.MouseButtonRelease, end, False)
    qapp.processEvents()


def click(qapp: QApplication, widget: QWidget, at: QPoint) -> None:
    send(widget, QEvent.Type.MouseButtonPress, at, True)
    send(widget, QEvent.Type.MouseButtonRelease, at, False)
    qapp.processEvents()


def open_thursday(qapp: QApplication, window: NativeWindow) -> HoursCanvas:
    """A click on Thursday's name in the Week opens it on Day."""
    QTest.mouseClick(window.findChild(QLabel, "weekDayName3"), LEFT)
    settled(qapp, window)
    assert window.session.planner_view == "day"
    return window.day_view.hours


def answer_editors(monkeypatch: pytest.MonkeyPatch, *titles: str | None) -> list[tuple[str, str]]:
    """Each block editor that opens is shown, and what its title and category say is kept. Then the
    title is typed and Save pressed, or with None, Cancel pressed."""
    seen: list[tuple[str, str]] = []
    queue = list(titles)

    def run(dialog: BlockDialog) -> int:
        dialog.show()
        seen.append((dialog.title.text(), dialog.category.currentText()))
        buttons = dialog.findChild(QDialogButtonBox, "dialogButtons")
        title = queue.pop(0)
        if title is None:
            QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Cancel), LEFT)
        else:
            dialog.title.selectAll()
            QTest.keyClicks(dialog.title, title)
            QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Save), LEFT)
        return dialog.result()

    monkeypatch.setattr(BlockDialog, "exec", run)
    return seen


def create_on(
    qapp: QApplication, window: NativeWindow, hours: HoursCanvas, day: int, span: str, title: str
) -> None:
    """Drag across free time from the first to the second of "HH:MM-HH:MM", and wait until the
    block the editor names `title` is saved."""
    start, end = minute(span[:5]), minute(span[6:])
    hours.reveal(day, start - 60, end + 60)
    qapp.processEvents()
    # Two pixels into the first minute, so the press is on free time rather than a block's edge.
    drag(qapp, hours, hours, hours.point_for(day, start) + QPoint(0, 2), hours.point_for(day, end))
    wait_until(qapp, lambda: any(block["title"] == title for block in window.session.blocks))
    settled(qapp, window)


def test_a_block_made_by_dragging_has_no_category_until_the_student_picks_one(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It used to be School, so an hour of Club counted as School in the Day's summary. A type picked
    under Add, "Then drag on the calendar", is still what the next drag makes."""
    seen = answer_editors(monkeypatch, "Club", None, "Practice")
    add = window.findChild(QPushButton, "addButton")
    day = open_thursday(qapp, window)
    says = [add.text()]
    create_on(qapp, window, day, 3, "16:00-17:00", "Club")
    window.add_menu.findChild(QAction, "addMenu-exercise").trigger()
    settled(qapp, window)
    says.append(add.text())
    create_on(qapp, window, day, 3, "17:30-18:00", "Practice")
    made = {
        block["title"]: (block["days"], block["start"], block["duration_min"], block.get("category"))
        for block in window.session.blocks
        if block["title"] in ("Club", "Practice")
    }
    assert (says, seen, made, window.day_view.summary.text()) == (
        ["Add", "Add sports"],
        [("", "None"), ("Sports", "Sports"), ("Sports", "Sports")],
        {"Club": ([3], "16:00", 60, None), "Practice": ([3], "17:30", 30, "exercise")},
        "School: 6 h 30 min\nOther: 1 h\nActivity: 30 min\nSports: 30 min\nHomework: 1 h",
    )


def notice(window: NativeWindow) -> tuple[bool, str, str]:
    """The toast with a button to press: whether it shows, its words and its button."""
    toast = window.toast
    if not toast.isVisible() or not toast.button.isVisible():
        return False, "", ""
    return True, toast.text(), toast.button.text()


def toast(window: NativeWindow) -> str:
    return window.toast.text() if window.toast.isVisible() else ""


def tray_chip(window: NativeWindow, block_id: str) -> QPushButton:
    return next(
        chip
        for chip in window.findChildren(QPushButton)
        if chip.property("block_id") == block_id and chip.property("tray") and chip.isVisible()
    )


def test_a_move_a_resize_a_create_and_a_placing_each_say_what_they_did_with_undo(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dragging saved at once with no sign. Now each change says what it did once it is saved, with
    Undo beside it, and Undo takes that one change back and says so."""
    session = window.session
    answer_editors(monkeypatch, "Club")
    hours = window.week_table.hours
    math = session_of(window, "math")["id"]
    said = []

    hours.reveal(3, 17 * 60, 21 * 60)
    qapp.processEvents()
    drag(qapp, hours, hours, hours.point_for(3, 19 * 60 + 30), hours.point_for(4, 18 * 60 + 30))
    wait_until(qapp, lambda: session_of(window, "essay")["days"] == [4])
    settled(qapp, window)
    said.append(notice(window))

    hours.reveal(4, 17 * 60, 21 * 60)
    qapp.processEvents()
    # Three pixels inside the essay's end, where a press resizes it.
    edge = QPoint(0, -3)
    drag(qapp, hours, hours, hours.point_for(4, 19 * 60) + edge, hours.point_for(4, 19 * 60 + 30) + edge)
    wait_until(qapp, lambda: session_of(window, "essay")["duration_min"] == 90)
    settled(qapp, window)
    said.append(notice(window))

    create_on(qapp, window, hours, 5, "10:00-11:00", "Club")
    said.append(notice(window))

    hours.reveal(3, 17 * 60, 20 * 60)
    qapp.processEvents()
    before = [dict(block) for block in session.blocks]
    drag(qapp, tray_chip(window, math), hours, tray_chip(window, math).mapToGlobal(QPoint(8, 8)),
         hours.point_for(3, 18 * 60))
    wait_until(qapp, lambda: session_of(window, "math").get("start") == "18:00")
    settled(qapp, window)
    said.append(notice(window))
    assert said == [
        (True, "Moved History essay to Fri 18:00.", "Undo"),
        (True, "History essay now ends at 19:30.", "Undo"),
        (True, "Added Club on Sat 10:00.", "Undo"),
        (True, "Placed Math worksheet on Thu 18:00.", "Undo"),
    ]

    QTest.mouseClick(window.findChild(QPushButton, "toastButton"), LEFT)
    wait_until(qapp, lambda: not session_of(window, "math").get("start"))
    settled(qapp, window)
    assert (notice(window), toast(window)) == ((False, "", ""), "Undid placing Math worksheet.")
    assert session.blocks == before, "Undo took back the placing and nothing else"


def test_the_notice_waits_for_the_pointer_and_goes_once_its_change_is_no_longer_the_last(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Nothing new appears under a held block, so a notice that lands while one is held waits for it
    to be let go. Once a later change is saved, its Undo would take back that one instead, so it
    goes."""
    session = window.session
    hours = window.week_table.hours
    hours.reveal(3, 16 * 60, 21 * 60)
    qapp.processEvents()
    drag(qapp, hours, hours, hours.point_for(3, 19 * 60 + 30), hours.point_for(3, 20 * 60 + 30))
    assert session.busy, "the essay's save is still on its way"
    # The chips the release took out of the tray are freed before a hand could press again. Freed
    # while a block is held, each is a window of its own going, which lets the block go.
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    # Held on Piano while the essay's save lands.
    send(hours, QEvent.Type.MouseButtonPress, hours.point_for(3, 17 * 60 + 15), True)
    send(hours, QEvent.Type.MouseMove, hours.point_for(3, 17 * 60 + 45), True)
    wait_until(qapp, lambda: not session.busy and session_of(window, "essay")["start"] == "20:00")
    held = notice(window)
    send(hours, QEvent.Type.MouseButtonRelease, hours.point_for(3, 17 * 60 + 45), False)
    qapp.processEvents()
    let_go = notice(window)
    wait_until(qapp, lambda: next(b for b in session.blocks if b["id"] == "piano")["start"] == "17:30")
    settled(qapp, window)
    after_piano = notice(window)
    session.select_block("piano", 3)
    QTest.keyClick(window, Qt.Key.Key_Delete)
    settled(qapp, window)
    assert (held, let_go, after_piano, notice(window)) == (
        (False, "", ""),
        (True, "Moved History essay to Thu 20:00.", "Undo"),
        (True, "Moved Piano to Thu 17:30.", "Undo"),
        (False, "", ""),
    )


def test_a_move_in_a_design_says_what_it_did_too(qapp: QApplication, window: NativeWindow) -> None:
    from desktop.native.layouts.registry import sanitize_layout

    window._layout = sanitize_layout({"main": "mission", "day": "one"})
    window._apply_appearance()
    window._on_week()
    settled(qapp, window)
    hours = window.planner.currentWidget().hours_surfaces()[0]
    hours.reveal(3, 17 * 60, 21 * 60)
    qapp.processEvents()
    drag(qapp, hours, hours, hours.point_for(3, 19 * 60 + 30), hours.point_for(4, 18 * 60 + 30))
    wait_until(qapp, lambda: session_of(window, "essay")["days"] == [4])
    settled(qapp, window)
    assert notice(window) == (True, "Moved History essay to Fri 18:00.", "Undo")


def test_a_chip_carried_on_month_says_what_it_did(qapp: QApplication, window: NativeWindow) -> None:
    from datetime import date

    # Inside the offscreen screen, 800 pixels square, where the hand can find the date under a point.
    window.move(0, 0)
    window.resize(760, 720)
    QTest.mouseClick(window.findChild(QPushButton, "viewMonth"), LEFT)
    settled(qapp, window)
    canvas = window.month_grid.canvas
    thursday = date.fromisoformat(window.session.week_start) + timedelta(days=3)
    friday = thursday + timedelta(days=1)
    canvas.reveal(thursday.isoformat())
    qapp.processEvents()
    essay = session_of(window, "essay")["id"]
    start, end = canvas.chip_point(essay, thursday.isoformat()), canvas.cell_point(friday.isoformat())
    drag(qapp, canvas, canvas, start, end)
    wait_until(qapp, lambda: session_of(window, "essay")["days"] == [4])
    settled(qapp, window)
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    words = f"Moved History essay to Fri {friday.day} {months[friday.month - 1]}."
    assert notice(window) == (True, words, "Undo")


def advanced(window: NativeWindow, words: str) -> None:
    """Pick the item under More > Advanced whose words start with `words`, as a click on it does."""
    menu = window.more_button.menu()
    menu.aboutToShow.emit()
    inner = next(action.menu() for action in menu.actions() if action.menu() and action.text() == "Advanced")
    next(action for action in inner.actions() if action.text().startswith(words)).trigger()


def test_every_advanced_action_says_what_it_did_when_it_is_done(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Their words went only to the status line at the foot of the window, which nobody watched."""
    from PySide6.QtWidgets import QComboBox, QLineEdit

    from desktop.native.settings import RestoreDialog
    from desktop.native.widgets import PreviewDialog

    days = iter((4, 5))

    def preview(dialog: PreviewDialog) -> int:
        """Put the copy on a free day, which ticks it, and save the preview."""
        dialog.show()
        dialog.findChild(QComboBox, "previewDay0").setCurrentIndex(next(days))
        QTest.mouseClick(dialog.confirm, LEFT)
        return dialog.result()

    def restore(dialog: RestoreDialog) -> int:
        dialog.show()
        QTest.keyClicks(dialog.findChild(QLineEdit, "restoreLabel"), "Before exams")
        QTest.mouseClick(dialog.findChild(QPushButton, "restoreCreate"), LEFT)
        return dialog.result()

    monkeypatch.setattr(PreviewDialog, "exec", preview)
    monkeypatch.setattr(RestoreDialog, "exec", restore)
    hours = window.week_table.hours
    hours.reveal(3, 16 * 60, 19 * 60)
    qapp.processEvents()
    click(qapp, hours, hours.point_for(3, 17 * 60 + 15))
    assert window.session.selected_block_id == "piano"
    said = []
    for words in ("Copy", "Paste", "Duplicate", "Copy Thursday", "Save", "Undo", "Redo", "Restore", "Reload"):
        window.toast.hide()
        advanced(window, words)
        settled(qapp, window)
        said.append((words, toast(window)))
    assert said == [
        ("Copy", "Piano copied. Choose a destination and paste."),
        ("Paste", "Pasted Piano."),
        ("Duplicate", "Duplicated Piano."),
        ("Copy Thursday", "Thursday · 3 items copied. Choose a destination and paste."),
        ("Save", "Saved."),
        ("Undo", "Undid duplicating Piano."),
        ("Redo", "Redid duplicating Piano."),
        ("Restore", "Saved restore point Before exams."),
        ("Reload", "Reloaded this week."),
    ]


def test_a_save_that_leaves_the_homework_waiting_keeps_the_same_chips(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Chips made again on every save were shown a frame after the old ones went, so Today's app's
    "Needs a time" bar blinked empty each time a block moved."""
    before = tray_chip(window, session_of(window, "math")["id"])
    essay = session_of(window, "essay")
    window._move_block(essay["id"], 3, 4, minute("18:00"), minute("19:00"))
    settled(qapp, window)
    after = tray_chip(window, session_of(window, "math")["id"])
    assert after is before, "the Needs a time bar made its chips again for the same homework"
    assert after.isVisible()


def test_a_notice_coming_and_going_never_moves_the_hours(
    qapp: QApplication, window: NativeWindow
) -> None:
    """A notice in a row of its own pushed the page down under the pointer, and on a short window put
    the next drop where the hours scroll by themselves. The toast floats over the hours instead."""
    before = window.planner.geometry()
    window._set_notice("Moved History essay to Fri 18:00.", "Undo", lambda: None)
    for _ in range(5):
        qapp.processEvents()
    assert window.toast.isVisible()
    assert window.planner.geometry() == before
    window.toast.hide()
    for _ in range(5):
        qapp.processEvents()
    assert window.planner.geometry() == before


def test_a_short_notice_keeps_its_words_on_one_line(qapp: QApplication, window: NativeWindow) -> None:
    window._set_notice("Moved History essay to Fri 18:00.", "Undo", lambda: None)
    for _ in range(5):
        qapp.processEvents()
    text = window.toast.label
    words = text.fontMetrics().horizontalAdvance("Moved History essay to Fri 18:00.")
    assert text.width() >= words, "the notice's words wrap onto a second line"
    assert window.toast.height() < 2 * text.fontMetrics().height() + 40


def test_the_toast_floats_over_the_foot_of_the_hours_and_lets_the_pointer_through(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Centred over the hours, 16 pixels above their foot, inside the window at any height, and only
    its button takes a click: the hours under its words still take a drag."""
    from desktop.native.widgets import TOAST_FOOT

    pressed = []
    for height in (860, 600):
        window.resize(1280, height)
        for _ in range(5):
            qapp.processEvents()
        window._set_notice("Moved History essay to Fri 18:00.", "Undo", lambda: pressed.append(True))
        # Past its rise into place.
        QTest.qWait(400)
        toast, planner = window.toast, window.planner
        foot = planner.mapTo(window, QPoint(0, planner.height())).y()
        middle = planner.mapTo(window, QPoint(planner.width() // 2, 0)).x()
        assert toast.geometry().bottom() + 1 == foot - TOAST_FOOT, height
        assert abs(toast.geometry().center().x() - middle) <= 1, height
        assert toast.geometry().bottom() < window.height(), height
        words = toast.geometry().topLeft() + QPoint(12, toast.height() // 2)
        assert window.childAt(words) is not toast and not toast.isAncestorOf(window.childAt(words))
        assert planner.isAncestorOf(window.childAt(words)), "the words take the hours' clicks"
        button = toast.button
        assert toast.geometry().contains(button.geometry()), "the button sits inside the toast"
        assert window.childAt(button.geometry().center()) is button
    QTest.mouseClick(window.toast.button, LEFT)
    assert pressed == [True]
    assert not window.toast.isVisible()


def test_a_view_switch_takes_the_toast_away(qapp: QApplication, window: NativeWindow) -> None:
    window._set_notice("Moved History essay to Fri 18:00.", "Undo", lambda: None)
    qapp.processEvents()
    assert window.toast.isVisible()
    QTest.mouseClick(window.findChild(QPushButton, "viewMonth"), LEFT)
    settled(qapp, window)
    assert not window.toast.isVisible() and not window.toast.button.isVisible()


def test_a_routine_save_says_nothing_and_a_refusal_says_why(qapp: QApplication, window: NativeWindow) -> None:
    """The status line said "Saved." after every drag. The toast says only what the student needs."""
    window.toast.hide()
    window.session._say("Saving…")
    window.session._say("Saved.")
    window.session._say("Saved preferences.")
    qapp.processEvents()
    assert not window.toast.isVisible()
    window.session._say("Select a block before copying it.")
    qapp.processEvents()
    assert toast(window) == "Select a block before copying it."
