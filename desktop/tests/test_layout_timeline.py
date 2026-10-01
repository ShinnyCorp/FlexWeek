"""Timeline, 0.17's Planner spread: the week as a paper planner opened flat, Monday to Wednesday on the
left page and Thursday to Sunday on the right, with the week's figures, the notes and what is due at
the foot of the pages; Day as one page of hours with its notes on the facing page."""

from __future__ import annotations

import importlib.util
import os
import re
import time
from collections.abc import Iterator
from dataclasses import replace
from itertools import product

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK, block

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    import shiboken6
    from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFontMetricsF, QMouseEvent, QPainter, QTextDocument
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    from desktop.native.calendar import CATEGORIES
    from desktop.native.fonts import load_fonts
    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.canvas import Drawn
    from desktop.native.hours.chips import TrayChip
    from desktop.native.hours.geometry import Axis, Span
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.base import Scene, family
    from desktop.native.layouts.registry import options_for, tokens_for
    from desktop.native.layouts.timeline import (
        Due,
        Split,
        TimelineCanvas,
        TimelinePainter,
        TimelineView,
        due_this_week,
        week_figures,
    )
    from desktop.native.look import (
        AA_TEXT,
        PACKS,
        block_time_colour,
        category_paint,
        mix_oklab,
        resolved_palette,
    )
    from desktop.native.tokens import contrast
    from desktop.native.weekmodel import build_week, minute_of
    from desktop.native.widgets import FittedLabel

THURSDAY = 3
HOSTS: list = []


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-timeline-test"])
    yield application


def scene_of(
    tab: str = "week",
    clock: str = "13:40",
    blocks: list[dict] | None = None,
    homework: dict | None = None,
    palette: dict | None = None,
    today: int = THURSDAY,
    **chosen: str,
) -> Scene:
    options = {**options_for(None, "timeline"), **chosen}
    palette = palette or resolved_palette("light-frost", False, None, "default")
    week = build_week(
        WEEK, BLOCKS if blocks is None else blocks, HOMEWORK if homework is None else homework, TRACE
    )
    return Scene(
        week,
        today,
        minute_of(clock),
        options,
        tokens_for("timeline", options["colour"], palette),
        surface=tab,
        iso_day=week.date_of(today).isoformat(),
    )


def shown(
    qapp: QApplication, tab: str = "week", size: tuple[int, int] = (1280, 744), **given
) -> TimelineView:
    load_fonts()
    host = QWidget()
    HOSTS.append(host)
    # The window's stylesheet gives every widget the body face at Normal text, and what fits in a
    # block depends on it.
    host.setStyleSheet("QWidget { font-family: Inter; font-size: 13pt; }")
    QVBoxLayout(host).setContentsMargins(0, 0, 0, 0)
    view = TimelineView()
    host.layout().addWidget(view)
    host.resize(*size)
    view.show_week(scene_of(tab, **given))
    host.show()
    for _ in range(3):
        qapp.processEvents()
    return view


def canvas(view: TimelineView) -> TimelineCanvas:
    found = view.hours_surfaces()
    assert len(found) == 1 and isinstance(found[0], TimelineCanvas)
    return found[0]


def scroll_of(view: TimelineView) -> HoursScroll:
    area = canvas(view)._scroll_area()
    assert isinstance(area, HoursScroll)
    return area


def page_of(view: TimelineView) -> QScrollArea:
    return view.findChild(QScrollArea, "timelineScroll")


def texts(view: TimelineView, name: str) -> list[str]:
    return [item.text() for item in view.findChildren(QLabel, name) if item.isVisible()]


def plain(item: QLabel) -> str:
    """A label's words as read, without the markup that colours some of them."""
    document = QTextDocument()
    document.setHtml(item.text())
    return document.toPlainText()


def near(colour: QColor, hex_colour: str, within: int = 8) -> bool:
    other = QColor(hex_colour)
    return (
        max(
            abs(colour.red() - other.red()),
            abs(colour.green() - other.green()),
            abs(colour.blue() - other.blue()),
        )
        <= within
    )


class Seen:
    """The view as drawn, read at points of one of its widgets. The hours paint only blocks and
    rules; the paper under them is the spread's, so a picture of the canvas alone would not show it."""

    def __init__(self, view: TimelineView) -> None:
        self.view, self.image = view, view.grab().toImage()

    def at(self, widget: QWidget, point: QPoint) -> QColor:
        return self.image.pixelColor(widget.mapTo(self.view, point))

    def inside(self, hours: TimelineCanvas, block_id: str, day: int) -> QColor:
        """Near a block's bottom right, clear of its words and its edges."""
        box = hours.block_rect(block_id, day)
        return self.at(hours, hours.mapFromGlobal(box.bottomRight()) - QPoint(8, min(5, box.height() // 2)))


class Said(QPainter):
    """Every text the hours draw, as they draw it."""

    words: list[str] = []

    def drawText(self, *args) -> None:  # noqa: N802
        Said.words.append(next(arg for arg in reversed(args) if isinstance(arg, str)))
        super().drawText(*args)


def drawn_words(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, view: TimelineView) -> list[str]:
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    Said.words = []
    canvas(view).repaint()
    return list(Said.words)


# Week: two pages of columns


def test_week_is_seven_columns_on_two_pages_of_one_canvas(qapp: QApplication) -> None:
    view = shown(qapp)
    hours = canvas(view)
    assert [(track.day, track.axis, track.first, track.last) for track in hours.tracks] == [
        (day, Axis.DOWN, 0, 1440) for day in range(7)
    ]
    assert hours.hand is view.hand and scroll_of(view).axis is Axis.DOWN
    areas = {track.day: track.area for track in hours.tracks}
    fold = hours.width() / 2
    assert areas[2].right() < fold < areas[3].left(), "Wednesday ends and Thursday starts at the gutter"
    assert areas[3].left() - areas[2].right() >= 40, "the gutter between the pages"
    assert {(round(area.top()), round(area.height())) for area in areas.values()} == {
        (round(areas[0].top()), round(areas[0].height()))
    }, "one set of hour rules runs across both pages"
    left, right = [areas[day].width() for day in (0, 1, 2)], [areas[day].width() for day in (3, 4, 5, 6)]
    assert max(left) - min(left) < 1 and max(right) - min(right) < 1


def test_each_days_name_sits_over_its_column_and_opens_it(qapp: QApplication) -> None:
    view = shown(qapp)
    hours = canvas(view)
    for track in hours.tracks:
        heading = view.findChild(QPushButton, f"timelineWeekDay{track.day}")
        centre = heading.mapToGlobal(heading.rect().center())
        column = hours.mapToGlobal(track.area.center().toPoint())
        assert abs(centre.x() - column.x()) <= 2, track.day
        assert hours.day_name(track.day) == centre
    names = [view.findChild(QPushButton, f"timelineWeekDay{day}").title.text() for day in range(7)]
    assert names == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert texts(view, "timelineChip") == ["17"], "today's date is the one chip"
    assert texts(view, "timelineDate") == ["14", "15", "16", "18", "19", "20"]
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    QTest.mouseClick(view.findChild(QPushButton, "timelineWeekDay4"), Qt.MouseButton.LeftButton)
    assert opened == ["2026-09-18"]


@pytest.mark.parametrize("size", [(1280, 744), (800, 700)])
def test_a_days_name_shortens_before_it_is_cut_and_its_date_follows_it(
    qapp: QApplication, size: tuple[int, int]
) -> None:
    view = shown(qapp, size=size)
    for day, short in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
        heading = view.findChild(QPushButton, f"timelineWeekDay{day}")
        title = heading.title
        words = title.fontMetrics().horizontalAdvance(title.text())
        assert "…" not in title.text() and title.text().startswith(short), title.text()
        assert words <= title.width()
        tag = heading.chip if heading.chip.isVisible() else heading.date
        gap = tag.geometry().left() - (title.geometry().left() + words)
        assert gap <= 10, f"{short}'s date is {gap} pixels after its name"
        assert tag.geometry().right() <= heading.width()


# Blocks


@pytest.mark.parametrize("colour", ["match", "paper", "night"])
def test_every_block_is_filled_with_its_category_colour(qapp: QApplication, colour: str) -> None:
    """School, Dinner and homework alike: the one fill the other designs give each category, in every
    colourway, where School was the page's colour in a card."""
    view = shown(qapp, colour=colour)
    hours = canvas(view)
    tokens = view.scene.tokens

    def fill(category: str) -> str:
        return category_paint(category, {"family": family(tokens), "panel": tokens["surface"]})[0]

    seen = Seen(view)
    assert near(seen.inside(hours, "essay-1", 3), fill("assignments"))
    assert near(seen.inside(hours, "school", 3), fill("class"))
    assert near(seen.inside(hours, "dinner", 3), fill("meals"))
    assert not near(seen.inside(hours, "school", 3), tokens["surface"], 4)


def test_a_blocks_words_and_times_read_on_its_fill_in_every_colourway() -> None:
    """The title in the page's text colour and the times a little quieter, on every category's fill, in
    the design's two colourways and in Match my look over every pack, dark or light."""
    looks = [(pack, dark) for pack in PACKS for dark in (False, True)]
    for colour, (pack, dark) in product(("paper", "night", "match"), looks):
        palette = resolved_palette(pack, dark, None, "default")
        tokens = tokens_for("timeline", colour, palette)
        painter = TimelinePainter(tokens)
        for name in CATEGORIES:
            drawn = Drawn("block", "Block", name, False, Span(0, 600, 660), 0, 1)
            fill, ink, _outline, _mark = (item.name() if item else None for item in painter.fills(drawn))
            where = f"{colour}/{pack}/{dark} {name}"
            assert fill != tokens["surface"], f"{where}: the block is the page's colour"
            assert contrast(ink, fill) >= AA_TEXT, f"{where}: its title"
            assert contrast(block_time_colour(ink, fill), fill) >= AA_TEXT, f"{where}: its times"


def test_every_block_is_outlined_in_ink_with_its_category_down_its_start_edge(qapp: QApplication) -> None:
    view = shown(qapp)
    hours = canvas(view)
    tokens = view.scene.tokens
    box = hours.block_rect("school", 3)
    local = hours.mapFromGlobal(box.topLeft())
    seen = Seen(view)
    mark = category_paint("class", {"family": "light", "panel": tokens["surface"]})[1]
    assert near(seen.at(hours, local + QPoint(1, box.height() // 2)), mark, 12)
    # A one-pixel line on a column a fraction of a pixel wide shares its ink between two pixels.
    edge = min(seen.at(hours, local + QPoint(box.width() - x, box.height() // 2)).lightness() for x in (1, 2))
    ink, fill = QColor(mix_oklab(tokens["text"], tokens["surface"], 0.78)), QColor(
        category_paint("class", {"family": "light", "panel": tokens["surface"]})[0]
    )
    assert edge <= (ink.lightness() + fill.lightness()) / 2, "no ink round the block"


def test_the_weeks_blocks_say_their_times_and_days_say_their_length_too(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    week = drawn_words(qapp, monkeypatch, shown(qapp))
    assert "08:00–14:30" in week and not any("6 h 30 min" in words for words in week)
    day = drawn_words(qapp, monkeypatch, shown(qapp, "day"))
    assert any("6 h 30 min" in words for words in day)


def test_a_half_hour_on_day_says_its_name_and_times_in_the_caption_size(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At Day's 45 pixels an hour a half-hour is too short for a line at the body size; the mock-up
    writes it smaller rather than leave Dinner a coloured bar."""
    said = drawn_words(qapp, monkeypatch, shown(qapp, "day"))
    assert "Dinner" in said and "18:00–18:30" in said


def test_now_is_a_line_across_todays_column_with_its_time(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = shown(qapp, clock="15:40")
    assert "15:40" in drawn_words(qapp, monkeypatch, view)
    hours = canvas(view)
    accent = view.scene.tokens["now"]
    at = hours.mapFromGlobal(hours.point_for(THURSDAY, 15 * 60 + 40))
    friday = hours.mapFromGlobal(hours.point_for(4, 15 * 60 + 40))
    seen = Seen(view)
    assert near(seen.at(hours, at + QPoint(30, 0)), accent, 24)
    assert not any(near(seen.at(hours, friday + QPoint(0, dy)), accent, 40) for dy in range(-2, 3))
    assert "15:40" in drawn_words(qapp, monkeypatch, shown(qapp, "day", clock="15:40"))


class Placed(QPainter):
    """Every text the hours draw, the box it was given and where its words lie, in the canvas's own
    pixels."""

    said: list[tuple[str, QRectF, QRectF]] = []

    def drawText(self, *args) -> None:  # noqa: N802
        if isinstance(args[0], QRectF):
            flags = getattr(args[1], "value", args[1])
            ink = QFontMetricsF(self.font()).boundingRect(args[0], int(flags), args[-1])
            turned = self.transform()
            Placed.said.append((args[-1], turned.mapRect(args[0]), turned.mapRect(ink)))
        super().drawText(*args)


@pytest.mark.parametrize("today", range(7))
@pytest.mark.parametrize(("tab", "density"), [("week", "roomy"), ("week", "compact"), ("day", "roomy")])
def test_the_time_now_is_on_a_pill_clear_of_every_block_and_hour_label(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, today: int, tab: str, density: str
) -> None:
    """At 10:05, with School on every day. Beside today's own column the pill lay on the day
    before and covered its School, and on Day it lay over the 10:00 label and the start of School.
    It is beside the hour labels, in place of the one it is nearest, or for a day on the right page
    in that page's margin at the fold."""
    school = block("school", "locked", list(range(7)), "08:00", 390, title="School", category="class")
    options = {"density": "compact"} if density == "compact" else {}
    view = shown(qapp, tab, clock="10:05", today=today, blocks=[school], **options)
    hours = canvas(view)
    monkeypatch.setattr(canvas_module, "QPainter", Placed)
    Placed.said = []
    hours.repaint()
    # Drawn again wherever the line crosses a block, clipped to it: each time clear of both.
    pills = [box for words, box, _ink in Placed.said if words.endswith("10:05")]
    assert pills
    blocks = [track.transform.mapRect(rect) for track in hours.tracks for _item, rect in hours.drawn(track)]
    assert len(blocks) == (7 if tab == "week" else 1)
    labels = [(words, ink) for words, _box, ink in Placed.said if re.fullmatch(r"\d\d:00", words)]
    assert len(labels) >= 10
    for pill in pills:
        assert pill.left() >= 0 and pill.right() <= hours.width()
        assert [box for box in blocks if box.intersects(pill)] == [], f"the pill at {pill} covers a block"
        assert [words for words, ink in labels if ink.intersects(pill)] == [], "the pill covers an hour label"


def test_two_blocks_at_one_time_go_half_width(qapp: QApplication) -> None:
    view = shown(qapp, "day", blocks=[*BLOCKS, block("quiz", "locked", [3], "18:00", 30)])
    hours = canvas(view)
    track = hours.tracks[0]
    boxes = {item.block_id: rect for item, rect in hours.drawn(track) if item.block_id in {"dinner", "quiz"}}
    dinner, quiz = boxes["dinner"], boxes["quiz"]
    assert abs(dinner.width() - quiz.width()) < 1
    assert dinner.width() < track.area.width() / 2
    assert dinner.right() <= quiz.left() or quiz.right() <= dinner.left()


# The foot of the pages


def test_the_left_pages_foot_gives_the_week_in_figures_and_what_is_next(qapp: QApplication) -> None:
    view = shown(qapp)
    assert "This week" in texts(view, "timelineLabel")
    assert list(zip(texts(view, "timelineStat"), texts(view, "timelineStatWord"), strict=True)) == [
        ("3 h 15 min", "homework planned"),
        ("1 of 4", "done"),
        ("1", "not placed yet"),
    ]
    (line,) = view.findChildren(QLabel, "timelineNext")
    assert plain(line) == "Next Dinner at 18:00, in 4 h 20 min"


def test_the_paper_shows_under_the_hours_and_the_notes_outside_the_window_too(qapp: QApplication) -> None:
    """Setup draws each design outside the window. A scroll area fills what it holds with Qt's grey,
    which covered the pages under the hours and behind Day's notes."""
    for tab in ("week", "day"):
        view = TimelineView()
        HOSTS.append(view)
        view.resize(1280, 744)
        view.show_week(scene_of(tab))
        view.show()
        qapp.processEvents()
        hours = canvas(view)
        paper = view.scene.tokens["surface"]
        seen = Seen(view)
        assert seen.at(hours, QPoint(3, round(hours.tracks[0].point_for(12 * 60 + 30).y()))).name() == paper
        if tab == "day":
            notes = view.findChild(QWidget, "timelineNotesPage")
            assert seen.at(notes, QPoint(notes.width() - 3, 3)).name() == paper


def test_the_gutter_is_plain_paper_either_side_of_the_fold_line(qapp: QApplication) -> None:
    """The fold is one line. The shade that once darkened the pages toward it is gone."""
    for tab in ("week", "day"):
        view = shown(qapp, tab)
        spread = view.findChild(QWidget, f"timeline{tab.title()}Spread")
        paper = view.scene.tokens["surface"]
        seen = Seen(view)
        fold, middle = spread.width() // 2, spread.height() // 2
        assert [
            reach
            for reach in (3, 8, 14)
            for side in (-1, 1)
            if seen.at(spread, QPoint(fold + side * reach, middle)).name() != paper
        ] == [], f"{tab}: paper either side of the fold"
        line = [seen.at(spread, QPoint(fold + beside, middle)).name() for beside in (-1, 0)]
        assert line != [paper, paper], f"{tab}: the fold line stays"


def test_the_right_pages_foot_holds_the_notes_and_what_is_due_this_week(qapp: QApplication) -> None:
    view = shown(qapp)
    assert texts(view, "timelineTrayLabel") == ["Not placed yet"]
    notes = [chip for chip in view.findChildren(TrayChip) if chip.isVisible()]
    assert [(chip.held.title, chip.hand is view.hand, chip.text()) for chip in notes] == [
        ("Poster-1", True, "Poster-1")
    ]
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    QTest.mouseClick(notes[0], Qt.MouseButton.LeftButton)
    assert opened == ["poster-1"]
    rows = [
        (row.findChild(FittedLabel, "timelineDueTitle").full_text(), row.findChild(QLabel, "timelineDueWhen"))
        for row in view.findChildren(QWidget, "timelineDueRow")
        if row.isVisible()
    ]
    assert [(title, when.text()) for title, when in rows] == [
        ("Poster-1", "Not placed yet"),
        ("Math-1", "Mon 15:45"),
        ("Essay-1", "Thu 18:45"),
        ("Chem-1", "Thu 20:00"),
    ]
    assert [bool(when.property("open")) for _title, when in rows] == [True, False, False, False]


def test_what_waits_is_listed_first_and_what_is_due_later_is_left_out() -> None:
    blocks = [
        *BLOCKS,
        # Two sessions of the essay, one of them still waiting: the essay is not placed yet.
        block("essay-2", "flexible", [], None, 30, assignment_id="essay", title="Essay-2"),
        block("lab-1", "flexible", [4], "16:00", 60, assignment_id="lab", title="Lab write-up"),
    ]
    homework = {
        **HOMEWORK,
        "lab": {"id": "lab", "title": "Lab", "due": "2026-09-22T23:59", "completed": False},
    }
    listed = due_this_week(build_week(WEEK, blocks, homework, TRACE))
    assert listed == [
        Due("Essay-2", None),
        Due("Poster-1", None),
        Due("Math-1", (0, 15 * 60 + 45)),
        Due("Chem-1", (3, 20 * 60)),
    ]


def test_the_weeks_figures_count_homework_whole_not_its_sessions() -> None:
    blocks = [
        *BLOCKS,
        # A second session of the finished math worksheet, not itself finished.
        block("math-2", "flexible", [2], "16:00", 30, assignment_id="math"),
    ]
    figures = week_figures(
        build_week(WEEK, blocks, {**HOMEWORK, "math": {**HOMEWORK["math"], "completed": False}}, TRACE)
    )
    assert figures == (("3 h 45 min", "homework planned"), ("0 of 4", "done"), ("1", "not placed yet"))
    empty = week_figures(build_week(WEEK, [BLOCKS[0]], {}, None))
    assert empty == (("0 min", "homework planned"), ("0", "done"), ("0", "not placed yet"))


def test_with_nothing_waiting_and_nothing_due_the_foot_says_so(qapp: QApplication) -> None:
    view = shown(qapp, blocks=[BLOCKS[0], BLOCKS[1]], homework={})
    assert texts(view, "timelineHint") == ["Nothing is waiting for a time.", "Nothing is due this week."]
    assert view.findChildren(TrayChip) == []


@pytest.mark.parametrize(("size", "direction"), [((1280, 744), "side"), ((800, 700), "under")])
def test_the_notes_and_what_is_due_sit_side_by_side_or_one_under_the_other(
    qapp: QApplication, size: tuple[int, int], direction: str
) -> None:
    view = shown(qapp, size=size)
    split = view.findChild(Split, "timelineNotesSplit")
    wanted = QBoxLayout.Direction.LeftToRight if direction == "side" else QBoxLayout.Direction.TopToBottom
    assert split.box.direction() == wanted
    for title in view.findChildren(FittedLabel, "timelineDueTitle"):
        assert title.text() == title.full_text(), title.text()


# Day: the day's page and its notes


def test_day_is_one_column_of_the_whole_day_on_the_left_page_and_its_notes_on_the_right(
    qapp: QApplication,
) -> None:
    view = shown(qapp, "day")
    hours = canvas(view)
    assert [(track.day, track.axis, track.first, track.last) for track in hours.tracks] == [
        (THURSDAY, Axis.DOWN, 0, 1440)
    ]
    assert [
        key for key in ("school", "dinner", "essay-1", "chem-1") if hours.block_rect(key, 3) is None
    ] == []
    fold = view.findChild(QWidget, "timelineDaySpread")
    middle = fold.mapToGlobal(QPoint(fold.width() // 2, 0)).x()
    notes = view.findChild(QWidget, "timelineNotesPage")
    assert hours.mapToGlobal(QPoint(hours.width(), 0)).x() < middle < notes.mapToGlobal(QPoint(0, 0)).x()
    heading = view.findChild(QPushButton, "timelineDayHead")
    assert (heading.title.text(), heading.chip.text(), heading.chip.isVisible()) == ("Thursday", "17", True)


def test_day_sums_the_day_up_says_what_is_next_and_lists_what_is_due_with_nothing_to_write_in(
    qapp: QApplication,
) -> None:
    view = shown(qapp, "day")
    assert texts(view, "timelineLabel") == ["Today", "Next", "Due this week"]
    assert texts(view, "timelineTrayLabel") == ["Not placed yet"]
    assert texts(view, "timelineSum") == ["2 h 30 min planned · 0 done"]
    shares = list(zip(texts(view, "timelineShare"), texts(view, "timelineShareLength"), strict=True))
    assert shares == [("School", "6 h 30 min"), ("Meals", "30 min"), ("Homework", "2 h 30 min")]
    (line,) = view.findChildren(QLabel, "timelineNext")
    assert plain(line) == "Dinner at 18:00, in 4 h 20 min"
    # No ruled space for notes: it looked writable and kept nothing.
    assert view.findChild(QWidget, "timelineRuled") is None
    assert [chip.held.title for chip in view.findChildren(TrayChip) if chip.isVisible()] == ["Poster-1"]


def test_another_day_is_named_for_itself_and_claims_no_next(qapp: QApplication) -> None:
    view = shown(qapp, "day")
    kept = scroll_of(view)
    view.show_week(replace(view.scene, iso_day="2026-09-14"))
    qapp.processEvents()
    assert texts(view, "timelineLabel") == ["Monday", "Due this week"]
    assert view.findChild(QPushButton, "timelineDayHead").title.text() == "Monday"
    assert [track.day for track in canvas(view).tracks] == [0]
    assert scroll_of(view) is kept


# The hours: kept, zoomed, and reached


def test_the_hours_are_kept_through_renders_and_tabs(qapp: QApplication) -> None:
    view = shown(qapp)
    week = scroll_of(view)
    week.zoom_by(1)
    view.show_week(replace(view.scene, minute=view.scene.minute + 1))
    view.show_week(replace(view.scene, surface="day"))
    day = scroll_of(view)
    view.show_week(replace(view.scene, surface="week"))
    qapp.processEvents()
    assert scroll_of(view) is week and week.px == 48
    assert day is not week and shiboken6.isValid(day) and not day.isVisible()


def test_parked_hours_die_with_the_window(qapp: QApplication) -> None:
    host = QWidget()
    view = TimelineView(host)
    QVBoxLayout(host).addWidget(view)
    view.show_week(scene_of("day"))
    host.show()
    qapp.processEvents()
    parked = scroll_of(view)
    view.show_week(scene_of("week"))
    assert shiboken6.isValid(parked) and not parked.isVisible()
    host.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(parked)


def test_the_week_opens_at_the_mock_ups_scale_and_not_at_a_level_kept_for_the_old_lines(
    qapp: QApplication,
) -> None:
    """0.16's lanes kept an hour's width across a line as `timeline.week`; opened as the columns'
    height it put the planner at twice its size."""
    view = TimelineView()
    view.remembered_zoom = {"timeline.week": 96}
    view.resize(1280, 744)
    view.show_week(scene_of())
    view.show()
    assert scroll_of(view).px == 36
    assert scroll_of(shown(qapp, "day")).px == 45


def test_a_new_text_size_makes_the_week_again_at_the_zoom_the_window_remembers(qapp: QApplication) -> None:
    view = shown(qapp)
    first = scroll_of(view)
    view.remembered_zoom = {"timeline.spread": 64}
    view.show_week(replace(view.scene, scale=1.25))
    qapp.processEvents()
    again = scroll_of(view)
    assert again is not first and again.px == 64
    name = view.findChild(QPushButton, "timelineWeekDay2").title
    assert name.fontMetrics().horizontalAdvance(name.text()) <= name.width()


def test_the_hours_are_no_taller_than_the_day_and_the_foot_follows_them(qapp: QApplication) -> None:
    view = shown(qapp, size=(1280, 1400))
    scroll = scroll_of(view)
    scroll.zoom_by(-1)
    qapp.processEvents()
    hours = canvas(view)
    assert scroll.px == 28
    assert scroll.viewport().height() <= hours.height(), "no empty page under the end of the day"
    foot = view.findChild(QWidget, "timelineWeekFoot")
    bottom = scroll.mapTo(view, QPoint(0, scroll.height())).y()
    assert 0 <= foot.mapTo(view, QPoint(0, 0)).y() - bottom <= 12


def test_a_week_taller_than_the_window_scrolls_and_every_day_can_be_reached(qapp: QApplication) -> None:
    view = shown(qapp, size=(1150, 300))
    page, hours = page_of(view), canvas(view)
    assert page.verticalScrollBar().maximum() > 0, "the pages are taller than the window"
    page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
    hours.reveal(6, 21 * 60, 22 * 60)
    qapp.processEvents()
    assert hours.in_view(6, 21 * 60) and hours.in_view(6, 22 * 60)
    hours.reveal(0, 7 * 60, 8 * 60)
    qapp.processEvents()
    assert hours.in_view(0, 7 * 60) and not hours.in_view(6, 22 * 60)


def test_a_block_rested_at_the_top_of_the_hours_scrolls_them_back(qapp: QApplication) -> None:
    """Inside the offscreen screen (800 by 800), where the hand can find what is under the pointer."""
    view = TimelineView()
    view.move(0, 0)
    view.resize(780, 560)
    view.show_week(scene_of())
    view.show()
    qapp.processEvents()
    hours, scroll = canvas(view), scroll_of(view)
    hours.reveal(3, 19 * 60, 20 * 60)
    qapp.processEvents()
    bar = scroll.verticalScrollBar()
    before = bar.value()
    assert before > 0
    grab = hours.block_rect("essay-1", 3).center()
    edge = QPoint(grab.x(), scroll.viewport().mapToGlobal(QPoint(0, 10)).y())

    def send(kind: QEvent.Type, at: QPoint, held: bool) -> None:
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        local = QPointF(hours.mapFromGlobal(at))
        QApplication.sendEvent(
            hours,
            QMouseEvent(
                kind, local, QPointF(at), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier
            ),
        )

    send(QEvent.Type.MouseButtonPress, grab, True)
    for step in range(1, 9):
        send(QEvent.Type.MouseMove, grab + (edge - grab) * step / 8, True)
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and bar.value() >= before:
        qapp.processEvents()
    assert bar.value() < before, "rested at the top of the hours: they scroll back"
    view.hand.cancel()


# Options and colours


def test_option_finished_hidden_drops_what_is_over(qapp: QApplication) -> None:
    def drawn(view: TimelineView) -> list[str]:
        return sorted(
            {item.block_id for track in canvas(view).tracks for item, _ in canvas(view).drawn(track)}
        )

    assert drawn(shown(qapp, clock="19:00")) == ["chem-1", "dinner", "essay-1", "math-1", "school"]
    assert drawn(shown(qapp, clock="19:00", finished="hide")) == ["chem-1", "dinner", "essay-1", "school"]
    assert drawn(shown(qapp, "day", clock="19:00", finished="hide")) == ["chem-1", "essay-1"]


def test_option_compact_gives_the_hours_more_of_the_page(qapp: QApplication) -> None:
    roomy, tight = scroll_of(shown(qapp)), scroll_of(shown(qapp, density="compact"))
    assert tight.height() > roomy.height()


def test_ruled_paper_and_night_repaint_the_page_and_keep_flexweeks_blue(qapp: QApplication) -> None:
    def corner(view: TimelineView) -> str:
        return view.grab().toImage().pixelColor(5, 5).name()

    assert corner(shown(qapp, colour="paper")) == "#fdfbf7"
    assert corner(shown(qapp, colour="night")) == "#14161c"
    gold = resolved_palette("light-frost", False, None, "gold")
    assert tokens_for("timeline", "paper", gold)["accent"] == "#3d6fc4"
    assert tokens_for("timeline", "night", gold)["accent"] == "#7fa8ff"


def test_its_own_colourways_set_the_names_and_figures_in_newsreader(qapp: QApplication) -> None:
    """The catalogue's Classic Elegant pairing. In Match my look they take the look's heading face,
    which the window's stylesheet gives them (look.HEADING_NAMES)."""

    def faces(view: TimelineView) -> set[str]:
        found = [*view.findChildren(QLabel, "timelineDayName"), *view.findChildren(QLabel, "timelineStat")]
        return {item.font().family() for item in found}

    assert faces(shown(qapp, colour="paper")) == {"Newsreader"}
    assert "Newsreader" not in faces(shown(qapp))
