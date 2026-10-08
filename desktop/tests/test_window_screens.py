"""The window's own screens and signs: a top bar that is never cut mid-word, a Next line that keeps
time, zoom keys that reach whichever hours show, a sensible kind for a block made by dragging, and
a notice with Undo for every change made on the hours."""

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
    from PySide6.QtCore import QPoint, QStandardPaths
    from PySide6.QtWidgets import QApplication, QPushButton, QStyle, QWidget

    from desktop.native.calendar import monday_of, sunday_due
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.look import sanitize_look
    from desktop.native.reuse import planner_title
    from desktop.native.window import PLAN_LABEL, PLAN_SHORT, PLAN_TINY, NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import fail_once, fixed, past_setup

PASSWORD = "a-long-test-password"
DESIGNS = ("classic", "timeline", "mission", "bento", "retro", "clay")


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-window-screens-test"])


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


class Clock:
    """Thursday 15:40 of this week, held, and moved on only by the test."""

    def __init__(self) -> None:
        monday = datetime.fromisoformat(monday_of(date.today().isoformat()))
        self.at = monday + timedelta(days=3, hours=15, minutes=40)

    def ms(self) -> int:
        return int(self.at.timestamp() * 1000)


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path, clock: Clock) -> Iterator[NativeWindow]:
    """Signed in with the clock held: school on weekdays, soccer on Tuesday and Thursday at 16:00,
    the History essay placed on Thursday at 19:00, and the Science poster waiting for a time."""
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    made.session.now_ms = clock.ms
    made.resize(1280, 860)
    made.show()
    try:
        made.username.setText("screens_student")
        made.password.setText(PASSWORD)
        made.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
        made.recovery_ack.setChecked(True)
        made.recovery_continue.click()
        past_setup(qapp, made)
        session = made.session
        session.add_block(
            {"id": "school", "title": "School", "kind": "locked", "category": "class",
             "start": "08:00", "duration_min": 390, "days": [0, 1, 2, 3, 4]}
        )
        session.add_block(
            {"id": "soccer", "title": "Soccer", "kind": "locked", "category": "exercise",
             "start": "16:00", "duration_min": 90, "days": [1, 3]}
        )
        due = sunday_due(session.week_start)
        for key, title, minutes in (("essay", "History essay", 60), ("poster", "Science poster", 90)):
            session.add_homework(
                {"id": key, "title": title, "due": due, "estimate_min": minutes, "revision": 0}
            )
        session.save()
        settled(qapp, made)
        essay = next(block for block in session.blocks if block.get("assignment_id") == "essay")
        session.add_block({**essay, "start": "19:00", "days": [3], "pinned": True})
        session.save()
        settled(qapp, made)
        yield made
    finally:
        with contextlib.suppress(RuntimeError):
            made.session.client.reset()
        made.hide()
        qapp.processEvents()
        server.stop()


BAR = (
    "prevWeek", "nextWeek", "todayWeek", "viewDay", "viewWeek", "viewMonth", "viewMyDay",
    "addButton", "addArrow", "solveButton", "retrySave", "moreButton", "settingsGear",
)


def bar_widgets(window: NativeWindow) -> list[QPushButton]:
    found = (window.findChild(QPushButton, name) for name in BAR)
    return [button for button in found if button is not None and button.isVisible()]


def text_size(window: NativeWindow, size: str) -> None:
    window._look = sanitize_look({**window._look, "knobs": {**window._look.get("knobs", {}), "text": size}})
    window._apply_appearance()


def cut_on_the_bar(window: NativeWindow) -> list[str]:
    return [
        f"{button.text()!r} {button.width()} of {QPushButton.sizeHint(button).width()} px"
        for button in bar_widgets(window)
        if button.width() < QPushButton.sizeHint(button).width()
    ]


def test_the_top_bar_is_never_cut_mid_word(qapp: QApplication, window: NativeWindow) -> None:
    """Down to the window's narrowest, in normal and large text, on Week, Day and Month: the title
    is its whole long or short form, every button on the bar is as wide as its words, and all of it
    is inside the window. At 900 pixels the bar read "21 – 2…" and "n my homew"."""
    session = window.session
    sizes = (("normal", (1280, 1100, 1000, 900, 800)), ("large", (1150, 1000, 900, 800)))
    for text, widths in sizes:
        text_size(window, text)
        for view in ("week", "day", "month"):
            window.findChild(QPushButton, f"view{view.title()}").click()
            wait_until(qapp, lambda: not session.busy)
            whole = (planner_title(session, view), planner_title(session, view, short=True))
            for width in widths:
                window.resize(width, 768)
                for _ in range(4):
                    qapp.processEvents()
                where = f"{text} text, {view}, {window.width()} px"
                title = window.week_title
                assert title.text() in whole, f"{where}: the title reads {title.text()!r}"
                room = title.contentsRect().width()
                assert title.fontMetrics().horizontalAdvance(title.text()) <= room, where
                assert window.solve_button in bar_widgets(window), where
                assert cut_on_the_bar(window) == [], f"{where}: cut {cut_on_the_bar(window)}"
                assert window.solve_button.text() in ("Plan my homework", "Plan homework", "Plan"), where
                right = max(item.mapTo(window, item.rect().topRight()).x() for item in bar_widgets(window))
                assert right < window.width(), f"{where}: the bar runs to {right}"
    # Suggest times and Retry save, which widen the bar, are never cut at the narrowest window.
    session.preferences = {**(session.preferences or {}), "planning_style": "manual"}
    window.retry_button.setVisible(True)
    window._sync_chrome()
    text_size(window, "large")
    window.resize(640, 768)
    for _ in range(4):
        qapp.processEvents()
    assert window.solve_button.text() in ("Suggest times", "Suggest")
    assert cut_on_the_bar(window) == [], f"large text, Suggest, {window.width()} px"
    session.preferences = {**session.preferences, "planning_style": "auto"}
    window.retry_button.setVisible(False)
    window._sync_chrome()
    text_size(window, "normal")
    window.resize(1150, 768)
    window.findChild(QPushButton, "viewWeek").click()
    for _ in range(4):
        qapp.processEvents()
    title_foot = window.week_title.mapTo(window, QPoint(0, window.week_title.height())).y()
    assert window.solve_button.mapTo(window, QPoint(0, 0)).y() < title_foot, "at 1150 the bar is one row"
    assert cut_on_the_bar(window) == [], "at 1150 pixels"


def test_the_bar_is_fitted_as_large_text_arrives_not_later(qapp: QApplication, window: NativeWindow) -> None:
    """The rig clicked Week where it had just been: Large text reached Plan and More after the bar was
    fitted, and the bar was fitted again only on a later change, its buttons moving under the pointer."""
    window.resize(1150, 768)
    for _ in range(4):
        qapp.processEvents()
    text_size(window, "large")
    for _ in range(4):
        qapp.processEvents()
    window._fit_plan_and_more()
    week = window.findChild(QPushButton, "viewWeek")
    seen = (window.solve_button.text(), window.more_button.text(), week.mapTo(window, QPoint(0, 0)))
    window._fit_plan_and_more()
    for _ in range(4):
        qapp.processEvents()
    assert (window.solve_button.text(), window.more_button.text(), week.mapTo(window, QPoint(0, 0))) == seen


def test_the_week_page_keeps_its_layout_margins(qapp: QApplication, window: NativeWindow) -> None:
    """0.18.1 inset the bar and planner from the window edge; zero margins on the page removed that."""
    style = QApplication.style()
    left = style.pixelMetric(QStyle.PixelMetric.PM_LayoutLeftMargin)
    top = style.pixelMetric(QStyle.PixelMetric.PM_LayoutTopMargin)
    right = style.pixelMetric(QStyle.PixelMetric.PM_LayoutRightMargin)
    bottom = style.pixelMetric(QStyle.PixelMetric.PM_LayoutBottomMargin)
    page = window._week_page.layout().contentsMargins()
    assert (page.left(), page.top(), page.right(), page.bottom()) == (left, top, right, bottom)
    assert left > 0 and right > 0


def test_at_1150_large_text_timeline_day_keeps_the_top_bar_on_one_row(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Rig day-small-large on Timeline day: a wrapped bar ate ~55 px and pushed Due chips off screen."""
    text_size(window, "large")
    window._layout = sanitize_layout({"main": "timeline", "day": "one"})
    window._day_mode = True
    window._on_week()
    window.resize(1150, 768)
    for _ in range(6):
        qapp.processEvents()
    title_foot = window.week_title.mapTo(window, QPoint(0, window.week_title.height())).y()
    assert window.solve_button.mapTo(window, QPoint(0, 0)).y() < title_foot
    assert window.more_button.text() in ("More", "")
    # Jonathan's call: "Plan", the last of #83's steps, where it keeps the bar on one row.
    assert window.solve_button.text() in (PLAN_LABEL, PLAN_SHORT, PLAN_TINY)
    assert cut_on_the_bar(window) == []


def test_retry_save_shows_only_after_a_save_fails(qapp: QApplication, window: NativeWindow) -> None:
    """A save on its way is not a failed one. Month's own fetch landing while the week saved drew
    the week with Retry save showing, and the view buttons jumped 129 pixels left under the pointer.
    A save that failed keeps Retry showing, greyed, while it is tried again."""
    session = window.session
    month = window.findChild(QPushButton, "viewMonth")
    month.click()
    wait_until(qapp, lambda: session.month_data is not None and not session.busy)
    page = window._week_page.layout()
    page.activate()
    home = month.mapTo(window, QPoint(0, 0))

    def drawn_mid_save() -> None:
        # What a reply landing during the save does: the week is drawn again.
        assert session.busy and session.pending_save is not None, "the save is no longer on its way"
        session.week_changed.emit()
        page.activate()

    session.blocks = [*session.blocks, fixed("lab", "Lab", 1, "09:00")]
    session.dirty = True
    session.save()
    drawn_mid_save()
    assert not window.retry_button.isVisible(), "Retry save showed while the save was still on its way"
    assert month.mapTo(window, QPoint(0, 0)) == home, "Month moved aside while the week saved"
    settled(qapp, window)
    assert not window.retry_button.isVisible()

    fail_once(session, "POST", "/api/changes")
    session.blocks = [*session.blocks, fixed("art", "Art", 2, "10:00")]
    session.dirty = True
    session.save()
    wait_until(qapp, lambda: not session.busy)
    assert window.retry_button.isVisible() and window.retry_button.isEnabled(), "a failed save offers Retry"
    window.retry_button.click()
    drawn_mid_save()
    assert window.retry_button.isVisible(), "Retry save went away while its own retry was on its way"
    assert not window.retry_button.isEnabled(), "Retry save was pressable while it was retrying"
    settled(qapp, window)
    assert not window.retry_button.isVisible(), "Retry save stayed after the retry saved"


def _title_switcher_gap(window: NativeWindow) -> int:
    segments = window.findChild(QWidget, "segments")
    assert segments is not None
    title_right = window.week_title.mapTo(window, window.week_title.rect().topRight()).x()
    switcher_left = segments.mapTo(window, QPoint(0, 0)).x()
    return switcher_left - title_right


@pytest.mark.parametrize(
    ("width", "text", "preset"),
    [
        (1157, "normal", "default"),
        (1157, "large", "default"),
        (1280, "normal", "default"),
        (1280, "large", "default"),
        (1157, "normal", "high-contrast"),
    ],
)
def test_the_title_keeps_sixteen_pixels_from_the_view_switcher(
    qapp: QApplication, window: NativeWindow, width: int, text: str, preset: str
) -> None:
    """#84: the date stays 16 px from Day/Week/Month even where that shortens Plan at 1157 px Large."""
    window._look = sanitize_look({"preset": preset, "knobs": {"text": text}})
    window._apply_appearance()
    window.findChild(QPushButton, "viewWeek").click()
    window.resize(width, 768)
    for _ in range(6):
        qapp.processEvents()
    window._fit_plan_and_more()
    for _ in range(4):
        qapp.processEvents()
    gap = _title_switcher_gap(window)
    assert 15 <= gap <= 17, (width, text, preset, gap)
