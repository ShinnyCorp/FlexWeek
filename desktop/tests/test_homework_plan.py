"""Homework and planning through the real window: new homework is due tomorrow, changing the due date
runs what hangs off it, Plan never puts anything before now, a homework's length is checked in words
beside its box, the due date's calendar shows its whole month, and one Plan is one Undo.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import time
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QDate, QPoint, QStandardPaths, Qt, QTime
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QCalendarWidget,
        QDialog,
        QPushButton,
        QTableView,
        QWidget,
    )

    from desktop.native.calendar import date_for_day, sunday_due
    from desktop.native.controller import plan_sentence
    from desktop.native.look import sanitize_look
    from desktop.native.reuse import plan_start, solve_request
    from desktop.native.setup import FIRST
    from desktop.native.widgets import DueField, HomeworkDialog, Toast
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import fail_once, past_setup

PASSWORD = "a-long-test-password"
TOO_LATE = "That time has already passed."
PAST_WEEK = "This week is over, so nothing was planned. Plan this week or a later one."


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-homework-plan-test"])


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def settled(qapp: QApplication, window: NativeWindow) -> None:
    for _ in range(3):
        wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)
        QTest.qWait(40)


def look_file() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(root) / "flexweek-look.json"


def signed_up(qapp: QApplication, server: LocalServer, name: str) -> NativeWindow:
    made = NativeWindow(server.origin)
    made.resize(1280, 860)
    made.show()
    made.username.setText(name)
    made.password.setText(PASSWORD)
    made.findChild(QPushButton, "createAccount").click()
    wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
    made.recovery_ack.setChecked(True)
    made.recovery_continue.click()
    return made


def closed(qapp: QApplication, made: NativeWindow) -> None:
    with contextlib.suppress(RuntimeError):
        made.session.client.reset()
    made.hide()
    qapp.processEvents()


@pytest.fixture()
def server(qapp: QApplication, tmp_path: Path) -> Iterator[LocalServer]:
    look_file().unlink(missing_ok=True)
    running = LocalServer(tmp_path / "flexweek.db")
    running.start()
    yield running
    running.stop()
    look_file().unlink(missing_ok=True)


@pytest.fixture()
def window(qapp: QApplication, server: LocalServer) -> Iterator[NativeWindow]:
    """This week: School Monday to Friday 08:00-14:30, the History essay placed by hand on Thursday
    19:00-20:00, and a Math worksheet due Sunday that still needs a time. The clock is held at
    Thursday 10:00."""
    made = signed_up(qapp, server, "plan_student")
    try:
        past_setup(qapp, made)
        session = made.session
        thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=10)
        session.now_ms = lambda: int(thursday.timestamp() * 1000)
        session.add_block(
            {
                "id": "school",
                "title": "School",
                "kind": "locked",
                "category": "class",
                "start": "08:00",
                "duration_min": 390,
                "days": [0, 1, 2, 3, 4],
            }
        )
        due = sunday_due(session.week_start)
        for key, title in (("essay", "History essay"), ("math", "Math worksheet")):
            session.add_homework({"id": key, "title": title, "due": due, "estimate_min": 60, "revision": 0})
        session.save()
        settled(qapp, made)
        session.place_session(session_of(made, "essay")["id"], 3, 19 * 60)
        session.save()
        settled(qapp, made)
        yield made
    finally:
        closed(qapp, made)


def session_of(window: NativeWindow, assignment_id: str) -> dict:
    return next(block for block in window.session.blocks if block.get("assignment_id") == assignment_id)


def thursday_iso(window: NativeWindow) -> str:
    return date_for_day(window.session.week_start, 3)


def opened_with(
    monkeypatch: pytest.MonkeyPatch, act: Callable[[HomeworkDialog], int]
) -> list[HomeworkDialog]:
    """Every homework editor the window opens is handed to `act` instead of waiting for a student."""
    seen: list[HomeworkDialog] = []

    def run(dialog: HomeworkDialog) -> int:
        seen.append(dialog)
        return act(dialog)

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    return seen


def press(dialog: QDialog, name: str) -> int:
    dialog.findChild(QPushButton, name).click()
    return QDialog.DialogCode.Accepted


def test_nothing_placed_says_nothing_placed_not_planned_zero() -> None:
    assert plan_sentence(0, 1) == "Nothing placed. 1 still needs a time."
    assert plan_sentence(0, 2) == "Nothing placed. 2 still need a time."
    assert plan_sentence(1, 1) == "Planned 1 homework block. 1 still needs a time."
    assert plan_sentence(3, 0) == "Planned 3 homework blocks."


# Due today


def test_new_homework_opens_due_tomorrow_whatever_week_is_on_screen(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    dues: list[str] = []

    def look(dialog: HomeworkDialog) -> int:
        dues.append(dialog.due.value())
        return QDialog.DialogCode.Rejected

    opened_with(monkeypatch, look)
    window._add_homework()
    tomorrow = (date.fromisoformat(thursday_iso(window)) + timedelta(days=1)).isoformat()
    assert dues == [tomorrow], "tomorrow, not on the Monday of the week on screen"

    dues.clear()
    window._edit_homework("math")
    assert dues == [window.session.assignments["math"]["due"][:10]], "editing keeps its own due date"

    ahead = (date.fromisoformat(window.session.week_start) + timedelta(days=7)).isoformat()
    window.session.load_week(ahead)
    wait_until(qapp, lambda: window.session.week_start == ahead and not window.session.busy)
    window._add_homework()
    assert dues[-1] == tomorrow


# The due date's follow-ups


def test_changing_the_due_date_turns_off_what_acts_on_the_saved_homework(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Let FlexWeek move it acts on the saved homework, so an unsaved edit turns it off. The due date's
    signal handed a date to a signal that takes none, raised inside Qt, and nothing connected after it
    ran."""
    states: list[tuple[str, bool]] = []

    def change(dialog: HomeworkDialog) -> int:
        unpin = dialog.findChild(QPushButton, "homeworkUnpin")
        states.append(("opened", unpin.isEnabled()))
        dialog.due.date.setDate(dialog.due.date.date().addDays(-1))
        states.append(("date", unpin.isEnabled()))
        return QDialog.DialogCode.Rejected

    opened_with(monkeypatch, change)
    window._edit_homework("essay")
    assert states == [("opened", True), ("date", False)]

    for step in ("timed", "time"):
        states.clear()

        def other(dialog: HomeworkDialog, step: str = step) -> int:
            unpin = dialog.findChild(QPushButton, "homeworkUnpin")
            if step == "timed":
                dialog.due.timed.setChecked(True)
            else:
                dialog.due.time.setTime(QTime(7, 45))
            states.append((step, unpin.isEnabled()))
            return QDialog.DialogCode.Rejected

        opened_with(monkeypatch, other)
        window._edit_homework("essay")
        assert states == [(step, False)], f"changing the {step} turns it off too"


def test_a_due_field_says_it_changed_with_no_arguments(qapp: QApplication) -> None:
    field = DueField("2026-09-24", "probe")
    heard: list[tuple] = []
    field.changed.connect(lambda *args: heard.append(args))
    field.date.setDate(QDate(2026, 9, 25))
    field.timed.setChecked(True)
    field.time.setTime(QTime(8, 15))
    assert heard == [(), (), ()]


# Plan never before now


def test_a_plan_starts_at_now_rounded_up_to_the_next_quarter_hour() -> None:
    def at(day: int, hour: int, minute: int, second: int = 0) -> tuple[int, int] | None:
        return plan_start("2026-09-21", datetime(2026, 9, day, hour, minute, second))

    assert at(24, 10, 0) == (3, 600)
    assert at(24, 10, 0, 30) == (3, 615)
    assert at(24, 10, 7) == (3, 615)
    assert at(24, 23, 50) == (4, 0)
    assert at(27, 23, 55) == (7, 0), "past Sunday: the week is over"
    assert at(20, 22, 0) is None, "the whole week is still ahead"


def test_plan_sends_earliest_from_not_before_not_a_stored_session_field() -> None:
    """DEADLINE_PASSED compares due to earliest; Plan sets earliest from now via not_before."""
    blocks = [
        {
            "id": "essay",
            "title": "Essay",
            "kind": "flexible",
            "duration_min": 60,
            "days": [0],
            "priority": 3,
            "energy": "medium",
            "assignment_id": "essay-a",
        }
    ]
    assignments = {
        "essay-a": {
            "id": "essay-a",
            "title": "Essay",
            "due": "2026-09-08T23:59",
            "estimate_min": 60,
            "focus_minutes": 0,
            "revision": 0,
        }
    }
    payload, targets = solve_request(
        blocks, assignments, "2026-09-07", not_before=(0, 10 * 60 + 30)
    )
    assert targets == {"essay"}
    placed = next(block for block in payload if block["id"] == "essay")
    assert placed["earliest"] == "Monday 10:30"
    assert blocks[0].get("earliest") is None


def test_plan_on_a_thursday_leaves_monday_to_wednesday_and_the_hours_before_now_alone(
    qapp: QApplication, window: NativeWindow
) -> None:
    session = window.session
    wednesday = date_for_day(session.week_start, 2)
    session.add_homework(
        {"id": "reading", "title": "Reading log", "due": sunday_due(session.week_start),
         "estimate_min": 60, "energy": "high", "revision": 0},
        days=[3],
    )
    session.add_homework({"id": "chem", "title": "Chem lab report", "due": wednesday, "estimate_min": 60,
                          "revision": 0})
    session.save()
    settled(qapp, window)
    before = {block["id"]: (block["days"], block.get("start")) for block in session.blocks}
    window.findChild(QPushButton, "solveButton").click()
    settled(qapp, window)

    after = {block["id"]: (block["days"], block.get("start")) for block in session.blocks}
    moved = {key: value for key, value in after.items() if before.get(key) != value}
    assert moved, "the plan placed something"
    for key, (days, start) in moved.items():
        assert start is not None and (days[0], start) >= (3, "10:00"), f"{key} planned at {days} {start}"
    assert session_of(window, "reading")["days"] == [3]
    assert session_of(window, "reading")["start"] >= "10:00", "its morning is before now"
    assert session_of(window, "math")["days"][0] >= 3
    chem = session_of(window, "chem")
    assert not chem.get("start"), "due yesterday: there is no time left for it this week"
    assert session.needs_time[chem["id"]] == TOO_LATE


def test_replan_all_leaves_homework_whose_time_has_passed(qapp: QApplication, window: NativeWindow) -> None:
    session = window.session
    math = session_of(window, "math")
    session.add_block({**math, "start": "15:00", "days": [1]})
    session.save()
    settled(qapp, window)
    assert not session_of(window, "math").get("pinned")
    window.findChild(QPushButton, "replanAll").click()
    settled(qapp, window)
    math = session_of(window, "math")
    assert (math["days"], math["start"]) == ([1], "15:00"), "Tuesday is gone; Replan all leaves it be"


def test_plan_it_as_i_add_it_starts_no_earlier_than_now(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.session.preferences = {**(window.session.preferences or {}), "planning_style": "auto"}

    def fill(dialog: HomeworkDialog) -> int:
        dialog.title.setText("Spanish vocab")
        dialog.due.date.setDate(QDate.fromString(sunday_due(window.session.week_start)[:10], "yyyy-MM-dd"))
        dialog.energy.setCurrentIndex(dialog.energy.findData("high"))
        dialog.accept()
        return QDialog.DialogCode.Accepted

    opened_with(monkeypatch, fill)
    window._add_homework()
    settled(qapp, window)
    added = next(item for item in window.session.assignments.values() if item["title"] == "Spanish vocab")
    placed = session_of(window, added["id"])
    assert placed.get("start"), "placed as it was added"
    assert (placed["days"][0], placed["start"]) >= (3, "10:00")


def test_plan_on_a_week_that_is_over_places_nothing_and_says_so(
    qapp: QApplication, window: NativeWindow
) -> None:
    session = window.session
    last = (date.fromisoformat(session.week_start) - timedelta(days=7)).isoformat()
    session.load_week(last)
    wait_until(qapp, lambda: session.week_start == last and not session.busy)
    session.add_homework({"id": "late", "title": "Old worksheet", "due": sunday_due(last), "estimate_min": 60,
                          "revision": 0})
    session.save()
    settled(qapp, window)
    window.findChild(QPushButton, "solveButton").click()
    settled(qapp, window)
    assert not session_of(window, "late").get("start")
    assert window.toast.text() == PAST_WEEK


# Length


def typed(box: QWidget, text: str) -> None:
    box.setFocus()
    box.selectAll()
    QTest.keyClicks(box, text)


def test_a_length_under_15_minutes_or_over_24_hours_is_refused_beside_the_box(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    said: list[tuple[str, int, bool, bool]] = []

    def enter(dialog: HomeworkDialog) -> int:
        dialog.show()
        dialog.title.setText("Science poster")
        hint = dialog.estimate_hint

        def saved_as(text: str) -> None:
            typed(dialog.estimate, text)
            dialog.accept()
            problem = bool(hint.property("problem"))
            said.append((hint.text(), dialog.estimate.value(), problem, dialog.isVisible()))

        saved_as("0")
        saved_as("1500")
        typed(dialog.estimate, "1440")
        QTest.keyClick(dialog.estimate, Qt.Key.Key_Up)
        said.append(("cap", dialog.estimate.value(), False, False))
        saved_as("90")
        return dialog.result()

    opened_with(monkeypatch, enter)
    window._add_homework()
    settled(qapp, window)
    zero, long, cap, fine = said
    assert zero == ("Give it at least 15 minutes.", 0, True, True), "0 is kept as typed and refused in words"
    assert long[1:] == (1500, True, True) and "Split it into parts" in long[0]
    assert cap[1] == 1440, "the arrows stop at 24 hours"
    assert fine[2:] == (False, False), "a length in range saves"
    saved = next(item for item in window.session.assignments.values() if item["title"] == "Science poster")
    assert saved["estimate_min"] == 90


# The due date's calendar


def calendar_problems(popup: QWidget, screen) -> list[str]:
    """What is cut off. The whole month's grid must fit its view: the look padded the grid like a
    panel, so the calendar lost its last column, or its first once it scrolled to a Sunday."""
    problems = []
    # geometry, not frameGeometry: a popup has no frame, but the offscreen platform draws one.
    if not screen.contains(popup.geometry()):
        problems.append(f"popup {popup.geometry().getRect()} outside {screen.getRect()}")
    view = popup.findChild(QCalendarWidget).findChild(QTableView)
    across, down = view.horizontalHeader(), view.verticalHeader()
    if across.length() > view.viewport().width():
        problems.append(f"the last column is cut: {across.length()} across {view.viewport().width()}")
    if down.length() > view.viewport().height():
        problems.append(f"the last week is cut: {down.length()} down {view.viewport().height()}")
    return problems


def opened_calendar(qapp: QApplication, field: DueField) -> QWidget:
    edit = field.date
    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(edit.width() - 6, edit.height() // 2))
    popup = edit.findChild(QWidget, "qt_datetimedit_calendar")
    wait_until(qapp, lambda: popup is not None and popup.isVisible())
    for _ in range(5):
        qapp.processEvents()
    return popup


@pytest.mark.parametrize("text", ["normal", "large"])
def test_the_due_calendar_shows_its_whole_month_on_the_windows_screen(
    qapp: QApplication, server: LocalServer, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    made = signed_up(qapp, server, f"calendar_{text}")
    try:
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "setupPage")
        if text == "large":
            made.resize(1150, 768)
            knobs = {**made._look.get("knobs", {}), "text": "large"}
            made._look = sanitize_look({**made._look, "knobs": knobs})
            made._apply_appearance()
        setup = made.setup_page
        # Setup draws its style pictures in windows of their own, one at a time; each one shown
        # closes any calendar that is open.
        wait_until(qapp, lambda: not setup._pending_pictures and not setup._warm.isActive())
        setup._show(FIRST)
        qapp.processEvents()
        screen = made.screen().availableGeometry()
        popup = opened_calendar(qapp, setup.homework_rows[0].due)
        assert calendar_problems(popup, screen) == [], "in setup"
        popup.hide()

        found: list[list[str]] = []

        def look(dialog: HomeworkDialog) -> int:
            dialog.show()
            qapp.processEvents()
            shown = opened_calendar(qapp, dialog.due)
            found.append(calendar_problems(shown, dialog.screen().availableGeometry()))
            shown.hide()
            return QDialog.DialogCode.Rejected

        opened_with(monkeypatch, look)
        made._add_homework()
        assert found == [[]], "in Add homework"
    finally:
        closed(qapp, made)


def stored_blocks(window: NativeWindow) -> list[dict]:
    return sorted(window.session.blocks, key=lambda block: block["id"])


def test_plan_says_what_it_did_with_an_undo_that_takes_it_all_back(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = window.session
    for key, title in (("poster", "Science poster"), ("vocab", "Spanish vocab")):
        session.add_homework({"id": key, "title": title, "due": sunday_due(session.week_start),
                              "estimate_min": 45, "revision": 0})
    session.save()
    settled(qapp, window)
    before = stored_blocks(window)
    shown: list[tuple[str, str]] = []
    show = Toast.show_message

    def recorded(toast: Toast, text: str, button: str = "", callback=None) -> None:
        shown.append((text, button))
        show(toast, text, button, callback)

    monkeypatch.setattr(Toast, "show_message", recorded)
    window.findChild(QPushButton, "solveButton").click()
    settled(qapp, window)
    monkeypatch.undo()
    assert shown == [("Planned 3 homework blocks.", "Undo")], "said once, with its Undo, not rewrapped"
    planned = stored_blocks(window)
    assert planned != before
    assert window.toast.button.isVisible()
    assert window.toast.text() == "Planned 3 homework blocks."
    assert window.toast.button.text() == "Undo"

    window.toast.button.click()
    settled(qapp, window)
    assert stored_blocks(window) == before, "one Undo takes back every block the plan placed"
    assert not window.toast.button.isVisible()
    assert session.can_redo()

    session.redo()
    settled(qapp, window)
    assert stored_blocks(window) == planned


def test_replan_all_is_one_undo_step(qapp: QApplication, window: NativeWindow) -> None:
    session = window.session
    window.findChild(QPushButton, "solveButton").click()
    settled(qapp, window)
    session.add_homework({"id": "poster", "title": "Science poster", "due": sunday_due(session.week_start),
                          "estimate_min": 45, "revision": 0})
    session.save()
    settled(qapp, window)
    before = stored_blocks(window)
    window.findChild(QPushButton, "replanAll").click()
    settled(qapp, window)
    assert stored_blocks(window) != before
    assert window.toast.button.text() == "Undo"
    window.toast.button.click()
    settled(qapp, window)
    assert stored_blocks(window) == before


def test_automatic_plan_stays_in_the_add_homework_undo_step(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = window.session
    session.preferences = {**(session.preferences or {}), "planning_style": "auto"}

    def add(dialog: HomeworkDialog) -> int:
        dialog.title.setText("Spanish vocab")
        dialog.due.date.setDate(QDate.fromString(sunday_due(session.week_start)[:10], "yyyy-MM-dd"))
        dialog.estimate.setValue(45)
        dialog.accept()
        return QDialog.DialogCode.Accepted

    opened_with(monkeypatch, add)
    window._add_homework()
    settled(qapp, window)
    added = next(item for item in session.assignments.values() if item["title"] == "Spanish vocab")
    assignment_id = added["id"]
    assert session_of(window, assignment_id).get("start")
    assert not window.toast.button.isVisible(), "the added homework owns this Undo step"

    session.undo()
    settled(qapp, window)
    assert assignment_id not in session.assignments
    assert not any(block.get("assignment_id") == assignment_id for block in session.blocks)
    session.redo()
    settled(qapp, window)
    assert assignment_id in session.assignments
    assert session_of(window, assignment_id).get("start")


def test_plan_undo_notice_disappears_after_a_later_save(
    qapp: QApplication, window: NativeWindow
) -> None:
    session = window.session
    window.findChild(QPushButton, "solveButton").click()
    settled(qapp, window)
    assert window.toast.button.isVisible()

    session.add_homework({"id": "next", "title": "New assignment", "due": sunday_due(session.week_start),
                          "estimate_min": 30, "revision": 0})
    session.save()
    settled(qapp, window)
    assert not window.toast.button.isVisible(), "the old Plan Undo must not undo the new assignment"
    session.undo()
    settled(qapp, window)
    assert "next" not in session.assignments
    assert session_of(window, "math").get("start"), "the earlier plan remains"


def test_a_plan_that_places_nothing_does_not_offer_a_false_undo(
    qapp: QApplication, window: NativeWindow
) -> None:
    session = window.session
    session.complete_homework("math")
    session.add_homework(
        {"id": "overdue", "title": "Overdue worksheet", "due": date_for_day(session.week_start, 2),
         "estimate_min": 60, "revision": 0}
    )
    session.save()
    settled(qapp, window)
    before = stored_blocks(window)
    undo_steps = len(session._undo)
    window.findChild(QPushButton, "solveButton").click()
    settled(qapp, window)
    assert stored_blocks(window) == before
    assert len(session._undo) == undo_steps, "no plan change means no Undo step"
    assert not window.toast.button.isVisible(), "no Undo for a plan that could place nothing"


def test_plan_waits_for_a_failed_save_before_offering_undo(
    qapp: QApplication, window: NativeWindow
) -> None:
    session = window.session
    before = stored_blocks(window)
    session.pending_save = {"weeks": [], "assignments": [], "operation_id": "failed-save"}
    # A save that failed was tried just now, so the autosave tick does not retry it mid-test.
    window._last_try_ms = session.now_ms()
    window.findChild(QPushButton, "solveButton").click()
    qapp.processEvents()
    assert stored_blocks(window) == before
    assert session.message == "Wait a moment: your last change is still saving. Then plan again."
    assert not window.toast.button.isVisible()


@pytest.mark.parametrize(
    ("field", "value", "said"),
    [
        ("title", "", "Give the homework a title."),
        ("title", "x" * 81, "Keep the homework title under 80 characters."),
        ("spotify", "https://example.com/song", "Paste a Spotify share link from open.spotify.com."),
        ("notes", "x" * 4001, "Keep notes under 4,000 characters."),
        ("link", "not-a-link", "A link needs an http:// or https:// address."),
        ("checklist", "x" * 81, "Keep each checklist step under 80 characters."),
        ("due", "yesterday", "Choose a valid due date."),
    ],
)
def test_homework_editor_refuses_each_field_in_its_own_words(
    qapp: QApplication, field: str, value: str, said: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = HomeworkDialog(today="2026-09-24")
    try:
        dialog.show()
        dialog.title.setText("Science poster")
        if field == "title":
            if len(value) > 80:
                dialog.title.setMaxLength(len(value))
            dialog.title.setText(value)
        elif field == "spotify":
            dialog.spotify.setText(value)
        elif field == "notes":
            dialog.notes.setPlainText(value)
        elif field == "link":
            dialog.link_label.setText("Class notes")
            dialog.link_url.setText(value)
            dialog.findChild(QPushButton, "addHomeworkLink").click()
        elif field == "checklist":
            dialog._append_check("step", value, False)
        else:
            # On the class: undone on the instance, the patch left the dialog's own bound method in its
            # dict, a cycle the collector later freed in the local server's thread of another test.
            monkeypatch.setattr(HomeworkDialog, "_chosen_due", lambda _dialog: value)
        dialog.accept()
        assert dialog.isVisible(), "invalid homework stays open"
        assert dialog.error.text() == said
        assert "Value error" not in dialog.error.text()
    finally:
        dialog.close()


def held_solves(window: NativeWindow) -> tuple[list[dict], list[Callable[[], None]]]:
    """Every /api/solve the window sends is kept, unanswered, until a test releases it."""
    sent: list[dict] = []
    waiting: list[Callable[[], None]] = []
    real = window.session.client.request

    def request(verb, target, payload, on_success, on_error):
        if verb == "POST" and target == "/api/solve":
            sent.append(payload)
            waiting.append(lambda: real(verb, target, payload, on_success, on_error))
            return None
        return real(verb, target, payload, on_success, on_error)

    window.session.client.request = request  # type: ignore[method-assign]
    return sent, waiting


def test_twelve_fast_clicks_on_plan_make_one_plan(qapp: QApplication, window: NativeWindow) -> None:
    sent, waiting = held_solves(window)
    plan = window.findChild(QPushButton, "solveButton")
    said: list[str] = []
    window.session.status.connect(said.append)
    for _ in range(12):
        plan.click()
        qapp.processEvents()
    assert not plan.isEnabled(), "disabled from the first click, not after the busy look's delay"
    assert len(sent) == 1
    assert said.count("Planning…") == 1
    waiting[0]()
    settled(qapp, window)
    assert plan.isEnabled(), "back once the result is in"
    assert len(sent) == 1


def test_plan_asked_for_in_other_ways_while_one_is_running_is_ignored(
    qapp: QApplication, window: NativeWindow
) -> None:
    sent, waiting = held_solves(window)
    window.session.solve()
    for _ in range(11):
        window.session.solve()
        window.session.solve(everything=True)
    assert len(sent) == 1
    waiting[0]()
    settled(qapp, window)
    assert len(sent) == 1


PLAN_UNREACHABLE = "Can't reach FlexWeek, so nothing was planned. Try again."
SAVE_UNREACHABLE = (
    "Not saved: FlexWeek can't be reached. Your changes are still here. Choose Retry save."
)


def test_plan_when_the_server_is_unreachable_says_nothing_was_planned(
    qapp: QApplication, window: NativeWindow
) -> None:
    fail_once(window.session, "POST", "/api/solve", 0)
    window.session.solve()
    wait_until(qapp, lambda: not window.session.busy)
    assert window.session.message == PLAN_UNREACHABLE


def test_save_when_the_server_is_unreachable_says_changes_are_kept(
    qapp: QApplication, window: NativeWindow
) -> None:
    session = window.session
    session.blocks = [*session.blocks, {
        "id": "club",
        "title": "Club",
        "kind": "locked",
        "category": "extra",
        "start": "16:00",
        "duration_min": 60,
        "days": [3],
    }]
    session.dirty = True
    fail_once(session, "POST", "/api/changes", 0)
    session.save()
    wait_until(qapp, lambda: not session.busy)
    assert session.message == SAVE_UNREACHABLE


def test_the_rail_and_the_plan_panel_count_the_same_homework_without_a_time(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Audit #10 saw the rail say "Everything has a time." beside a plan panel saying "1 without a
    time". Plan with one project too long for what is left today: both say one, and the rail's
    "Everything has a time." is hidden. Not reproduced on 0.18.0: this test passes without a change."""
    session = window.session
    session.add_homework(
        {
            "id": "project",
            "title": "Long project",
            "due": thursday_iso(window) + "T23:00",
            "estimate_min": 300,
            "revision": 0,
        }
    )
    session.save()
    settled(qapp, window)
    window.findChild(QPushButton, "solveButton").click()
    settled(qapp, window)
    assert window.plan_review.heading.text() == "Placed 1 · 1 without a time"
    assert window.rail.waiting_count.text() == "1"
    assert len(window.rail.chips()) == 1
    assert not window.rail.none_waiting.isVisible()
