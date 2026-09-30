"""Retro desktop, Windows 98 as it was drawn: live hours in Week.exe, the homework in Notepad, Up next
as a dialog, and a desktop whose icons, buttons and taskbar do what they say or nothing at all."""

from __future__ import annotations

import importlib.util
import itertools
import os
from collections.abc import Iterator

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK, block

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QLabel,
        QLayout,
        QLayoutItem,
        QPushButton,
        QScrollBar,
        QWidget,
    )
    from shiboken6 import isValid

    from desktop.native.fonts import load_fonts
    from desktop.native.hours.canvas import Drawn, Started, Written, cuts_a_word
    from desktop.native.hours.chips import TrayChip
    from desktop.native.hours.geometry import Span
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.registry import MATCH, options_for, tokens_for
    from desktop.native.layouts.retro import (
        NOT_PLACED,
        ZOOM_MS,
        Deadline,
        Mirror,
        RetroPainter,
        RetroView,
        Zoom,
        arrange,
        deadlines,
        due_heading,
        note_lines,
        note_widths,
        scheme,
        shorten,
        up_next,
    )
    from desktop.native.look import (
        AA_TEXT,
        ACCENTS,
        LOOK_PRESETS,
        PACKS,
        contrast,
        luminance,
        resolved_palette,
    )
    from desktop.native.motion import apply_ui_effects, duration
    from desktop.native.weekmodel import build_week, minute_of

NBSP = "\u00a0"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-retro-test"])
    yield application


def palette_of(look: str = "light") -> dict:
    return {
        "light": resolved_palette("light-frost", False, None, "default"),
        "dark": resolved_palette("dark-frost", True, None, "default"),
        "contrast": resolved_palette("system", False, {"preset": "high-contrast", "knobs": {}}, "default"),
    }[look]


def scene(
    clock: str = "13:40",
    blocks: list[dict] | None = None,
    *,
    surface: str = "week",
    iso_day: str = "",
    scale: float = 1.0,
    look: str = "light",
    **chosen: str,
) -> Scene:
    options = {**options_for(None, "retro"), **chosen}
    week = build_week(WEEK, blocks or BLOCKS, HOMEWORK, TRACE)
    return Scene(
        week,
        3,
        minute_of(clock),
        options,
        tokens_for("retro", options["colour"], palette_of(look)),
        scale=scale,
        surface=surface,
        iso_day=iso_day,
    )


def shown(
    qapp: QApplication,
    width: int = 1366,
    height: int = 720,
    blocks: list[dict] | None = None,
    **chosen: str,
) -> RetroView:
    view = RetroView()
    view.resize(width, height)
    view.show_week(scene(blocks=blocks, **chosen))
    view.show()
    qapp.processEvents()
    return view


def windows(view: RetroView) -> list[str]:
    """The windows open on the desktop. A closed one is kept, hidden, so it opens where it was."""
    return sorted(
        item.objectName()
        for item in view.findChildren(QFrame)
        if item.property("role") == "window" and item.isVisibleTo(view)
    )


def task(view: RetroView, key: str) -> QPushButton:
    return view.findChild(QPushButton, f"retroTask-{key}")


def text(view: RetroView, name: str) -> str:
    return view.findChild(QLabel, name).text()


def test_three_windows_open_and_the_taskbar_says_so(qapp: QApplication) -> None:
    view = shown(qapp)
    assert windows(view) == ["retroWindow-next", "retroWindow-notes", "retroWindow-week"]
    tasks = [task(view, key) for key in ("week", "notes", "next")]
    assert [(made.text(), made.property("open")) for made in tasks] == [
        ("Week.exe", "true"),
        ("deadlines.txt", "true"),
        ("Up next", "true"),
    ]
    # Windows 98 presses in the button of the window in front alone.
    assert [made.sunk for made in tasks] == [True, False, False]
    assert text(view, "retroClock") == "13:40"
    assert text(view, "retroTitle-notes") == "deadlines.txt - Notepad"


@pytest.mark.parametrize(("width", "height", "scale"), [(1280, 820, 1.0), (1150, 768, 1.4)])
def test_day_opens_week_exe_on_one_live_column(
    qapp: QApplication, width: int, height: int, scale: float
) -> None:
    view = shown(qapp, width, height, surface="day", iso_day="2026-09-17", scale=scale)
    assert text(view, "retroTitle-week") == "Week.exe - Thursday 17 September"
    assert task(view, "week").text() == "Week.exe"
    scroll = view.findChild(HoursScroll, "retroDayScroll")
    assert scroll is not None
    assert [track.day for track in scroll.canvas.tracks] == [3]
    assert scroll.canvas.hand is view.hand
    assert scroll.canvas.block_rect("school", 3) is not None
    chip = view.findChild(TrayChip, "retroNoteWaiting0")
    assert chip.isVisible()
    corner = chip.mapTo(view, QPoint(chip.width(), chip.height()))
    assert corner.x() <= view.width() and corner.y() <= view.height()


def test_day_has_the_folder_web_view_with_the_days_summary(qapp: QApplication) -> None:
    """Thursday has School 08:00 to 14:30, Dinner 18:00, Essay-1 18:45 and Chem-1 20:00, 9 h 30 min in
    all, three of them after 13:40; it is free from School's end to Dinner, and from Chem-1's end to
    22:00. The quarter hours between Dinner, Essay-1 and Chem-1 are too short to list."""
    view = shown(qapp, 1280, 820, surface="day", iso_day="2026-09-17")
    said = [label.text() for label in view.findChildren(QLabel) if label.objectName().startswith("retroWeb")]
    assert said == [
        "Thursday",
        "17 September",
        f"9{NBSP}h{NBSP}30{NBSP}min planned, 3 still to come.",
        "Your day",
        "School",
        "6 h 30 min",
        "Homework",
        "2 h 30 min",
        "Meals",
        "30 min",
        "Free from now",
        "14:30–18:00",
        "3 h 30 min",
        "21:30–22:00",
        "30 min",
    ]
    assert text(view, "retroStatusNow") == "3 still to come"
    other = shown(qapp, 1280, 820, surface="day", iso_day="2026-09-18")
    said = [label.text() for label in other.findChildren(QLabel) if label.objectName().startswith("retroWeb")]
    assert "Free from now" not in said and "Free" in said
    assert not other.findChild(QLabel, "retroStatusNow").isVisible()


def test_week_has_seven_live_columns_and_pinned_day_names(qapp: QApplication) -> None:
    view = shown(qapp, 1150, 768)
    scroll = view.findChild(HoursScroll, "retroWeekScroll")
    assert scroll is not None
    assert [track.day for track in scroll.canvas.tracks] == list(range(7))
    assert scroll.canvas.hand is view.hand
    assert scroll.horizontalScrollBar().maximum() == 0
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    for day in range(7):
        pick = view.findChild(QPushButton, f"retroDay{day}")
        assert pick.isVisible()
        assert pick.text().startswith(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[day])
        assert pick.mapToGlobal(pick.rect().center()) == scroll.canvas.day_name(day)
    view.findChild(QPushButton, "retroDay6").click()
    assert opened == ["2026-09-20"]


def test_a_narrow_week_names_every_day_alike(qapp: QApplication) -> None:
    """With no room for "Wed 16" in one column, every column says its day alone, not some with the
    date and some without."""
    view = shown(qapp, 800, 700)
    heads = [view.findChild(QPushButton, f"retroDay{day}") for day in range(7)]
    assert [head.parts() for head in heads] == [
        [(name, day == 3)] for day, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))
    ]
    wide = shown(qapp, 1366, 720)
    assert wide.findChild(QPushButton, "retroDay2").parts() == [("Wed ", False), ("16", True)]


def test_the_week_scrolls_on_windows_98s_bar_in_step_with_the_hours(qapp: QApplication) -> None:
    view = shown(qapp)
    scroll = view.findChild(HoursScroll, "retroWeekScroll")
    bar = view.findChild(QWidget, "retroWeekScrollBar")
    assert bar.isVisible() and bar.width() == 17
    assert not scroll.verticalScrollBar().isVisible()
    scroll.verticalScrollBar().setValue(120)
    assert bar.value() == 120
    bar.setValue(200)
    assert scroll.verticalScrollBar().value() == 200


def test_windows_98s_bar_leaves_a_cut_value_for_the_hours_to_keep(qapp: QApplication) -> None:
    """The drawn bar copies the hours' range whenever it changes. Qt says a range changed before it
    cuts the value to it, which is when the hours keep where they were; the drawn bar wrote its own cut
    value back first, and so whoever heard of the range after it saw the hours already moved."""
    host = QWidget()
    source, shown = QScrollBar(host), QScrollBar(host)
    source.setRange(0, 400)
    source.setValue(400)
    Mirror(source, shown, host)
    seen: list[int] = []
    source.rangeChanged.connect(lambda _low, _high: seen.append(source.value()))
    source.setRange(0, 380)
    assert seen == [400]
    assert (source.value(), shown.value(), shown.maximum()) == (380, 380, 380)
    shown.setValue(120)
    assert source.value() == 120, "the student's own scrolling on the drawn bar still moves the hours"


def test_a_window_closes_and_the_taskbar_brings_it_back(qapp: QApplication) -> None:
    view = shown(qapp)
    view.findChild(QPushButton, "retroClose-notes").click()
    assert windows(view) == ["retroWindow-next", "retroWindow-week"]
    assert task(view, "notes").property("open") == "false"
    task(view, "notes").click()
    assert "retroWindow-notes" in windows(view)


def test_a_window_opens_with_windows_98s_zoom_rectangle_within_the_levels(qapp: QApplication) -> None:
    """Decision 35 of 0.17: the title bar of a window opened from the taskbar flies out from its button
    to where the window's lands, and the window shows there. Under Reduce it fades in instead, and with
    animations off it is simply there. Live at once in every level."""
    try:
        for level in ("normal", "reduce", "off"):
            apply_ui_effects(level)
            view = shown(qapp)
            view.findChild(QPushButton, "retroClose-notes").click()
            task(view, "notes").click()
            notes = view.findChild(QFrame, "retroWindow-notes")
            assert "retroWindow-notes" in windows(view), level
            zooms = [child for child in view.children() if isinstance(child, Zoom)]
            effect = notes.graphicsEffect()
            if level == "normal":
                assert len(zooms) == 1, "a title bar flies out"
                zoom = zooms[0]
                assert zoom.start.top() > zoom.end.top(), "up from the taskbar"
                assert zoom.end == QRectF(QRect(notes.bar.mapTo(view, QPoint(0, 0)), notes.bar.size()))
                assert effect.opacity == 0, "the window waits for its title bar to land"
            elif level == "reduce":
                assert zooms == [] and effect.offset == QPoint() and effect.opacity == 0, "a fade, no zoom"
            else:
                assert zooms == [] and effect is None
            QTest.qWait(duration(ZOOM_MS, "normal") + 200)
            assert notes.graphicsEffect() is None, level
            assert [child for child in view.children() if isinstance(child, Zoom)] == [], level
    finally:
        apply_ui_effects("normal")


def test_a_taskbar_button_brings_its_window_forward_or_puts_the_one_in_front_away(qapp: QApplication) -> None:
    view = shown(qapp)
    task(view, "notes").click()
    assert "retroWindow-notes" in windows(view)
    assert [task(view, key).sunk for key in ("week", "notes", "next")] == [False, True, False]
    task(view, "notes").click()
    assert "retroWindow-notes" not in windows(view)
    assert task(view, "week").sunk, "the window under it comes to the front"
    task(view, "notes").click()
    assert "retroWindow-notes" in windows(view) and task(view, "notes").sunk


def test_minimise_hides_a_window_and_maximise_fills_the_desktop_and_restores_it(qapp: QApplication) -> None:
    view = shown(qapp)
    week = view.findChild(QFrame, "retroWindow-week")
    desk = view.findChild(QWidget, "retroDesk")
    home = week.geometry()
    maximise = view.findChild(QPushButton, "retroMax-week")
    maximise.click()
    qapp.processEvents()
    assert week.geometry() == desk.rect()
    assert maximise.accessibleName() == "Restore Week.exe"
    maximise.click()
    qapp.processEvents()
    assert week.geometry() == home
    assert maximise.accessibleName() == "Maximise Week.exe"
    view.findChild(QPushButton, "retroMin-week").click()
    assert "retroWindow-week" not in windows(view)
    assert task(view, "week").property("open") == "false"


def test_start_opens_the_apps_own_menu_from_its_corner(qapp: QApplication) -> None:
    view = shown(qapp)
    asked: list[QPoint] = []
    view.menu_requested.connect(asked.append)
    start = view.findChild(QPushButton, "retroStart")
    start.click()
    assert asked == [start.mapToGlobal(QPoint(0, 0))]


def test_the_desktop_icons_open_their_windows_and_the_others_are_only_pictures(qapp: QApplication) -> None:
    view = shown(qapp)
    view.findChild(QPushButton, "retroClose-notes").click()
    notes = view.findChild(QPushButton, "retroIcon1")
    assert notes.text() == "deadlines.txt"
    notes.click()
    assert "retroWindow-notes" in windows(view) and task(view, "notes").sunk
    for index, words in ((2, "Homework"), (3, "Focus timer"), (4, "Recycle Bin")):
        assert view.findChild(QPushButton, f"retroIcon{index}") is None
        assert view.findChild(QWidget, f"retroIcon{index}").accessibleName() == words


def test_the_icons_give_way_before_week_exe_gets_narrow() -> None:
    homes, icons = arrange(QSize(1280, 708), 212, 1.0)
    assert icons and homes["week"].left() == 100 and homes["notes"].width() == 380
    assert homes["notes"].left() == homes["week"].right() + 13
    homes, icons = arrange(QSize(1150, 700), 212, 1.2)
    assert not icons and homes["week"].left() == 12
    assert homes["next"].top() == homes["notes"].bottom() + 17


def test_ok_dismisses_up_next_and_it_says_what_is_coming(qapp: QApplication) -> None:
    view = shown(qapp)
    assert text(view, "retroNextTitle") == "Dinner"
    # "in 4 h 20 min" is never broken over two lines.
    assert text(view, "retroNextText") == f"starts at 18:00, in{NBSP}4{NBSP}h{NBSP}20{NBSP}min."
    assert text(view, "retroNextThen") == "Then Essay-1 at 18:45."
    view.findChild(QPushButton, "retroNextOk").click()
    assert windows(view) == ["retroWindow-notes", "retroWindow-week"]


def test_up_next_on_another_week_says_nothing_is_next() -> None:
    other = scene()
    other = Scene(other.week, None, other.minute, other.options, other.tokens)
    assert up_next(other).line == "This is another week, so nothing is next."
    last = up_next(scene("19:00"))
    assert (last.title, last.then) == ("Chem-1", "")
    assert up_next(scene("21:00")).title == "Nothing else scheduled today"


def test_a_window_drags_by_its_title_bar_and_stays_where_it_was_put(qapp: QApplication) -> None:
    view = shown(qapp)
    frame = view.findChild(QFrame, "retroWindow-notes")
    start = frame.pos()
    bar = view.findChild(QLabel, "retroTitle-notes")
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=QPoint(20, 8))
    QTest.mouseMove(bar, QPoint(20 - 150, 8 + 90))
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(20 - 150, 8 + 90))
    moved = view.findChild(QFrame, "retroWindow-notes").pos()
    assert (moved.x(), moved.y()) == (start.x() - 150, start.y() + 90)
    view.show_week(scene("13:41"))
    again = view.findChild(QFrame, "retroWindow-notes").pos()
    assert (again.x(), again.y()) == (moved.x(), moved.y())


def test_a_window_cannot_be_dragged_off_the_desktop(qapp: QApplication) -> None:
    view = shown(qapp)
    bar = view.findChild(QLabel, "retroTitle-next")
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=QPoint(10, 8))
    QTest.mouseMove(bar, QPoint(-5000, -5000))
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(-5000, -5000))
    spot = view.findChild(QFrame, "retroWindow-next").pos()
    assert (spot.x(), spot.y()) == (0, 0)


def test_every_weekday_and_the_tray_are_reachable_when_the_desk_is_narrow(qapp: QApplication) -> None:
    weekend = BLOCKS + [
        block("shift", "locked", [5], "09:00", 240, title="Saturday shift at the cafe", category="extra"),
        block(
            "choir", "locked", [6], "10:00", 180, title="Sunday choir practice and coffee", category="extra"
        ),
    ]
    view = shown(qapp, 1150, 768, blocks=weekend, scale=1.4)
    week = view.findChild(QFrame, "retroWindow-week")
    desk = view.findChild(QWidget, "retroDesk")
    assert week.width() <= desk.width()
    assert 0 <= week.x() <= max(desk.width() - 60, 0)
    pane = view.findChild(HoursScroll, "retroWeekScroll")
    assert pane is not None
    for day in range(7):
        assert pane.canvas.track_for(day) is not None
        head = view.findChild(QPushButton, f"retroDay{day}")
        assert head.mapTo(view, QPoint(0, 0)).x() >= 0
        assert head.mapTo(view, QPoint(head.width(), 0)).x() <= view.width()
    note = view.findChild(TrayChip, "retroNoteWaiting0")
    assert note.isVisible()
    assert note.mapTo(view, QPoint(note.width(), note.height())).x() <= view.width()


def test_notepad_lists_the_homework_under_its_deadline_with_its_length_and_time(qapp: QApplication) -> None:
    """Chem lab report is due today and placed at 20:00 for 1 h 30; the history essay is due tomorrow at
    21:00 and placed at 18:45 for an hour; the poster, due Sunday at 20:00, has no time yet. Each line's
    length and time sit in columns as wide as the widest. The time a homework is placed at says so, so
    it is never read as when it is due, which the heading above it says."""
    view = shown(qapp)
    headings = [label.text() for label in view.findChildren(QLabel, "retroNoteDue")]
    assert headings == [
        "Due Thursday 17 September, today.",
        "Due Friday 18 September at 21:00, tomorrow.",
        f"Due Sunday 20 September at 20:00, in{NBSP}3{NBSP}days.",
    ]
    rows = [view.findChild(QPushButton, name) for name in ("retroNote0", "retroNote1", "retroNoteWaiting0")]
    assert [row.lines for row in rows] == [
        ["Chem-1    1 h 30  placed Thu 20:00"],
        ["Essay-1   1 h     placed Thu 18:45"],
        [f"Poster-1  2 h     {NOT_PLACED}"],
    ]
    chip = view.findChild(TrayChip, "retroNoteWaiting0")
    assert chip.block_id == "poster-1"
    assert chip.hand is view.hand
    assert text(view, "retroNotesHint") == f"1 {NOT_PLACED}: drag it onto Week.exe, or use Plan my homework."
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    rows[0].click()
    assert opened == ["chem-1"]


def test_what_has_no_time_is_shown_once_in_the_notepad_or_under_the_hours_when_it_is_closed(
    qapp: QApplication,
) -> None:
    view = shown(qapp)

    def seen() -> list[str]:
        # A closed window is kept, hidden, with its chip in it: out of sight, out of the mouse's and
        # Tab's reach. A chip made as a click is handled shows once the event loop runs again.
        qapp.processEvents()
        chips = view.findChildren(TrayChip)
        return [chip.objectName() for chip in chips if chip.block_id == "poster-1" and chip.isVisible()]

    assert seen() == ["retroNoteWaiting0"]
    QTest.mouseClick(view.findChild(QPushButton, "retroClose-notes"), Qt.MouseButton.LeftButton)
    assert seen() == ["retroWaiting0"]
    QTest.mouseClick(task(view, "notes"), Qt.MouseButton.LeftButton)
    assert seen() == ["retroNoteWaiting0"]


def test_a_notepad_line_short_of_room_puts_its_length_and_time_under_its_title(qapp: QApplication) -> None:
    """At 1150x768 with large text a long title leaves no room on its line for the length and time,
    so they go on the line under it, whole; the title is shortened only at a word, and no line runs
    off the page."""
    long = [
        item if item["id"] != "essay-1" else {**item, "title": "History essay on the causes of the war"}
        for item in BLOCKS
    ]
    view = shown(qapp, 1150, 768, blocks=long, scale=1.4)
    qapp.processEvents()
    page = view.findChild(QFrame, "retroNotepad")
    essay = next(row for row in view.findChildren(QPushButton) if row.objectName() == "retroNote1")
    assert len(essay.lines) == 2, essay.lines
    assert "History essay on the causes of the war".startswith(essay.lines[0].removesuffix("…"))
    # Under the title, in from the edge; "placed" leaves this narrow page no title column.
    assert essay.lines[1].split() == ["1", "h", "placed", "Thu", "18:45"] and essay.lines[1].startswith("  ")
    for row in view.findChildren(QPushButton):
        if row.property("role") != "note":
            continue
        need = row.sizeHint()
        assert need.width() <= row.width() and need.height() <= row.height(), f"{row.lines!r} is cut"
        assert row.mapTo(page, QPoint(row.width(), 0)).x() <= page.width()


def test_notepads_columns_and_their_fallbacks() -> None:
    chem = Deadline("Chem lab report", "1 h 30", "Mon 20:00", "chem-1")
    spanish = Deadline("Spanish vocab", "30 min", NOT_PLACED, "spanish-1")
    assert note_widths([chem, spanish], 42) == (15, 6)
    # On a narrower page the title column gives way to the lengths and times.
    assert note_widths([chem, spanish], 30) == (6, 6)
    assert note_lines(chem, (15, 6), 42) == ["Chem lab report  1 h 30  Mon 20:00"]
    assert note_lines(spanish, (15, 6), 42) == ["Spanish vocab    30 min  not placed yet"]
    # Too narrow for the columns beside the title: they go under it, in from the edge.
    assert note_lines(chem, (15, 6), 30) == ["Chem lab report", "   1 h 30  Mon 20:00"]
    # A title wider than its column, on a page wide enough for the columns: under it, in their columns.
    assert note_lines(chem, (10, 6), 42) == ["Chem lab report", "            1 h 30  Mon 20:00"]
    assert shorten("History essay on the causes of the war", 30) == "History essay on the causes…"
    assert shorten("Supercalifragilistic", 8) == "Superca…"


def test_a_deadline_says_when_it_is_from_today() -> None:
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    assert due_heading("2026-09-17T23:59", week, 3) == "Due Thursday 17 September, today."
    assert due_heading("2026-09-18T21:00", week, 3) == "Due Friday 18 September at 21:00, tomorrow."
    assert due_heading("2026-09-15T08:00", week, 3) == "Due Tuesday 15 September at 08:00, past due."
    assert due_heading("2026-09-20T23:59", week, None) == "Due Sunday 20 September."
    assert due_heading(None, week, 3) == "No due date."
    groups = deadlines(week, 3)
    assert [[line.block_id for line in group.lines] for group in groups] == [
        ["chem-1"],
        ["essay-1"],
        ["poster-1"],
    ]


def test_closing_the_notepad_cannot_hide_what_has_no_time(qapp: QApplication) -> None:
    view = shown(qapp, windows="week")
    assert windows(view) == ["retroWindow-week"]
    waiting = view.findChild(TrayChip, "retroWaiting0")
    assert waiting.text() == "Poster-1 · 2 h"
    assert waiting.hand is view.hand
    assert "There is not enough time left before it is due" in waiting.toolTip()


def test_redraw_keeps_each_tabs_scroll_zoom_and_position(qapp: QApplication) -> None:
    view = shown(qapp)
    week = view.findChild(HoursScroll, "retroWeekScroll")
    week.zoom_by(1)
    week.verticalScrollBar().setValue(180)
    view.show_week(scene("13:41"))
    assert view.findChild(HoursScroll, "retroWeekScroll") is week
    assert (week.px, week.verticalScrollBar().value()) == (56, 180)
    view.show_week(scene("13:41", surface="day", iso_day="2026-09-17"))
    day = view.findChild(HoursScroll, "retroDayScroll")
    assert day is not None and day is not week
    assert week.parentWidget() is not None
    view.show_week(scene("13:42"))
    assert view.findChild(HoursScroll, "retroWeekScroll") is week
    assert day.parentWidget() is not None
    assert (week.px, week.verticalScrollBar().value()) == (56, 180)


def item_holding(layout: QLayout, widget: QWidget) -> QLayoutItem | None:
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            return item
        inner = item.layout()
        if inner is not None and (found := item_holding(inner, widget)) is not None:
            return found
    return None


def test_redraw_takes_the_hours_out_of_their_row_before_keeping_them(qapp: QApplication) -> None:
    """Moved out while Week.exe's row still listed them, the hours made Qt delete the row's item behind
    PySide, whose wrapper for it lived on. What Qt made next at that address reached Python as that
    item, and the rig crashed with a segfault."""
    view = shown(qapp, surface="day", iso_day="2026-09-17")
    window = view.findChild(QFrame, "retroWindow-week")
    hours = view.findChild(QFrame, "retroDayScrollField")
    held = item_holding(window.layout(), hours)
    assert held is not None
    wrapped_as_they_left: list[bool] = []

    class Watch(QObject):
        def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
            if event.type() == QEvent.Type.ChildRemoved and event.child() is hours:
                wrapped_as_they_left.append(isValid(held))
            return False

    watch = Watch()
    window.installEventFilter(watch)
    view.show_week(scene("13:41", surface="day", iso_day="2026-09-17"))
    window.removeEventFilter(watch)
    assert view.findChild(QFrame, "retroDayScrollField") is hours
    assert wrapped_as_they_left == [False]


@pytest.mark.parametrize(
    ("verdict", "expected", "state"),
    [
        (Verdict(True, "Thu 10:00–12:00 · 2 h"), "Thu 10:00–12:00 · 2 h", "ok"),
        (Verdict(False, "After the due date"), "10:00–12:00 · After the due date", "refused"),
    ],
)
def test_status_bar_tracks_the_hands_time_and_verdict(
    qapp: QApplication, verdict: Verdict, expected: str, state: str
) -> None:
    host = QWidget()
    hand = Hand(lambda block_id, from_day, span: verdict, host)
    view = RetroView(hand=hand)
    view.resize(1150, 768)
    view.show_week(scene(windows="week"))
    view.show()
    qapp.processEvents()
    assert text(view, "retroStatus") == "Ready"
    scroll = view.findChild(HoursScroll, "retroWeekScroll")
    scroll.scroll_to(10 * 60)
    qapp.processEvents()
    chip = view.findChild(TrayChip, "retroWaiting0")
    target = scroll.canvas.point_for(3, 10 * 60)
    QTest.mousePress(chip, Qt.MouseButton.LeftButton, pos=chip.rect().center())
    QTest.mouseMove(chip, chip.mapFromGlobal(target))
    assert text(view, "retroStatus") == expected
    assert view.findChild(QLabel, "retroStatus").property("verdict") == state
    assert (hand.preview.span.start, hand.preview.span.end) == (600, 720)
    QTest.mouseRelease(chip, Qt.MouseButton.LeftButton, pos=chip.mapFromGlobal(target))
    assert view.findChild(QLabel, "retroStatus").property("verdict") == "ready"


def test_the_status_bar_says_less_rather_than_cutting_its_words(qapp: QApplication) -> None:
    wide = shown(qapp)
    assert [text(wide, name) for name in ("retroStatusNow", "retroStatusWaiting")] == [
        "Thursday 17, 13:40",
        f"1 homework {NOT_PLACED}",
    ]
    narrow = shown(qapp, 800, 700)
    for name in ("retroStatus", "retroStatusNow", "retroStatusWaiting"):
        cell = narrow.findChild(QLabel, name)
        assert cell.fontMetrics().horizontalAdvance(cell.text()) <= cell.contentsRect().width(), cell.text()
    assert text(narrow, "retroStatusWaiting") in (f"1 homework {NOT_PLACED}", f"1 {NOT_PLACED}")


def test_option_colours_repaint_the_desktop_and_the_title_bars(qapp: QApplication) -> None:
    def seen(view: RetroView) -> tuple[str, str]:
        desk = view.findChild(QWidget, "retroDesk")
        bar = view.findChild(QLabel, "retroTitle-week")
        corner = desk.grab().toImage().pixelColor(2, desk.height() - 3).name()
        return corner, bar.grab().toImage().pixelColor(2, 2).name()

    assert seen(shown(qapp, colour="teal")) == ("#008080", "#000080")
    assert seen(shown(qapp, colour="plum")) == ("#5b2a6e", "#4b0082")


def test_match_my_look_puts_the_accent_on_the_desktop_and_the_title_bars() -> None:
    light = palette_of("light")
    colours = scheme(tokens_for("retro", MATCH, light))
    assert colours.desk == colours.title_end == light["accent"]
    assert luminance(colours.title) < luminance(light["accent"]), "the gradient starts darker, as navy does"
    assert (colours.face, colours.field, colours.family) == ("#c0c0c0", "#ffffff", "light")
    dark = palette_of("dark")
    colours = scheme(tokens_for("retro", MATCH, dark))
    assert luminance(dark["window"]) < luminance(colours.desk) < luminance(dark["accent"])
    assert colours.face == "#c0c0c0", "inside the windows it is period silver whatever the look"


def test_high_contrast_is_windows_98s_high_contrast_black() -> None:
    contrasted = palette_of("contrast")
    colours = scheme(tokens_for("retro", MATCH, contrasted))
    assert (colours.face, colours.field, colours.desk) == ("#000000",) * 3
    assert (colours.ink, colours.hi, colours.dark) == ("#ffffff",) * 3
    assert colours.title == colours.title_end == contrasted["accent"]
    assert colours.family == "contrast"


def test_the_teal_desktop_is_windows_98s_own() -> None:
    colours = scheme(tokens_for("retro", "teal", palette_of("light")))
    assert (colours.desk, colours.title, colours.title_end, colours.title_ink) == (
        "#008080",
        "#000080",
        "#1084d0",
        "#ffffff",
    )


def test_every_word_on_retros_colours_reads_in_every_look() -> None:
    """The title bar's words read on both ends of its gradient, the icons' names on the desktop, and
    the words on the silver and white inside the windows, in every look and accent."""
    failures = []
    for pack, dark, preset, accent in itertools.product(PACKS, (False, True), LOOK_PRESETS, ACCENTS):
        palette = resolved_palette(pack, dark, {"preset": preset, "knobs": {}}, accent)
        colours = scheme(tokens_for("retro", MATCH, palette))
        for ink, ground in (
            (colours.title_ink, colours.title),
            (colours.title_ink, colours.title_end),
            (colours.desk_ink, colours.desk),
            (colours.ink, colours.face),
            (colours.ink, colours.field),
            (colours.danger, colours.face),
        ):
            if contrast(ink, ground) < AA_TEXT:
                failures.append((pack, dark, preset, accent, ink, ground, round(contrast(ink, ground), 2)))
    assert failures == []


def test_a_week_block_says_its_start_alone_and_day_its_length_too() -> None:
    drawn = Drawn("school", "School", "class", False, Span(3, 480, 870), 0, 1)
    assert Started(**vars(drawn)).times == "08:00"
    colours = scheme(tokens_for("retro", "teal", palette_of("light")))
    assert RetroPainter(colours).measures["show_lengths"] is False
    assert RetroPainter(colours, wide=True).measures["show_lengths"] is True


def dark_pixels(image: QImage, left: int) -> int:
    return sum(
        image.pixelColor(x, y).lightness() < 60
        for x in range(left, image.width())
        for y in range(image.height())
    )


def test_a_block_with_no_room_for_its_first_word_says_nothing_rather_than_cut_it(qapp: QApplication) -> None:
    """ "Robotics club" in a column too narrow for "Robotics" is its colour alone, not "Robot…"."""
    load_fonts()
    colours = scheme(tokens_for("retro", "teal", palette_of("light")))
    drawn = Drawn("club", "Robotics club", "extra", False, Span(0, 915, 990), 0, 1)

    def painted(width: int) -> int:
        image = QImage(width, 50, QImage.Format.Format_RGB32)
        image.fill(QColor("#ffffff"))
        painter = QPainter(image)
        painter.setFont(QFont("Pixelify Sans", 13))
        RetroPainter(colours).block(painter, QRectF(0, 0, width, 50), drawn, QRectF(0, 0, width, 50))
        painter.end()
        return dark_pixels(image, 4)

    assert painted(160) > 0
    assert painted(56) == 0


def test_a_title_cut_inside_a_word_is_found() -> None:
    def said(*lines: str) -> list[Written]:
        return [Written(line, True, QRectF()) for line in lines]

    assert cuts_a_word(said("Robot…"), "Robotics club")
    assert not cuts_a_word(said("Robotics…"), "Robotics club")
    assert not cuts_a_word(said("Chem lab", "report"), "Chem lab report")
    assert cuts_a_word(said("…"), "Math worksheet")
