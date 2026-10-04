"""0.18.2 batch A lane 2: week behaviour (#15–#18, #20, #82, #83)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QWidget
from shiboken6 import isValid

from desktop.native import window as window_module
from desktop.native.calendar import monday_of, sunday_due
from desktop.native.layouts.base import NARROW_WIDTH
from desktop.native.layouts.empty import EMPTY_COPY_LAST, EMPTY_USE_ROUTINE
from desktop.native.menus import Menu
from desktop.native.widgets import ConfirmSheet, PreviewDialog, RoutineDialog
from desktop.native.window import PLAN_LABEL, PLAN_SHORT, NativeWindow
from desktop.tests import window_support as window_support_mod
from desktop.tests.window_support import (  # noqa: F401
    free,
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401

PAST_REFUSAL = "That's in the past."


def send_mouse(widget, kind, at: QPoint, held: bool) -> None:
    local = QPointF(widget.mapFromGlobal(at))
    buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
    event = QMouseEvent(
        kind, local, QPointF(at), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(widget, event)


@pytest.fixture()
def window(qapp: QApplication, signed_in: NativeWindow) -> Iterator[NativeWindow]:  # noqa: F811
    session = signed_in.session
    signed_in.resize(1280, 860)
    signed_in._layout = {"main": "classic", "day": "one", "options": {}}
    due = sunday_due(session.week_start)
    session.add_homework(
        {"id": "math", "title": "Math worksheet", "due": due, "estimate_min": 45, "revision": 0}
    )
    block = next(b for b in session.blocks if b.get("assignment_id") == "math")
    session.place_session(block["id"], 2, 17 * 60)
    session.save()
    settled(qapp, signed_in)
    signed_in.findChild(QPushButton, "viewWeek").click()
    settled(qapp, signed_in)
    yield signed_in


def essay_on_past_day(window: NativeWindow) -> None:
    """Clock on Thursday; essay sits Wednesday so dragging it to Monday is in the past."""
    session = window.session
    thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=12)
    session.now_ms = lambda: int(thursday.timestamp() * 1000)
    session.save()
    settled(QApplication.instance(), window)


def test_a_drop_on_a_past_day_is_refused_and_says_why(
    qapp: QApplication, window: NativeWindow  # noqa: F811
) -> None:
    essay_on_past_day(window)
    essay = next(b for b in window.session.blocks if b.get("assignment_id") == "math")
    before = [dict(b) for b in window.session.blocks]
    # Wednesday → Monday: a different day already past. Synthetic moves never leave the origin
    # column (Hand asks widgetAt), so the judge is the drop rule the window uses on release.
    verdict = window._judge_span(essay["id"], 2, 0, 17 * 60, 17 * 60 + 45)
    assert (verdict.ok, verdict.words) == (False, PAST_REFUSAL)
    window._move_block(essay["id"], 2, 0, 17 * 60, 17 * 60 + 45)
    assert window.session.blocks == before
    assert essay["days"] == [2]


def test_moving_one_day_of_a_series_on_a_past_day_still_splits(
    qapp: QApplication, window: NativeWindow  # noqa: F811
) -> None:
    """A drop onto a different past day is refused. Changing Wednesday's School time, with the clock
    on Thursday, still splits that day's occurrence — the week-series-one-day gesture."""
    from PySide6.QtCore import QEvent

    essay_on_past_day(window)
    session = window.session
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
    session.save()
    settled(qapp, window)
    hours = window.week_table.hours
    hours.reveal(2, 8 * 60, 11 * 60)
    start = hours.point_for(2, 9 * 60)
    end = hours.point_for(2, 10 * 60)
    send_mouse(hours, QEvent.Type.MouseButtonPress, start, True)
    for step in range(1, 9):
        send_mouse(hours, QEvent.Type.MouseMove, start + (end - start) * step / 8, True)
    send_mouse(hours, QEvent.Type.MouseButtonRelease, end, False)
    settled(qapp, window)
    school = sorted((tuple(b["days"]), b["start"]) for b in session.blocks if b["title"] == "School")
    assert school == [((0, 1, 3, 4), "08:00"), ((2,), "09:00")]


def test_an_empty_next_week_offers_copy_last_week_and_use_a_routine(
    qapp: QApplication, signed_in: NativeWindow  # noqa: F811
) -> None:
    session = signed_in.session
    signed_in._layout = {"main": "classic", "day": "one", "options": {}}
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
    session.save()
    settled(qapp, signed_in)
    signed_in.findChild(QPushButton, "nextWeek").click()
    wait_until(qapp, lambda: not session.busy)
    settled(qapp, signed_in)
    assert session.blocks == []
    assert signed_in.planner.currentWidget() is signed_in.week_table
    card = signed_in.empty_week
    assert card.isVisible()
    buttons = [b.text() for b in card.findChildren(QPushButton) if b.isVisible()]
    assert EMPTY_COPY_LAST in buttons and EMPTY_USE_ROUTINE in buttons


def test_routines_with_none_saved_says_so(qapp: QApplication) -> None:  # noqa: F811
    dialog = RoutineDialog(None, {}, [], "2026-09-21")
    dialog.show()
    qapp.processEvents()
    empty = dialog.findChild(type(dialog.empty), "routineEmpty")
    assert empty.text() == "No routines saved yet." and empty.isVisible()
    assert not dialog.list.isVisible()
    dialog.close()
    dialog.deleteLater()
    qapp.processEvents()


def test_unfinished_collapses_to_a_badge_after_the_first_showing(
    qapp: QApplication, signed_in: NativeWindow  # noqa: F811
) -> None:
    session = signed_in.session
    current = session.week_start
    previous = (date.fromisoformat(current) - timedelta(days=7)).isoformat()
    session.load_week(previous)
    wait_until(qapp, lambda: session.week_start == previous and not session.busy)
    session.add_homework(
        {
            "id": "late",
            "title": "Late essay",
            "due": previous + "T21:00",
            "estimate_min": 60,
            "revision": 0,
        }
    )
    session.save()
    wait_until(qapp, lambda: not session.busy)
    session.load_week(current)
    wait_until(qapp, lambda: session.week_start == current and not session.busy)
    settled(qapp, signed_in)
    items = session.unfinished()
    assert items
    panel = signed_in.unfinished_panel
    badge = signed_in.findChild(QPushButton, "unfinishedBadge")
    assert badge is not None
    panel.set_items(items)
    assert panel.isVisible()
    panel.findChild(QPushButton, "unfinishedDismiss").click()
    qapp.processEvents()
    assert not panel.isVisible() and badge.isVisible()
    badge.click()
    qapp.processEvents()
    assert panel.isVisible()


def test_a_running_timer_in_todays_app_is_one_line_in_the_rail(
    qapp: QApplication, window: NativeWindow  # noqa: F811
) -> None:
    essay = next(b for b in window.session.blocks if b.get("assignment_id") == "math")
    window.session.start_focus(essay["id"], 2)
    wait_until(qapp, lambda: window.session.focus is not None)
    window._on_week()
    qapp.processEvents()
    panel = window.focus_panel
    assert panel.isVisible() and window.rail.isAncestorOf(panel)
    assert panel.task.isVisible()
    assert not panel.phase.isVisible() and not panel.time.isVisible()
    line = panel.task.text()
    assert line.startswith("Session · ") and " left" in line
    assert [b.text() for b in panel.findChildren(QPushButton) if b.isVisible()] == ["Focus screen"]


@pytest.fixture()
def menus(monkeypatch: pytest.MonkeyPatch) -> dict:
    seen: dict = {"widths": [], "rows": []}

    class Shown(Menu):
        def exec(self, at: QPoint | None = None, *_rest: object) -> object:
            seen["widths"].append(self.minimumWidth())
            seen["rows"].append([a.text() or "---" for a in self.actions()])
            return None

    monkeypatch.setattr(window_module, "Menu", Shown)
    return seen


def test_the_block_menu_matches_free_time_and_includes_copy(
    qapp: QApplication, window: NativeWindow, menus: dict  # noqa: F811
) -> None:
    hours = window.week_table.hours
    essay = next(b for b in window.session.blocks if b.get("assignment_id") == "math")
    box = hours.block_rect(essay["id"], 2)
    assert box is not None
    window._block_menu(essay["id"], 2, box.center())
    hours.hand.step = 15
    hours.reveal(1, 17 * 60, 17 * 60 + 30)
    qapp.processEvents()
    window._spot_menu(1, 17 * 60, hours.point_for(1, 17 * 60))
    assert len(menus["widths"]) == 2 and menus["widths"][0] == menus["widths"][1]
    block_rows = menus["rows"][0]
    assert "Copy\tCtrl+C" in block_rows
    assert "Delete homework" not in block_rows
    assert sum("Delete" in r for r in block_rows) == 1


def test_the_folded_rail_shows_a_waiting_chip_not_a_bare_line(
    qapp: QApplication, window: NativeWindow  # noqa: F811
) -> None:
    due = sunday_due(window.session.week_start)
    window.session.add_homework(
        {"id": "poster", "title": "Poster", "due": due, "estimate_min": 30, "revision": 0}
    )
    window.session.save()
    settled(qapp, window)
    window.resize(NARROW_WIDTH - 1, 860)
    for _ in range(5):
        qapp.processEvents()
    rail = window.rail
    assert rail.folded
    chip = rail.findChild(QPushButton, "railWaitingChip")
    assert chip is not None and chip.isVisible()
    words = chip.findChild(QLabel, "railWaitingWords")
    assert words is not None and "Not placed yet" in words.text()
    assert "Not placed yet:" not in rail.line.text()


def test_plan_keeps_its_words_then_more_then_drops_my(
    qapp: QApplication, signed_in: NativeWindow  # noqa: F811
) -> None:
    from desktop.native.look import sanitize_look

    signed_in._look = sanitize_look({"preset": "default", "knobs": {"text": "large"}})
    signed_in._apply_appearance()
    signed_in._sync_chrome()
    for width in (1280, 1100, 1000, 900, 800):
        signed_in.resize(width, 800)
        for _ in range(4):
            qapp.processEvents()
        plan = signed_in.solve_button.text()
        more = signed_in.more_button.text()
        assert plan in (PLAN_LABEL, PLAN_SHORT), (width, plan)
        assert more in ("More", ""), (width, more)
        if plan != PLAN_LABEL:
            assert PLAN_SHORT == "Plan homework", PLAN_SHORT
            assert more == "", "More should be icon-only before Plan shortens"


def test_plan_follows_one_shortening_rule_at_every_width_and_text_size(
    qapp: QApplication, signed_in: NativeWindow  # noqa: F811
) -> None:
    from desktop.native.look import sanitize_look

    for size in ("normal", "large"):
        signed_in._look = sanitize_look({"preset": "default", "knobs": {"text": size}})
        signed_in._apply_appearance()
        signed_in._sync_chrome()
        for width in (810, 900, 1100, 1400):
            signed_in.solve_button.setMaximumWidth(16777215)
            signed_in.resize(width, 800)
            for _ in range(6):
                qapp.processEvents()
            plan = signed_in.solve_button
            more = signed_in.more_button
            assert plan.text() in (PLAN_LABEL, PLAN_SHORT), (size, width, plan.text())
            assert more.text() in ("More", ""), (size, width, more.text())
            if plan.text() == PLAN_SHORT:
                assert more.text() == ""
            room = max(0, plan.contentsRect().width() - plan.iconSize().width() - 16)
            ink = plan.fontMetrics().horizontalAdvance(plan.text())
            assert ink <= max(room, plan.width()), (size, width, plan.text(), ink, room)
        signed_in.resize(1100, 800)
        for _ in range(4):
            qapp.processEvents()
        plan = signed_in.solve_button
        plan.setMaximumWidth(plan._wide(PLAN_SHORT) + 20)
        signed_in._fit_plan_and_more()
        qapp.processEvents()
        assert plan.text() == PLAN_SHORT, (size, plan.text(), plan.width())
        plan.setMaximumWidth(16777215)


LAST_WEEK_FIXED = {
    "id": "soccer",
    "kind": "locked",
    "title": "Soccer",
    "category": "sport",
    "start": "16:00",
    "duration_min": 90,
    "days": [2],
}


def test_copying_last_weeks_fixed_times_does_not_park_it_as_unsaved(
    qapp: QApplication, signed_in: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """Last week is fetched for the copy sheet, then opened again as saved work."""
    window = signed_in
    window._layout = {"main": "classic", "day": "one", "options": {}}
    session = window.session
    session.add_block(dict(LAST_WEEK_FIXED))
    session.save()
    wait_until(qapp, lambda: not session.busy)
    source = session.week_start
    window.findChild(QPushButton, "nextWeek").click()
    wait_until(qapp, lambda: session.week_start != source and not session.busy)
    settled(qapp, window)
    previous = monday_of((date.fromisoformat(session.week_start) - timedelta(days=7)).isoformat())
    assert previous == source
    assert previous not in session._drafts
    shown: list[bool] = []

    def skip(dialog: PreviewDialog) -> int:
        shown.append(True)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(PreviewDialog, "exec", skip)
    window._copy_last_week_fixed()
    wait_until(qapp, lambda: not session.busy and shown)
    assert previous not in session._drafts
    assert previous not in session.unsaved_weeks()
    session.load_week(previous)
    wait_until(qapp, lambda: session.week_start == previous and not session.busy)
    assert "Soccer" in [block["title"] for block in session.blocks]
    assert previous not in session.unsaved_weeks()


def two_essay_sessions(window: NativeWindow) -> tuple[dict, dict]:
    from copy import deepcopy

    session = window.session
    first = next(item for item in session.blocks if item.get("assignment_id") == "math")
    extra = deepcopy(first)
    extra["id"] = "math-2"
    extra["days"] = [4]
    extra["start"] = "16:00"
    session.blocks.append(extra)
    return first, session.assignments["math"]


def test_deleting_one_time_of_homework_from_the_menu_asks_which(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    block, assignment = two_essay_sessions(window)

    def run(sheet: ConfirmSheet) -> int:
        words = {button.text() for button in sheet.buttons.values()}
        assert "This time" in words and "Delete" in words
        chosen = next(key for key, button in sheet.buttons.items() if button.text() == "This time")
        sheet.buttons[chosen].click()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ConfirmSheet, "exec", run)
    window._delete_from_block_menu(block, assignment, 2)
    settled(qapp, window)
    kept = [item for item in window.session.blocks if item.get("assignment_id") == "math"]
    assert len(kept) == 1 and kept[0]["days"] == [4]
    assert "math" in window.session.assignments


def test_deleting_the_whole_homework_from_the_menu_uses_the_editors_words(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    block, assignment = two_essay_sessions(window)
    questions: list[str] = []

    def run(sheet: ConfirmSheet) -> int:
        questions.append(sheet.question.text())
        chosen = next(key for key, button in sheet.buttons.items() if button.text() == "Delete")
        sheet.buttons[chosen].click()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ConfirmSheet, "exec", run)
    window._delete_from_block_menu(block, assignment, 2)
    settled(qapp, window)
    assert questions == [
        "Delete Math worksheet? Its times on the calendar go too, in every week. You can undo this."
    ]
    assert "math" not in window.session.assignments


def test_the_folded_waiting_popup_is_gone_once_a_drag_has_started(
    qapp: QApplication, window: NativeWindow  # noqa: F811
) -> None:
    due = sunday_due(window.session.week_start)
    window.session.add_homework(
        {"id": "poster", "title": "Poster", "due": due, "estimate_min": 30, "revision": 0}
    )
    window.session.save()
    settled(qapp, window)
    window.move(0, 0)
    window.resize(800, 720)
    for _ in range(5):
        qapp.processEvents()
    assert window.rail.folded
    window.rail.waiting_chip.click()
    qapp.processEvents()
    popup = window.findChild(QWidget, "railWaitingPopup")
    assert popup is not None and popup.isVisible()
    waiting = next(block for block in window.session.blocks if block.get("assignment_id") == "poster")
    chip = next(
        widget
        for widget in window.findChildren(QPushButton)
        if widget.property("block_id") == waiting["id"] and widget.property("tray") and widget.isVisible()
    )
    hours = window.week_table.hours
    if not hours.tracks:
        hours.resize(980, 640)
        hours.relayout()
    hours.reveal(2, 15 * 60, 18 * 60)
    qapp.processEvents()
    start = chip.mapToGlobal(chip.rect().center())
    end = hours.point_for(2, 16 * 60)
    send_mouse(chip, QEvent.Type.MouseButtonPress, start, True)
    for step in range(1, 9):
        moved = QPoint(
            start.x() + (end.x() - start.x()) * step // 8,
            start.y() + (end.y() - start.y()) * step // 8,
        )
        send_mouse(hours, QEvent.Type.MouseMove, moved, True)
        if window.hand.active:
            break
    qapp.processEvents()
    assert window.hand.active
    shown = window.findChild(QWidget, "railWaitingPopup")
    assert shown is None or not shown.isVisible()
    window.hand.cancel()


def test_the_folded_waiting_chip_has_a_chevron_and_opens_without_resizing(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    due = sunday_due(window.session.week_start)
    window.session.add_homework(
        {"id": "poster", "title": "Poster", "due": due, "estimate_min": 30, "revision": 0}
    )
    window.session.save()
    settled(qapp, window)
    window.resize(NARROW_WIDTH - 1, 860)
    for _ in range(5):
        qapp.processEvents()
    rail = window.rail
    chip = rail.findChild(QPushButton, "railWaitingChip")
    chevron = chip.findChild(QLabel, "railWaitingChevron")
    assert chevron is not None and not chevron.pixmap().isNull()
    before = window.width()
    QTest.mouseClick(chip, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert window.width() == before
    popup = window.findChild(QWidget, "railWaitingPopup")
    assert popup is not None and popup.isVisible()
    popup.close()
    qapp.processEvents()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert window.findChild(QWidget, "railWaitingPopup") is None
    for waiting in rail.chips():
        assert waiting.parent() is rail.waiting
    QTest.mouseClick(chip, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    popup = window.findChild(QWidget, "railWaitingPopup")
    assert popup is not None and popup.isVisible()
    caught: list[BaseException] = []
    previous_hook = sys.excepthook
    previous_unraisable = sys.unraisablehook

    def hook(kind, value, traceback) -> None:
        caught.append(value)
        previous_hook(kind, value, traceback)

    def unraisable(args) -> None:
        if args.exc_value is not None:
            caught.append(args.exc_value)
        previous_unraisable(args)

    def safe_hide(*_args, **_kwargs) -> None:
        if isValid(window):
            QWidget.hide(window)

    def safe_free(widget: QWidget) -> None:
        if isValid(widget):
            free(widget)

    monkeypatch.setattr(window, "hide", safe_hide)
    monkeypatch.setattr(window_support_mod, "free", safe_free)
    sys.excepthook = hook
    sys.unraisablehook = unraisable
    try:
        window.close()
        free(window)
    finally:
        sys.excepthook = previous_hook
        sys.unraisablehook = previous_unraisable
    assert caught == []


def test_a_click_on_the_grid_beside_the_empty_week_card_opens_the_free_time_menu(
    qapp: QApplication, signed_in: NativeWindow, menus: dict  # noqa: F811
) -> None:
    session = signed_in.session
    signed_in._layout = {"main": "classic", "day": "one", "options": {}}
    session.add_homework(
        {
            "id": "essay",
            "title": "History essay",
            "due": sunday_due(session.week_start),
            "estimate_min": 60,
            "revision": 0,
        }
    )
    session.save()
    wait_until(qapp, lambda: not session.busy)
    signed_in.findChild(QPushButton, "nextWeek").click()
    wait_until(qapp, lambda: not session.busy)
    settled(qapp, signed_in)
    assert signed_in.planner.currentWidget() is signed_in.week_table
    card = signed_in.empty_week
    assert card.isVisible() and EMPTY_COPY_LAST in [
        button.text() for button in card.findChildren(QPushButton) if button.isVisible()
    ]
    hours = signed_in.week_table.hours
    hours.reveal(1, 17 * 60, 17 * 60 + 30)
    qapp.processEvents()
    at = hours.point_for(1, 17 * 60)
    parent = card.parentWidget()
    assert parent is signed_in.week_table
    assert not card.geometry().contains(parent.mapFromGlobal(at))
    local = hours.mapFromGlobal(at)
    QApplication.sendEvent(hours, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, local, at))
    assert menus["rows"] and any("Add fixed time" in row for row in menus["rows"][0])
