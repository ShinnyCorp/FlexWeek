"""The native window driven the way a student drives it, against a real local API.

Dialogs are modal, so a test scripts what the student does inside exec() and lets the window's own
slot read the result. Expected behaviour comes from the web client, the reference implementation.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QStandardPaths, Qt, QTime
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

    from desktop.native.widgets import BlockDialog
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    # The window reads flexweek-look.json from the user data folder. Test mode points Qt at a scratch
    # location, so these tests neither read nor write the look saved on this machine.
    QStandardPaths.setTestModeEnabled(True)
    application = QApplication.instance() or QApplication(["flexweek-window-test"])
    yield application


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def settled(qapp: QApplication, window: NativeWindow) -> None:
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)


def on_page(window: NativeWindow, name: str) -> bool:
    return window._stack.currentWidget().objectName() == name


@pytest.fixture()
def registering(qapp: QApplication, tmp_path: Path) -> Iterator[NativeWindow]:
    """A window that has just created an account and is showing the recovery codes."""
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    window = NativeWindow(server.origin)
    window.show()
    try:
        window.username.setText("ui_student")
        window.password.setText(PASSWORD)
        window.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: on_page(window, "recoveryPage"))
        yield window
    finally:
        with contextlib.suppress(RuntimeError):
            window.session.client.reset()
        window.hide()
        qapp.processEvents()
        server.stop()


@pytest.fixture()
def window(qapp: QApplication, registering: NativeWindow) -> NativeWindow:
    """Signed in, on the week page, with preferences loaded."""
    registering.recovery_ack.setChecked(True)
    registering.recovery_continue.click()
    past_setup(qapp, registering)
    wait_until(qapp, lambda: registering.session.preferences is not None)
    return registering


def school() -> dict:
    return {
        "id": "school",
        "title": "School",
        "kind": "locked",
        "category": "class",
        "start": "08:00",
        "duration_min": 390,
        "days": [0, 1, 2, 3, 4],
    }


def saved(qapp: QApplication, window: NativeWindow, *blocks: dict) -> None:
    for block in blocks:
        window.session.add_block(block)
    window.session.save()
    settled(qapp, window)


def student(dialog: QDialog, monkeypatch: pytest.MonkeyPatch, steps: Callable[[], None]) -> None:
    """Stand in for the student while the dialog is open, then return as exec() would."""

    def run() -> int:
        dialog.show()
        steps()
        return dialog.result()

    monkeypatch.setattr(dialog, "exec", run, raising=False)


def test_this_day_only_plus_missed_marks_that_one_day_and_saves(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "This day only" gives Wednesday a new id. The replan was asked for the old id and did nothing,
    and the window returned before saving, so the split stayed an unsaved draft."""
    saved(qapp, window, school())
    dialog = BlockDialog(window, window.session.blocks[0], occurrence_day=2)

    def steps() -> None:
        dialog.scope_occurrence.setChecked(True)
        dialog.missed.setChecked(True)
        dialog.accept()

    student(dialog, monkeypatch, steps)
    window._commit_block(dialog)
    settled(qapp, window)
    by_days = {tuple(block["days"]): block for block in window.session.blocks}
    assert sorted(by_days) == [(0, 1, 3, 4), (2,)]
    # The API leaves missed_days out of a block that has none.
    assert by_days[(2,)].get("missed_days") == [2]
    assert by_days[(0, 1, 3, 4)].get("missed_days") is None
    assert window.session.revision == 2, "the split and the missed day reached the server"


def soccer() -> dict:
    return {
        "id": "soccer",
        "title": "Soccer",
        "kind": "locked",
        "start": "07:00",
        "duration_min": 60,
        "days": [0],
    }


def test_the_block_editor_saves_any_minute_and_shows_it_back(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """18:37 to 19:22 was taken by the editor and refused by the server after Save."""
    saved(qapp, window, soccer())
    dialog = BlockDialog(window, soccer())

    def steps() -> None:
        dialog.start.setTime(QTime(18, 37))
        dialog.end.setTime(QTime(19, 22))
        dialog.accept()

    student(dialog, monkeypatch, steps)
    window._commit_block(dialog)
    settled(qapp, window)
    window.session.load_week(window.session.week_start, discard=True)
    settled(qapp, window)
    stored = next(block for block in window.session.blocks if block["id"] == "soccer")
    assert (stored["start"], stored["duration_min"]) == ("18:37", 45)
    again = BlockDialog(window, stored)
    assert (again.start.time().toString("HH:mm"), again.end.time().toString("HH:mm")) == ("18:37", "19:22")
    assert again.duration_line.text() == "45 min"


def test_w_d_and_m_switch_views_while_the_calendar_has_the_keyboard(
    qapp: QApplication, window: NativeWindow
) -> None:
    """A click in the calendar gives it the keyboard, and Qt sends keys to the widget that has it.

    Item views keep letter keys for their own type-ahead search, so W, D and M never reached the
    window. The older test sends the key straight to the window, which no student can do.
    """
    session = window.session
    QTest.keyClick(window.week_table.hours, Qt.Key.Key_D)
    wait_until(qapp, lambda: session.planner_view == "day" and not session.busy)
    QTest.keyClick(window.day_view.hours, Qt.Key.Key_M)
    wait_until(qapp, lambda: session.planner_view == "month" and not session.busy)
    QTest.keyClick(window.month_grid.canvas, Qt.Key.Key_W)
    wait_until(qapp, lambda: session.planner_view == "week" and not session.busy)
    QTest.keyClick(window.rail.tasks, Qt.Key.Key_M)
    wait_until(qapp, lambda: session.planner_view == "month" and not session.busy)


def test_ctrl_c_in_the_week_grid_copies_the_block_and_leaves_the_os_clipboard_alone(
    qapp: QApplication, window: NativeWindow
) -> None:
    """docs/native-python-migration.md: "Ctrl/C/V/D never touch the OS clipboard"."""
    saved(qapp, window, soccer())
    window.session.select_block("soccer", 0)
    QGuiApplication.clipboard().setText("the student's own text")
    # Pressed on the week itself, where a block was just clicked: the window's copy, not the system's.
    window.week_table.hours.setFocus()
    QTest.keyClick(window.week_table.hours, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QGuiApplication.clipboard().text() == "the student's own text"
    assert (window.session.clipboard or {}).get("kind") == "block"
    assert "Soccer" in window.session.clipboard["label"]


def test_creating_an_account_shows_password_length_before_submit(qapp: QApplication, tmp_path: Path) -> None:
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    window = NativeWindow(server.origin)
    window.show()
    try:
        window.findChild(QPushButton, "authSwitch").click()
        qapp.processEvents()
        hint = window.findChild(QLabel, "passwordHint")
        assert hint is not None and hint.isVisible()
        assert "12" in hint.text()
        window.username.setText("newbie")
        window.password.setText("short")
        window.findChild(QPushButton, "createAccount").click()
        qapp.processEvents()
        assert window.session.account is None
        assert "12" in window.auth_status.text()
        assert "password" in window.auth_status.text().lower()
    finally:
        with contextlib.suppress(RuntimeError):
            window.session.client.reset()
        window.hide()
        qapp.processEvents()
        server.stop()
