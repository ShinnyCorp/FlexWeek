"""Ctrl+K: type a few letters, press Enter, and it is done or open."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QStandardPaths, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from desktop.native.calendar import sunday_due
from desktop.native.command_bar import BAR_WIDTH, KEY_ROLE, KEYS_ROLE, Command, grouped, match_rank, ranked
from desktop.native.settings import HELP_KEYS
from desktop.native.widgets import HomeworkDialog
from desktop.native.window import NativeWindow
from desktop.server import LocalServer
from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"
CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-command-bar-test"])


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
    """Today's app's Week with a History essay and a Math worksheet, neither with a time yet."""
    look_file().unlink(missing_ok=True)
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    made.resize(1280, 860)
    made.show()
    try:
        made.username.setText("command_bar_student")
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
        for key, title in (("essay", "History essay"), ("math", "Math worksheet")):
            session.add_homework({"id": key, "title": title, "due": due, "estimate_min": 60, "revision": 0})
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


def open_bar(window: NativeWindow) -> None:
    QTest.keyClick(window.week_table.hours, Qt.Key.Key_K, CTRL)
    assert window.command_bar.isVisible()


def test_typing_filters_by_letters_in_order_then_by_first_letters() -> None:
    commands = [Command(key, words) for key, words in (
        ("a", "Add homework"), ("m", "Month"), ("p", "Plan my homework"), ("math", "Math worksheet"),
    )]
    assert [command.key for command in ranked("", commands)] == ["a", "m", "p", "math"]
    assert [command.key for command in ranked("ma", commands)] == ["math"]
    assert [command.key for command in ranked("mo", commands)] == ["m"]
    assert [command.key for command in ranked("home", commands)] == ["a", "p"]
    assert [command.key for command in ranked("pmh", commands)] == ["p"]
    assert [command.key for command in ranked("orks", commands)] == ["math"]
    assert match_rank("zz", "Math worksheet") is None


def test_ctrl_k_opens_a_centred_box_listing_what_can_be_done(
    qapp: QApplication, window: NativeWindow
) -> None:
    open_bar(window)
    bar = window.command_bar
    assert window.focusWidget() is bar.input, "typing goes straight into the box"
    box = bar.box.geometry()
    assert box.width() == BAR_WIDTH
    assert abs(box.center().x() - window.width() // 2) <= 1
    assert box.top() < window.height() / 3, "the box sits in the top third"
    assert bar.shown_groups() == ["Add", "Go to", "Settings", "Homework"]
    assert bar.shown_words() == [
        "Add homework", "Add fixed time", "School hours",
        "Day", "Week", "Month", "My day", "Focus screen", "Settings", "Help",
        "Look and colours", "Customise look…", "Planning settings", "Focus settings", "Alerts",
        "This computer",
        "Plan my homework", "History essay", "Math worksheet",
    ]
    QTest.keyClick(bar.input, Qt.Key.Key_Escape)
    assert bar.isVisible() is False


def test_ma_then_enter_opens_math_worksheet(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []

    def look(dialog: HomeworkDialog) -> int:
        opened.append(dialog.title.text())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(HomeworkDialog, "exec", look)
    open_bar(window)
    bar = window.command_bar
    QTest.keyClicks(bar.input, "ma")
    assert bar.shown_words() == ["Math worksheet"]
    QTest.keyClick(bar.input, Qt.Key.Key_Return)
    assert opened == ["Math worksheet"]
    assert bar.isVisible() is False


def test_arrows_choose_and_enter_runs_what_is_chosen(qapp: QApplication, window: NativeWindow) -> None:
    open_bar(window)
    bar = window.command_bar
    QTest.keyClicks(bar.input, "d")
    assert bar.shown_words()[:2] == ["Day", "My day"]
    QTest.keyClick(bar.input, Qt.Key.Key_Down)
    QTest.keyClick(bar.input, Qt.Key.Key_Return)
    assert window._day_mode is True, "My day, the second row, ran"

    open_bar(window)
    QTest.keyClicks(bar.input, "mon")
    QTest.keyClick(bar.input, Qt.Key.Key_Up)
    QTest.keyClick(bar.input, Qt.Key.Key_Return)
    wait_until(qapp, lambda: window.session.planner_view == "month" and not window.session.busy)
    assert window._day_mode is False
    assert window.planner.currentWidget() is window.month_grid


def test_a_click_outside_the_box_closes_it_and_nothing_matching_runs_nothing(
    qapp: QApplication, window: NativeWindow
) -> None:
    open_bar(window)
    bar = window.command_bar
    QTest.keyClicks(bar.input, "xyzzy")
    assert bar.shown_words() == []
    assert bar.nothing.isVisible()
    QTest.keyClick(bar.input, Qt.Key.Key_Return)
    assert bar.isVisible(), "Enter with nothing to run keeps the box"
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(10, window.height() - 10))
    assert bar.isVisible() is False
    assert window.session.planner_view == "week"


def test_a_click_on_a_row_runs_it(qapp: QApplication, window: NativeWindow) -> None:
    open_bar(window)
    bar = window.command_bar
    QTest.keyClicks(bar.input, "focus scr")
    assert bar.shown_words() == ["Focus screen"]
    rows = [bar.list.item(row) for row in range(bar.list.count())]
    focus = next(item for item in rows if item.text() == "Focus screen")
    row = bar.list.visualItemRect(focus).center()
    QTest.mouseClick(bar.list.viewport(), Qt.MouseButton.LeftButton, pos=row)
    assert window._stack.currentWidget() is window.focus_screen


def test_plan_says_suggest_times_for_a_student_who_plans_by_hand(
    qapp: QApplication, window: NativeWindow
) -> None:
    window.session.preferences = {**(window.session.preferences or {}), "planning_style": "manual"}
    open_bar(window)
    assert "Suggest times" in window.command_bar.shown_words()
    assert "Plan my homework" not in window.command_bar.shown_words()


def test_help_lists_both_keys() -> None:
    assert ("[Ctrl]+[K]", "Command bar") in HELP_KEYS
    assert ("[F]", "Focus screen") in HELP_KEYS


def test_the_group_with_the_best_match_comes_first_so_enter_runs_it() -> None:
    commands = [
        Command("school", "School hours", group="Add"),
        Command("chem", "Chem lab report", group="Homework"),
        Command("month", "Month", group="Go to"),
    ]
    assert [group for group, _rows in grouped("", commands)] == ["Add", "Go to", "Homework"]
    found = grouped("ch", commands)
    assert [(group, [row.key for row in rows]) for group, rows in found] == [
        ("Homework", ["chem"]),
        ("Add", ["school"]),
    ], "Chem starts with ch; School only holds it"


def test_every_row_has_an_icon_and_the_views_their_keys(qapp: QApplication, window: NativeWindow) -> None:
    open_bar(window)
    bar = window.command_bar
    rows = [bar.list.item(row) for row in range(bar.list.count())]
    commands = [item for item in rows if item.data(KEY_ROLE)]
    labels = [item for item in rows if not item.data(KEY_ROLE)]
    assert all(not item.icon().isNull() for item in commands)
    assert all(item.flags() == Qt.ItemFlag.NoItemFlags for item in labels), "a label cannot be chosen"
    keys = {item.text(): item.data(KEYS_ROLE) for item in commands if item.data(KEYS_ROLE)}
    assert keys == {"Day": "D", "Week": "W", "Month": "M", "My day": "T", "Focus screen": "F"}
    assert bar.list.currentItem().text() == "Add homework", "the first command, not the label over it"
    QTest.keyClick(bar.input, Qt.Key.Key_Up)
    assert bar.list.currentItem().text() == "Math worksheet", "Up from the top goes round, past the label"
    for _ in range(2):
        QTest.keyClick(bar.input, Qt.Key.Key_Down)
    assert bar.list.currentItem().text() == "Add fixed time", "Down steps over the Add label"
    QTest.keyClick(bar.input, Qt.Key.Key_Down)
    QTest.keyClick(bar.input, Qt.Key.Key_Down)
    assert bar.list.currentItem().text() == "Day", "and over the Go to label"


def test_the_box_rises_8_pixels_into_place_as_the_window_dims(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Decision 31 of 0.17: Ctrl+K fades and rises; under Reduce it only fades."""
    for level, rise in (("normal", 8), ("reduce", 0)):
        window.session.preferences = {**(window.session.preferences or {}), "motion": level}
        window._apply_appearance()
        open_bar(window)
        bar = window.command_bar
        first = bar.box.y()
        assert bar.graphicsEffect() is not None, "the dimmed window fades in"
        wait_until(qapp, lambda bar=bar: bar.graphicsEffect() is None)
        QTest.qWait(100)
        assert first - bar.box.y() == rise, level
        bar.close_bar()


def test_the_window_is_dimmed_40_percent_and_the_box_is_lifted_with_the_large_shadow(
    qapp: QApplication, window: NativeWindow
) -> None:
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    from desktop.native.tokens import SHADOW_LARGE

    open_bar(window)
    bar = window.command_bar
    assert "QWidget#commandBar { background: rgba(0, 0, 0, 102); }" in window.styleSheet()
    shadow = bar.box.graphicsEffect()
    assert isinstance(shadow, QGraphicsDropShadowEffect)
    assert (shadow.offset().y(), shadow.blurRadius()) == (SHADOW_LARGE.y, SHADOW_LARGE.blur)
    # It fades in with the level's fade, and nothing is left on it once it has.
    assert bar.graphicsEffect() is not None
    wait_until(qapp, lambda: bar.graphicsEffect() is None)
    assert bar.box.graphicsEffect() is shadow, "the fade leaves the box's shadow alone"


def test_look_finds_the_look_and_opens_settings_where_it_is(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Grok Bot's 0.17.0 audit (X1): "look" found nothing in Ctrl+K."""
    open_bar(window)
    bar = window.command_bar
    QTest.keyClicks(bar.input, "look")
    assert bar.shown_words()[:2] == ["Look and colours", "Customise look…"]
    QTest.keyClick(bar.input, Qt.Key.Key_Return)
    settings = window._settings
    assert settings is not None and window._stack.currentWidget() is settings
    assert settings.nav.currentRow() == 0, "Appearance, where Colours comes first"
    settings.close_page()
    open_bar(window)
    QTest.keyClicks(bar.input, "alerts")
    QTest.keyClick(bar.input, Qt.Key.Key_Return)
    assert window._settings.nav.currentRow() == 3
    window._settings.close_page()
