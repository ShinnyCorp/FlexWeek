"""Retro desktop: live hours in movable windows, with reachable waiting homework."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK, block

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QWidget

    from desktop.native.hours.chips import TrayChip
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.registry import options_for, tokens_for
    from desktop.native.layouts.retro import RetroView
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week, minute_of


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-retro-test"])
    yield application


def scene(
    clock: str = "13:40",
    blocks: list[dict] | None = None,
    *,
    surface: str = "week",
    iso_day: str = "",
    scale: float = 1.0,
    **chosen: str,
) -> Scene:
    options = {**options_for(None, "retro"), **chosen}
    palette = resolved_palette("light-frost", False, None, "default")
    week = build_week(WEEK, blocks or BLOCKS, HOMEWORK, TRACE)
    return Scene(
        week,
        3,
        minute_of(clock),
        options,
        tokens_for("retro", options["colour"], palette),
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
    return sorted(
        item.objectName() for item in view.findChildren(QFrame) if item.property("role") == "window"
    )


def test_three_windows_open_and_the_taskbar_says_so(qapp: QApplication) -> None:
    view = shown(qapp)
    assert windows(view) == ["retroWindow-next", "retroWindow-notes", "retroWindow-week"]
    tasks = [view.findChild(QPushButton, f"retroTask-{key}") for key in ("week", "notes", "next")]
    assert [(task.text(), task.property("open")) for task in tasks] == [
        ("Week.exe", "true"),
        ("deadlines.txt", "true"),
        ("Up next", "true"),
    ]
    assert view.findChild(QLabel, "retroClock").text() == "13:40"


@pytest.mark.parametrize(("width", "height", "scale"), [(1280, 820, 1.0), (1150, 768, 1.4)])
def test_day_opens_schedule_with_one_live_column(
    qapp: QApplication, width: int, height: int, scale: float
) -> None:
    view = shown(qapp, width, height, surface="day", iso_day="2026-09-17", scale=scale)
    assert view.findChild(QLabel, "retroTitle-week").text() == "Schedule.exe — Thursday 17"
    assert view.findChild(QPushButton, "retroTask-week").text() == "Schedule.exe"
    scroll = view.findChild(HoursScroll, "retroDayScroll")
    assert scroll is not None
    assert [track.day for track in scroll.canvas.tracks] == [3]
    assert scroll.canvas.hand is view.hand
    assert scroll.canvas.block_rect("school", 3) is not None
    chip = view.findChild(TrayChip, "retroNoteWaiting0")
    assert chip.isVisible()
    corner = chip.mapTo(view, QPoint(chip.width(), chip.height()))
    assert corner.x() <= view.width() and corner.y() <= view.height()


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


def test_a_window_closes_and_the_taskbar_brings_it_back(qapp: QApplication) -> None:
    view = shown(qapp)
    view.findChild(QPushButton, "retroClose-notes").click()
    assert windows(view) == ["retroWindow-next", "retroWindow-week"]
    assert view.findChild(QPushButton, "retroTask-notes").property("open") == "false"
    view.findChild(QPushButton, "retroTask-notes").click()
    assert "retroWindow-notes" in windows(view)


def test_ok_dismisses_up_next_and_it_says_what_is_coming(qapp: QApplication) -> None:
    view = shown(qapp)
    assert view.findChild(QLabel, "retroNextText").text() == "Dinner starts at 18:00, in 4 h 20 min."
    view.findChild(QPushButton, "retroNextOk").click()
    assert windows(view) == ["retroWindow-notes", "retroWindow-week"]


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
        block(
            "shift",
            "locked",
            [5],
            "09:00",
            240,
            title="Saturday shift at the cafe",
            category="extra",
        ),
        block(
            "choir",
            "locked",
            [6],
            "10:00",
            180,
            title="Sunday choir practice and coffee",
            category="extra",
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


def test_the_notepad_flags_squeezed_work_and_shows_a_live_waiting_chip(qapp: QApplication) -> None:
    view = shown(qapp)
    lines = [view.findChild(QPushButton, f"retroNote{index}").text() for index in range(2)]
    assert [line[:2] for line in lines] == ["!!", " !"]
    chip = view.findChild(TrayChip, "retroNoteWaiting0")
    assert chip.block_id == "poster-1"
    assert chip.hand is view.hand


def test_what_has_no_time_is_shown_once_in_the_notepad_or_under_the_hours_when_it_is_closed(
    qapp: QApplication,
) -> None:
    view = shown(qapp)
    waiting = [chip.objectName() for chip in view.findChildren(TrayChip) if chip.block_id == "poster-1"]
    assert waiting == ["retroNoteWaiting0"]
    QTest.mouseClick(view.findChild(QPushButton, "retroClose-notes"), Qt.MouseButton.LeftButton)
    waiting = [chip.objectName() for chip in view.findChildren(TrayChip) if chip.block_id == "poster-1"]
    assert waiting == ["retroWaiting0"]
    assert view.findChild(TrayChip, "retroWaiting0").isVisible()
    QTest.mouseClick(view.findChild(QPushButton, "retroTask-notes"), Qt.MouseButton.LeftButton)
    waiting = [chip.objectName() for chip in view.findChildren(TrayChip) if chip.block_id == "poster-1"]
    assert waiting == ["retroNoteWaiting0"]


def test_a_notepad_line_short_of_room_puts_its_date_under_its_title(qapp: QApplication) -> None:
    """At 1150x768 with large text a long line read "History essay Sun 27 Se", cut by the page. A
    line that fits stays one line; one that does not puts its date, whole, on a line of its own."""
    long = [
        item if item["id"] != "essay-1" else {**item, "title": "History essay on the causes of the war"}
        for item in BLOCKS
    ]
    view = shown(qapp, 1150, 768, blocks=long, scale=1.4)
    qapp.processEvents()
    pad = view.findChild(QFrame, "retroWindow-notes")
    short, long_line = (view.findChild(QPushButton, f"retroNote{index}") for index in range(2))
    assert short.text() == "!! Chem-1  Thu 17 Sep"
    lines = long_line.text().split("\n")
    assert len(lines) == 2, f"{long_line.text()!r} is one line"
    assert lines[0].startswith(" ! History essay") and lines[1] == "   Fri 18 Sep, 21:00", lines
    for line in (short, long_line):
        need = QPushButton.sizeHint(line)
        assert need.width() <= line.width() and need.height() <= line.height(), f"{line.text()!r} is cut"
        assert line.mapTo(pad, QPoint(line.width(), line.height())).x() <= pad.width()
        assert line.mapTo(pad, QPoint(line.width(), line.height())).y() <= pad.height()


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
    assert (week.px, week.verticalScrollBar().value()) == (80, 180)
    view.show_week(scene("13:41", surface="day", iso_day="2026-09-17"))
    day = view.findChild(HoursScroll, "retroDayScroll")
    assert day is not None and day is not week
    assert week.parentWidget() is not None
    view.show_week(scene("13:42"))
    assert view.findChild(HoursScroll, "retroWeekScroll") is week
    assert day.parentWidget() is not None
    assert (week.px, week.verticalScrollBar().value()) == (80, 180)


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
    scroll = view.findChild(HoursScroll, "retroWeekScroll")
    scroll.scroll_to(10 * 60)
    qapp.processEvents()
    chip = view.findChild(TrayChip, "retroWaiting0")
    target = scroll.canvas.point_for(3, 10 * 60)
    QTest.mousePress(chip, Qt.MouseButton.LeftButton, pos=chip.rect().center())
    QTest.mouseMove(chip, chip.mapFromGlobal(target))
    assert view.findChild(QLabel, "retroStatus").text() == expected
    assert view.findChild(QLabel, "retroStatus").property("verdict") == state
    assert (hand.preview.span.start, hand.preview.span.end) == (600, 720)
    QTest.mouseRelease(chip, Qt.MouseButton.LeftButton, pos=chip.mapFromGlobal(target))
    assert view.findChild(QLabel, "retroStatus").property("verdict") == "ready"


def test_option_colours_repaint_the_desktop_and_the_title_bars(qapp: QApplication) -> None:
    def seen(view: RetroView) -> tuple[str, str]:
        bar = view.findChild(QLabel, "retroTitle-week")
        return view.grab().toImage().pixelColor(
            2, view.height() // 2
        ).name(), bar.grab().toImage().pixelColor(2, 2).name()

    assert seen(shown(qapp, colour="teal")) == ("#008080", "#000080")
    assert seen(shown(qapp, colour="plum")) == ("#5b2a6e", "#4b0082")
