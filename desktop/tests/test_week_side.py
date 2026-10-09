"""Today's app's rail (0.17's pick B): the mini month, what is next, Not placed yet and the focus list
left of Day and Week, the running timer as its first card, the month folded away and remembered;
folded into one line on a narrow window, where blocks keep their times; and the window's floor."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from desktop.native.calendar import sunday_due
from desktop.native.hours.canvas import BlockPainter, Drawn
from desktop.native.hours.geometry import Span
from desktop.native.hours.rail import RAIL_PX
from desktop.native.layouts.registry import sanitize_layout
from desktop.native.window import WINDOW_MIN_WIDTH, NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
    window,
)


def seeded(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    """Thursday 15:40: Soccer practice next and Dinner after it, the essay placed at 19:00 and Chem
    on Monday, the worksheet with no time."""
    session = window.session
    thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=15, minutes=40)
    session.now_ms = lambda: int(thursday.timestamp() * 1000)
    session.add_block({"id": "soccer", "title": "Soccer practice", "kind": "locked", "category": "extra",
                       "start": "16:00", "duration_min": 90, "days": [1, 3]})
    session.add_block({"id": "dinner", "title": "Dinner", "kind": "locked", "category": "meals",
                       "start": "18:30", "duration_min": 30, "days": [3]})
    due = sunday_due(session.week_start)
    for key, title in (("essay", "History essay"), ("math", "Math worksheet"), ("chem", "Chem lab report")):
        session.add_homework({"id": key, "title": title, "due": due, "estimate_min": 60, "revision": 0})
    session.save()
    settled(qapp, window)
    for key, day, start in (("essay", 3, "19:00"), ("chem", 0, "20:00")):
        block = next(block for block in session.blocks if block.get("assignment_id") == key)
        session.add_block({**block, "start": start, "days": [day], "pinned": True})
    session.save()
    settled(qapp, window)
    window._layout = sanitize_layout({"main": "classic", "day": "one"})
    window._apply_appearance()
    session.set_view("week")
    window.resize(1280, 860)
    window._on_week()
    for _ in range(5):
        qapp.processEvents()


def use_clock(qapp: QApplication, window: NativeWindow, twenty_four: bool) -> None:  # noqa: F811
    """Chooses the clock the way Settings does, so every surface redraws its times."""
    window.session.preferences = {**(window.session.preferences or {}), "clock_24h": twenty_four}
    window._sync_chrome()
    for _ in range(5):
        qapp.processEvents()


def chips(window: NativeWindow) -> list[QPushButton]:  # noqa: F811
    found = window.rail.findChildren(QPushButton)
    return [chip for chip in found if chip.property("tray") and chip.isVisible()]


def test_the_rail_holds_next_not_placed_yet_and_the_focus_list_left_of_the_week(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """The side panel went; a slim rail left of the hours holds what it held, and the week takes the
    rest of the width. Above the hours there is only the top bar."""
    seeded(qapp, window)
    rail, hours = window.rail, window.week_table
    assert window.planner.currentWidget() is window.week_table
    assert rail.isVisible() and not rail.folded and rail.width() == RAIL_PX
    left = hours.mapTo(window, QPoint(0, 0)).x()
    assert rail.mapTo(window, QPoint(rail.width(), 0)).x() <= left, "the rail is left of the hours"
    assert window.width() - (left + hours.width()) < 24, "the week takes the rest of the width"
    card = rail.next
    assert card.isVisible()
    assert (card.label.text(), card.title.text(), card.when.text(), card.then.text()) == (
        "Next", "Soccer practice", "4:00 PM · in 20 min", "Then Dinner at 6:30 PM"
    )
    # In time order with the time at the right, today's said as Today.
    assert rail.task_rows() == [("Chem lab report", "Mon 8:00 PM"), ("History essay", "Today 7:00 PM")]
    assert [chip.accessibleName() for chip in chips(window)] == ["Math worksheet · 1 h"]
    assert rail.waiting_count.text() == "1"
    use_clock(qapp, window, True)
    assert (card.when.text(), card.then.text()) == ("16:00 · in 20 min", "Then Dinner at 18:30")
    assert rail.task_rows() == [("Chem lab report", "Mon 20:00"), ("History essay", "Today 19:00")]
    use_clock(qapp, window, False)
    assert not window.focus_panel.isVisible()
    bar_bottom = window.solve_button.mapTo(window, QPoint(0, window.solve_button.height())).y()
    assert window.planner.mapTo(window, QPoint(0, 0)).y() - bar_bottom < 32
    # Day keeps the rail, and says what is next there instead of in a band above its hours.
    window.findChild(QPushButton, "viewDay").click()
    wait_until(qapp, lambda: window.planner.currentWidget() is window.day_view)
    qapp.processEvents()
    assert rail.isVisible() and card.isVisible()
    assert not window.focus_panel.now_next.isVisible(), "Day's Next band is gone"


def test_each_days_header_carries_its_homework_hours(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """The "This week" card is gone; each day says its hours of homework under its date."""
    seeded(qapp, window)
    names = [window.week_table.findChild(QLabel, f"weekDayName{day}") for day in range(7)]
    assert [name.homework for name in names] == [60, 0, 0, 60, 0, 0, 0]
    assert names[3].property("today") is True and names[0].property("today") is False
    assert names[0].accessibleName().endswith("1 h of homework")


def test_a_days_homework_length_is_never_cut_at_any_window_width(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    seeded(qapp, window)
    label = window.week_table.findChild(QLabel, "weekDayName0")
    for width in range(810, 1281, 47):
        window.resize(width, 860)
        for _ in range(5):
            qapp.processEvents()
        label.show_day("Mon", "28", 90, False)
        words = label.homework_words()
        assert words in ("1 h 30 min", "1h 30m"), (width, words)
        icon = round(QFontMetricsF(label._fonts()[2]).ascent())
        room = label.width() - label._homework_left(icon)
        fits = QFontMetricsF(label._fonts()[2]).horizontalAdvance(words) <= room
        assert fits, f"{words!r} is cut at {width} px: {label.width()} wide"


def test_the_month_folds_away_from_its_header_and_stays_folded_after_a_restart(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    server,  # noqa: F811
) -> None:
    seeded(qapp, window)
    rail = window.rail
    month = rail.month
    week = date.fromisoformat(window.session.week_start)
    assert month.isVisible() and month.dates.week_start == week.isoformat()
    assert sunday_due(window.session.week_start)[:10] in month.dates.due, "a dot on the day homework is due"
    assert month.fold.toolTip() == "Hide the month"
    QTest.mouseClick(month.fold, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert not month.isVisible()
    # With the month hidden the rail starts at Next, whose header has the way back.
    top = rail.next.mapTo(rail, QPoint(0, 0)).y()
    assert top < 40, f"Next starts {top} px down the rail"
    assert rail.show_month.isVisible() and rail.show_month.toolTip() == "Show the month"
    assert rail.next.isAncestorOf(rail.show_month)
    again = NativeWindow(server.origin)
    try:
        assert again.rail.month_shown is False, "the fold was forgotten"
    finally:
        again.close()
    QTest.mouseClick(rail.show_month, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert month.isVisible()
    # A date in the month opens its week.
    later = week + timedelta(days=14)
    QTest.mouseClick(
        month.dates, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        month.dates.date_point(later.isoformat()).toPoint(),
    )
    wait_until(qapp, lambda: window.session.week_start == later.isoformat() and not window.session.busy)


def test_a_running_timer_is_the_rails_first_card(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Decision 15: the timer is the rail's first card, not a strip over the hours."""
    seeded(qapp, window)
    essay = next(block for block in window.session.blocks if block.get("assignment_id") == "essay")
    window.session.start_focus(essay["id"], 3)
    wait_until(qapp, lambda: window.session.focus is not None)
    window._on_week()
    qapp.processEvents()
    panel, rail = window.focus_panel, window.rail
    assert panel.isVisible() and rail.isAncestorOf(panel)
    tops = {name: widget.mapTo(rail, QPoint(0, 0)).y() for name, widget in
            (("timer", panel), ("month", rail.month), ("next", rail.next))}
    assert tops["timer"] < tops["month"] < tops["next"], tops
    # #18: Today's app shows the one-line strip the other designs show, not the homework's name.
    assert panel.width() <= RAIL_PX and panel.task.text() == "Session · 30:00 left"
    window.session.reset_focus()
    wait_until(qapp, lambda: window.session.focus is None)


def test_high_contrast_cuts_no_chip_and_scrolls_the_focus_list_neither_way(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Switched to High contrast with the rail up, its larger text ran the chips' words off their edge
    and gave the focus list a sideways scroll bar and a row short."""
    from desktop.native.look import sanitize_look

    seeded(qapp, window)
    session = window.session
    session.add_homework(
        {"id": "poster", "title": "Science poster for the fair", "due": sunday_due(session.week_start),
         "estimate_min": 90, "revision": 0}
    )
    session.save()
    settled(qapp, window)
    window._look = sanitize_look({"preset": "high-contrast", "knobs": {}})
    window._apply_appearance()
    for _ in range(5):
        qapp.processEvents()
    rail = window.rail
    shown = chips(window)
    assert len(shown) == 2
    for chip in shown:
        assert len(chip.title_lines()) <= 2
        assert chip.mapTo(rail, chip.rect().topRight()).x() <= rail.width()
    assert rail.width() == RAIL_PX
    tasks = rail.tasks
    assert tasks.count() and not tasks.horizontalScrollBar().isVisible()
    assert not tasks.verticalScrollBar().isVisible()
    assert tasks.viewport().height() >= tasks.count() * tasks.sizeHintForRow(0)


def test_a_narrow_window_folds_the_rail_into_one_line_and_blocks_keep_their_times(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    seeded(qapp, window)
    rail, hours = window.rail, window.week_table
    window.resize(1100, 860)
    for _ in range(5):
        qapp.processEvents()
    assert rail.folded and not hours.hours.short_words
    line_foot = rail.mapTo(window, rail.rect().bottomLeft()).y()
    assert line_foot < hours.mapTo(window, hours.rect().topLeft()).y(), "the line sits above the hours"
    assert rail.height() < 80, "one slim line"
    # #82: what waits is a chip with the book and a chevron after the line, not words in it.
    assert rail.line.text() == "Next: Soccer practice, 4:00 PM · in 20 min"
    use_clock(qapp, window, True)
    assert rail.line.text() == "Next: Soccer practice, 16:00 · in 20 min"
    use_clock(qapp, window, False)
    assert not rail.tasks.isVisible() and not rail.month.isVisible()
    waiting = rail.waiting_chip
    assert waiting.isVisible()
    assert waiting.findChild(QLabel, "railWaitingWords").text() == "Not placed yet · 1"
    assert waiting.geometry().top() == rail.line.geometry().top(), "the chip follows the line"
    assert window.rect().contains(waiting.mapTo(window, waiting.rect().bottomRight()))
    chip = rail.chips()[0]
    window.resize(1280, 860)
    for _ in range(5):
        qapp.processEvents()
    assert not rail.folded and not hours.hours.short_words
    assert rail.width() == RAIL_PX and chip.isVisible()


def test_the_window_is_never_narrower_than_800(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    assert WINDOW_MIN_WIDTH == 800
    window.resize(650, 720)
    for _ in range(3):
        qapp.processEvents()
    assert window.width() == 800


def test_a_short_block_word_gives_its_name_the_room_its_times_took(qapp: QApplication) -> None:  # noqa: F811
    """At 800 pixels "Soccer practice" read "Soccer …" above its times. Short of room its name is
    whole, and the times are left to its editor."""
    from desktop.native.hours.canvas import block_layout

    title, small = BlockPainter({}).fonts(QFont("Inter", 12))
    room = QRectF(0, 0, 120, 72)
    soccer = Drawn("soccer", "Soccer practice", "sport", False, Span(3, 16 * 60, 17 * 60 + 30), 0, 1)
    assert any("16:00" in line.text for line in block_layout(soccer, title, small, room))
    short = Drawn(**{**soccer.__dict__, "short": True})
    assert [line.text for line in block_layout(short, title, small, room)] == ["Soccer practice"]


def test_the_focus_list_grows_to_its_rows_with_no_scroll_bar_and_no_row_cut(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """The list was a small scrolling box that clipped the last row ("Fri 17:0(")."""
    seeded(qapp, window)
    session = window.session
    math = next(block for block in session.blocks if block.get("assignment_id") == "math")
    session.add_block({**math, "start": "17:00", "days": [4], "pinned": True})
    session.save()
    settled(qapp, window)
    for _ in range(5):
        qapp.processEvents()
    tasks = window.rail.tasks
    assert tasks.count() == 3
    row = tasks.sizeHintForRow(0)
    assert not tasks.verticalScrollBar().isVisible() and not tasks.horizontalScrollBar().isVisible()
    assert tasks.viewport().height() >= 3 * row, "all three rows fit"
    last = tasks.visualItemRect(tasks.item(2))
    assert last.bottom() <= tasks.viewport().height() and last.right() <= tasks.viewport().width()
    assert tasks.height() >= 3 * row


def test_the_focus_list_has_no_row_limit_of_its_own(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """The rail scrolls as a whole, so the list never needs a scroll bar of its own."""
    seeded(qapp, window)
    rows = [{"id": f"t{n}", "day": 4, "start": "17:00", "title": f"Task {n}"} for n in range(9)]
    window.rail.set_tasks(rows, 0)
    tasks = window.rail.tasks
    assert tasks.count() == 9
    assert tasks.height() >= 9 * tasks.sizeHintForRow(0)


@pytest.mark.parametrize("twenty_four", [True, False])
def test_rail_chips_and_focus_rows_wrap_long_names_on_two_lines_at_large_text(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    twenty_four: bool,
) -> None:
    """#84: "Math worksheet, chapter 4" and "History / essay" stay whole on two lines, not "Math worksh…".
    On the 12-hour clock the time ("Today 7:00 PM") is wider and left too little room for "worksheet,"."""
    from desktop.native.hours.rail import rail_title_lines
    from desktop.native.look import sanitize_look

    seeded(qapp, window)
    use_clock(qapp, window, twenty_four)
    session = window.session
    due = sunday_due(session.week_start)
    for key, title in (
        ("long-math", "Math worksheet, chapter 4"),
        ("long-history", "History / essay"),
    ):
        session.add_homework({"id": key, "title": title, "due": due, "estimate_min": 60, "revision": 0})
    session.save()
    settled(qapp, window)
    window._look = sanitize_look({"preset": "default", "knobs": {"text": "large"}})
    window._apply_appearance()
    for _ in range(5):
        qapp.processEvents()
    by_title = {chip._title: chip for chip in window.rail.chips()}
    for title in ("Math worksheet, chapter 4", "History / essay"):
        chip = by_title[title]
        lines = chip.title_lines()
        assert len(lines) <= 2
        assert " ".join(lines) == title
        assert "…" not in chip.shown_title()
        assert title in chip.accessibleName()
        body, _small = chip._fonts()
        assert rail_title_lines(title, QFontMetricsF(body), chip._title_room()) == lines
    essay = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    session.add_block({**essay, "start": "18:00", "days": [3], "pinned": True})
    math = next(block for block in session.blocks if block.get("assignment_id") == "long-math")
    session.add_block({**math, "start": "19:00", "days": [3], "pinned": True})
    history = next(block for block in session.blocks if block.get("assignment_id") == "long-history")
    session.add_block({**history, "start": "20:00", "days": [3], "pinned": True})
    session.save()
    settled(qapp, window)
    for _ in range(5):
        qapp.processEvents()
    # The focus rows: each long name on two lines, and the list as tall as all of them, at the
    # widths the bar fits Plan to, after Large text has arrived (the list was sized before it).
    tasks = window.rail.tasks
    line = QFontMetricsF(window.rail.fonts()[0]).lineSpacing()
    for width in (1157, 1280):
        window.resize(width, 800)
        for _ in range(5):
            qapp.processEvents()
        rows = {tasks.item(row).text(): tasks.visualItemRect(tasks.item(row)) for row in range(tasks.count())}
        for title in ("Math worksheet, chapter 4", "History / essay"):
            assert rows[title].height() >= 2 * line, (width, title, rows[title].height(), line)
        shown = {tasks.item(row).text(): tasks.item(row) for row in range(tasks.count())}
        assert shown["Math worksheet, chapter 4"].data(Qt.ItemDataRole.ToolTipRole) == (
            "Today 19:00" if twenty_four else "Today 7:00 PM"
        )
        # Whole, not "Math wor…": the lines the row draws spell the name.
        for title in ("Math worksheet, chapter 4", "History / essay"):
            drawn, _below, _timing = tasks.itemDelegate().row_lines(
                tasks.indexFromItem(shown[title]), tasks.viewport().width()
            )
            assert len(drawn) <= 2 and " ".join(drawn) == title, (width, title, drawn)
        lowest = max(rect.bottom() for rect in rows.values())
        assert lowest < tasks.viewport().height(), (width, lowest, tasks.viewport().height())


@pytest.mark.parametrize(
    ("twenty_four", "words"), [(True, "18:45 · Starting now"), (False, "6:45 PM · Starting now")]
)
def test_the_ringing_alarm_says_its_time_on_the_clock_the_student_chose(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    twenty_four: bool,
    words: str,
) -> None:
    from desktop.native.settings import AlarmRingDialog

    use_clock(qapp, window, twenty_four)
    dialog = AlarmRingDialog(window, {"name": "Guitar practice", "time": "18:45", "block": "guitar"}, "")
    assert dialog.findChild(QLabel, "alarmDetail").text() == words
