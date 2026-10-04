"""0.18.2 batch A lane 4: F1 Help, Ctrl+N add homework, and Ctrl+K polish (#88, #89)."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from desktop.native.calendar import sunday_due
from desktop.native.command_bar import KEY_ROLE, match_span
from desktop.native.settings import CUSTOMISE, HELP_KEYS, HelpDialog
from desktop.native.widgets import HomeworkDialog
from desktop.native.window import NativeWindow
from desktop.server import LocalServer
from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"
CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-keys-0182"])


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def look_file() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(root) / "flexweek-look.json"


def settled(qapp: QApplication, window: NativeWindow) -> None:
    session = window.session
    wait_until(
        qapp, lambda: not session.busy and not session.dirty and not any(session.client._replies.values())
    )


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path) -> Iterator[NativeWindow]:
    look_file().unlink(missing_ok=True)
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    made.resize(1280, 860)
    made.show()
    try:
        made.username.setText("keys0182_student")
        made.password.setText(PASSWORD)
        made.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
        made.recovery_ack.setChecked(True)
        made.recovery_continue.click()
        past_setup(qapp, made)
        session = made.session
        thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=10)
        session.now_ms = lambda: int(thursday.timestamp() * 1000)
        due = sunday_due(session.week_start)
        session.add_homework(
            {"id": "essay", "title": "History essay", "due": due, "estimate_min": 60, "revision": 0}
        )
        session.save()
        settled(qapp, made)
        made.findChild(QPushButton, "viewWeek").click()
        settled(qapp, made)
        made.week_table.hours.setFocus()
        yield made
    finally:
        with contextlib.suppress(RuntimeError):
            made.session.client.reset()
        made.hide()
        qapp.processEvents()
        server.stop()
        look_file().unlink(missing_ok=True)


def test_f1_opens_help_from_the_week(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []

    def show_help(dialog: HelpDialog) -> int:
        opened.append(dialog.windowTitle())
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(HelpDialog, "exec", show_help)
    QTest.keyClick(window.week_table.hours, Qt.Key.Key_F1)
    assert opened == ["Help"]


def test_ctrl_n_opens_add_homework_from_the_week(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []

    def look(dialog: HomeworkDialog) -> int:
        opened.append(dialog.title.text())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(HomeworkDialog, "exec", look)
    QTest.keyClick(window.week_table.hours, Qt.Key.Key_N, CTRL)
    assert opened == [""]


def test_help_and_ctrl_k_list_f1_and_ctrl_n() -> None:
    assert ("[F1]", "Help") in HELP_KEYS
    assert ("[Ctrl]+[N]", "Add homework") in HELP_KEYS


def test_ctrl_k_lists_help_add_homework_choose_time_and_settings_pages(
    qapp: QApplication, window: NativeWindow
) -> None:
    QTest.keyClick(window.week_table.hours, Qt.Key.Key_K, CTRL)
    bar = window.command_bar
    words = bar.shown_words()
    assert "Help" in words
    assert "Add homework" in words
    assert "Choose a time…" in words
    assert "Alerts" in words
    assert "This computer" in words
    assert f"{CUSTOMISE}…" in words
    assert "Customise look…" not in words
    bar.close_bar()


def test_choose_finds_choose_a_time(qapp: QApplication, window: NativeWindow) -> None:
    QTest.keyClick(window.week_table.hours, Qt.Key.Key_K, CTRL)
    bar = window.command_bar
    QTest.keyClicks(bar.input, "choose")
    assert bar.shown_words() == ["Choose a time…"]
    bar.close_bar()


def test_typed_letters_are_highlighted_in_the_row(qapp: QApplication, window: NativeWindow) -> None:
    assert match_span("ma", "Math worksheet") == (0, 2)
    QTest.keyClick(window.week_table.hours, Qt.Key.Key_K, CTRL)
    bar = window.command_bar
    QTest.keyClicks(bar.input, "hist")
    item = next(
        bar.list.item(row)
        for row in range(bar.list.count())
        if bar.list.item(row).text() == "History essay"
    )
    rect = bar.list.visualItemRect(item)
    picture = bar.list.viewport().grab().toImage()
    from desktop.native.look import resolved_palette

    palette = resolved_palette(*window._look_inputs()[:2], window._look, window._look_inputs()[2])
    accent = QColor(palette["accent"])
    plain = QColor(palette["text"])
    mid = rect.center().y()
    highlighted = picture.pixelColor(rect.left() + 40, mid)

    def distance(left: QColor, right: QColor) -> int:
        return (
            abs(left.red() - right.red())
            + abs(left.green() - right.green())
            + abs(left.blue() - right.blue())
        )

    assert distance(highlighted, accent) < distance(highlighted, plain)
    bar.close_bar()


def test_hover_is_lighter_than_the_enter_row(qapp: QApplication, window: NativeWindow) -> None:
    from desktop.native.look import mix, resolved_palette

    QTest.keyClick(window.week_table.hours, Qt.Key.Key_K, CTRL)
    bar = window.command_bar
    palette = resolved_palette(*window._look_inputs()[:2], window._look, window._look_inputs()[2])
    selected = QColor(mix(palette["accent"], palette["panel"], 0.14))
    hover = QColor(mix(palette["accent"], palette["panel"], 0.06))
    assert abs(hover.red() - selected.red()) + abs(hover.green() - selected.green()) > 8
    qapp.processEvents()
    chosen = bar.list.visualItemRect(bar.list.currentItem())
    items = [bar.list.item(row) for row in range(bar.list.count()) if bar.list.item(row).data(KEY_ROLE)]
    other = next(item for item in items if item.text() == "Week")
    hover_rect = bar.list.visualItemRect(other)
    QTest.mouseMove(bar.list.viewport(), hover_rect.center())
    qapp.processEvents()
    picture = bar.list.viewport().grab().toImage()
    enter_colour = picture.pixelColor(chosen.left() + 48, chosen.center().y())
    hover_colour = picture.pixelColor(hover_rect.left() + 48, hover_rect.center().y())
    def distance(left: QColor, right: QColor) -> int:
        return (
            abs(left.red() - right.red())
            + abs(left.green() - right.green())
            + abs(left.blue() - right.blue())
        )

    assert distance(enter_colour, selected) <= distance(enter_colour, hover)
    assert distance(hover_colour, hover) < distance(hover_colour, selected)
    bar.close_bar()


def test_the_command_box_stays_inside_the_window(qapp: QApplication, window: NativeWindow) -> None:
    window.resize(1280, 860)
    qapp.processEvents()
    QTest.keyClick(window.week_table.hours, Qt.Key.Key_K, CTRL)
    bar = window.command_bar
    qapp.processEvents()
    box = bar.box.geometry()
    assert box.bottom() <= window.height()
    assert box.top() >= 0
    bar.close_bar()
