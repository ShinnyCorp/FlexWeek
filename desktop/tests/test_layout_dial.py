"""Day dial, the clock-face day screen. The face is painted, so the tests hold it to what can be seen
and reached: a click on a segment reaches that block, every segment has a row beside it that a
keyboard can reach, and the ring, hand and time are read back as pixels and places.
"""

from __future__ import annotations

import importlib.util
import itertools
import math
import os
from collections.abc import Iterator

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK, block

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.dial import DayDialView, DialFace
    from desktop.native.layouts.registry import LAYOUTS, options_for, tokens_for
    from desktop.native.look import ACCENTS, category_paint, contrast, resolved_palette
    from desktop.native.weekmodel import build_week, minute_of, set_clock_24h
    from desktop.native.widgets import FittedLabel

THURSDAY = 3


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-dial-test"])
    yield application


def shown(
    qapp: QApplication,
    clock: str,
    blocks: list[dict] | None = None,
    today: int | None = THURSDAY,
    palette: dict | None = None,
    homework: dict | None = None,
    **chosen: str,
) -> DayDialView:
    options = {**options_for(None, "dial"), **chosen}
    palette = palette or resolved_palette("light-frost", False, None, "default")
    week = build_week(WEEK, BLOCKS if blocks is None else blocks, homework or HOMEWORK, TRACE)
    view = DayDialView()
    view.resize(1300, 720)
    view.show_week(
        Scene(week, today, minute_of(clock), options, tokens_for("dial", options["colour"], palette))
    )
    view.show()
    qapp.processEvents()
    return view


def text(view: DayDialView, name: str) -> str:
    return view.findChild(QLabel, name).text()


def row_buttons(view: DayDialView) -> list[QPushButton]:
    return [item for item in view.findChildren(QPushButton) if item.property("kind") == "row"]


def rows(view: DayDialView) -> list[tuple[str, str, str, str, str]]:
    """Each row's columns as they read: start, title, length, tag, and whether it is over or on."""
    read = []
    for row in row_buttons(view):
        tag = row.findChild(QLabel, "dialRowTagText")
        read.append(
            (
                row.findChild(QLabel, "dialRowTime").text(),
                row.findChild(FittedLabel, "dialRowName").full_text(),
                row.findChild(QLabel, "dialRowLength").text(),
                tag.text() if tag is not None else "",
                row.property("state"),
            )
        )
    return read


def actions(view: DayDialView) -> list[tuple[str, str]]:
    found = [item for item in view.findChildren(QPushButton) if item.property("kind") != "row"]
    return [(item.objectName(), item.property("kind") or "") for item in found]


def face(view: DayDialView) -> DialFace:
    return view.findChild(DialFace, "dialFace")


def reachable(dial: DialFace) -> set[str]:
    hits = set()
    for x in range(0, dial.width(), 5):
        for y in range(0, dial.height(), 5):
            found = dial.block_at(QPointF(x, y))
            if found is not None:
                hits.add(found.block_id)
    return hits


class Seen:
    """The view as drawn, read at points of one of its widgets. A widget's own grab shows the default
    palette where it paints nothing, not the page behind it."""

    def __init__(self, view: DayDialView) -> None:
        self.view, self.image = view, view.grab().toImage()

    def at(self, widget: QWidget, point: QPointF | QPoint) -> QColor:
        spot = point.toPoint() if isinstance(point, QPointF) else point
        return self.image.pixelColor(widget.mapTo(self.view, spot))


def near(first: QColor, second: str | QColor, within: int = 6) -> bool:
    other = QColor(second)
    return all(
        abs(a - b) <= within
        for a, b in zip(first.getRgb()[:3], other.getRgb()[:3], strict=True)
    )


def on_ring(dial: DialFace, minute: float, reach: float | None = None) -> QPointF:
    """A point of the face at `minute`, halfway across the ring or at `reach` from the centre."""
    track = dial.track
    middle = track.point_for(round(minute))
    if reach is None:
        return QPointF(middle)
    scale = reach / math.hypot(middle.x() - track.centre.x(), middle.y() - track.centre.y())
    return track.centre + (QPointF(middle) - track.centre) * scale


def paint(tokens: dict[str, str], category: str) -> tuple[str, str]:
    return category_paint(category, {"family": "light", "panel": tokens["surface"]})


def test_between_blocks_the_card_says_what_is_up_next_and_in_how_long(qapp: QApplication) -> None:
    view = shown(qapp, "15:40")
    assert text(view, "dialKicker") == "Up next"
    assert text(view, "dialIn") == "in 2 h 20 min"
    assert text(view, "dialTitle") == "Dinner"
    assert text(view, "dialThen") == "18:00–18:30 · 30 min · then Essay-1 at 18:45"
    # One filled button, the step this minute is for: with no homework on, Running late.
    assert actions(view) == [("dialLate", "main"), ("dialBack", "")]


def test_during_homework_the_card_says_so_and_what_comes_after(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    assert text(view, "dialKicker") == "Now"
    assert text(view, "dialIn") == "45 min left"
    assert text(view, "dialTitle") == "Essay-1"
    assert text(view, "dialThen") == "18:45–19:45 · 1 h · then Chem-1 at 20:00"
    assert actions(view) == [
        ("dialFinished", "main"),
        ("dialFocus", ""),
        ("dialLate", ""),
        ("dialBack", ""),
    ]


def test_the_buttons_are_rounded_rectangles_not_pills(qapp: QApplication) -> None:
    """A pill's corner is the page four pixels in; a 6-pixel corner is already the button's fill."""
    view = shown(qapp, "15:40")
    late = view.findChild(QPushButton, "dialLate")
    assert late.height() >= 30
    corner = Seen(view).at(late, QPoint(4, 4))
    assert near(corner, view.scene.tokens["accent"]), corner.name()


def test_the_list_reads_the_day_in_columns_marking_what_is_over_done(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    assert rows(view) == [
        ("08:00", "School", "6 h 30 min", "Done", "past"),
        ("18:00", "Dinner", "30 min", "Done", "past"),
        ("18:45", "Essay-1", "1 h", "", "now"),
        ("20:00", "Chem-1", "1 h 30 min", "", ""),
    ]
    # Marked, not struck through: a line through the words made them hard to read.
    assert not any(row.findChild(FittedLabel, "dialRowName").font().strikeOut() for row in row_buttons(view))


def test_times_and_lengths_line_up_however_wide_they_are(qapp: QApplication) -> None:
    """On the 12-hour clock 10:00 AM is wider than 8:00 AM; each column still ends at one edge."""
    study = [*BLOCKS, block("study-hall", "flexible", [3], "10:00", 45, assignment_id="essay")]
    set_clock_24h(False)
    try:
        view = shown(qapp, "19:00", study)
        for name in ("dialRowTime", "dialRowLength"):
            cells = [row.findChild(QLabel, name) for row in row_buttons(view)]
            assert len({cell.text() for cell in cells}) > 1
            edges = {cell.mapTo(view, cell.rect().topRight()).x() for cell in cells}
            assert len(edges) == 1, f"{name} is not one column: {edges}"
    finally:
        set_clock_24h(True)


def test_nothing_else_today_is_said_once(qapp: QApplication) -> None:
    def said(view: DayDialView) -> list[str]:
        return [
            item.text()
            for item in view.findChildren(QLabel)
            if item.text().startswith("Nothing else") and item.isVisibleTo(view)
        ]

    view = shown(qapp, "15:40")
    assert said(view) == ["Nothing else today"]
    assert text(view, "dialNoneTime") == "21:30"
    # Once the day is over the card says it, and the list does not say it again.
    view = shown(qapp, "22:30")
    assert said(view) == ["Nothing else scheduled today"]
    assert view.findChild(QLabel, "dialNoneTime") is None


def test_homework_with_no_time_is_counted_with_the_book_and_named(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    assert text(view, "dialWaiting") == "1 homework not placed yet"
    assert view.findChild(FittedLabel, "dialWaitingList").full_text() == "· Poster-1"
    unplaced = view.findChild(QWidget, "dialUnplaced")
    assert any(not item.pixmap().isNull() for item in unplaced.findChildren(QLabel))
    vocab = {"id": "vocab", "title": "Spanish vocab", "due": "2026-09-19T08:00", "completed": False}
    more = [*BLOCKS, block("vocab-1", "flexible", [], None, 30, assignment_id="vocab")]
    view = shown(qapp, "19:00", more, homework={**HOMEWORK, "vocab": vocab})
    assert text(view, "dialWaiting") == "2 homework not placed yet"
    assert view.findChild(FittedLabel, "dialWaitingList").full_text() == "· Vocab-1, Poster-1"


def test_every_segment_has_a_row_a_keyboard_can_reach(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    for item in row_buttons(view):
        assert item.focusPolicy() != Qt.FocusPolicy.NoFocus
        item.click()
    assert opened == ["school", "dinner", "essay-1", "chem-1"]
    assert reachable(face(view)) == set(opened)


def test_a_click_on_a_segment_opens_that_block_and_the_middle_opens_nothing(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    dial = face(view)
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    QTest.mouseClick(dial, Qt.MouseButton.LeftButton, pos=QPoint(dial.width() // 2, dial.height() // 2))
    assert opened == []
    QTest.mouseClick(dial, Qt.MouseButton.LeftButton, pos=on_ring(dial, 20 * 60 + 45).toPoint())
    assert opened == ["chem-1"]


def test_homework_inside_a_fixed_block_can_still_be_clicked(qapp: QApplication) -> None:
    inside = [*BLOCKS, block("study-hall", "flexible", [3], "10:00", 45, assignment_id="essay")]
    dial = face(shown(qapp, "19:00", inside))
    assert dial.block_at(on_ring(dial, 10 * 60 + 20)).block_id == "study-hall"
    assert dial.block_at(on_ring(dial, 9 * 60)).block_id == "school"
    assert dial.block_at(on_ring(dial, 12 * 60)).block_id == "school"


def test_the_ring_is_the_whole_day_with_noon_at_the_top_and_midnight_at_the_bottom(
    qapp: QApplication,
) -> None:
    early = [
        *BLOCKS,
        block("paper-round", "locked", [3], "05:00", 45),
        block("late-call", "locked", [3], "23:00", 30),
    ]
    dial = face(shown(qapp, "19:00", early))
    assert {"paper-round", "late-call"} <= reachable(dial)
    centre = dial.track.centre
    noon, midnight, six = on_ring(dial, 12 * 60), on_ring(dial, 0), on_ring(dial, 6 * 60)
    assert abs(noon.x() - centre.x()) < 1 and noon.y() < centre.y()
    assert abs(midnight.x() - centre.x()) < 1 and midnight.y() > centre.y()
    assert six.x() < centre.x() and abs(six.y() - centre.y()) < 1


def test_what_is_over_is_paler_and_neighbours_are_two_degrees_apart(qapp: QApplication) -> None:
    view = shown(qapp, "15:40")
    dial, tokens = face(view), view.scene.tokens
    seen = Seen(view)

    def ring(minute: int) -> QColor:
        return seen.at(dial, on_ring(dial, minute))

    school_fill, _ = paint(tokens, "class")
    _, dinner_mark = paint(tokens, "meals")
    assert near(ring(11 * 60), school_fill), "School is over, so pale"
    assert near(ring(18 * 60 + 15), dinner_mark), "Dinner is to come"
    # School ends at 14:30 and free time begins: the page shows between them, a degree (four minutes)
    # to either side, and ten minutes away each is solid again.
    assert near(ring(14 * 60 + 30), tokens["bg"])
    assert near(ring(14 * 60 + 20), school_fill)
    assert not near(ring(14 * 60 + 40), tokens["bg"], 3)
    # The free time holding now is split at now, its elapsed part fainter.
    before, after = ring(15 * 60), ring(17 * 60)
    page = QColor(tokens["bg"])
    assert sum(abs(a - b) for a, b in zip(before.getRgb(), page.getRgb(), strict=True)) < sum(
        abs(a - b) for a, b in zip(after.getRgb(), page.getRgb(), strict=True)
    )


def test_the_hand_stops_at_the_rings_inner_edge(qapp: QApplication) -> None:
    view = shown(qapp, "15:40")
    dial, tokens = face(view), view.scene.tokens
    seen, track = Seen(view), dial.track
    minute = minute_of("15:40")
    assert near(seen.at(dial, on_ring(dial, minute, track.inner * 0.6)), tokens["accent"], 20)
    for reach in (track.inner + 4, (track.inner + track.outer) / 2, track.outer - 4):
        assert not near(seen.at(dial, on_ring(dial, minute, reach)), tokens["accent"], 40), reach


def test_hour_labels_sit_outside_the_ring_and_none_inside_it(qapp: QApplication) -> None:
    """Under the ring or inside it a label was crossed by the hand and hidden by the segments."""
    view = shown(qapp, "12:00", [])
    dial, tokens = face(view), view.scene.tokens
    seen, track = Seen(view), dial.track

    def inked(point: QPointF) -> bool:
        spots = (point + QPointF(dx, dy) for dx in range(-8, 9) for dy in range(-6, 7))
        return any(not near(seen.at(dial, spot), tokens["bg"], 30) for spot in spots)

    for hour in range(0, 24, 2):
        assert inked(on_ring(dial, hour * 60, track.outer + 32)), f"no label for {hour:02d}"
        if hour != 12:
            # At noon the hand points at 12.
            assert not inked(on_ring(dial, hour * 60, track.inner - 16)), f"{hour:02d} inside the ring"


def test_the_time_sits_under_the_hub_and_the_hand_never_crosses_it(qapp: QApplication) -> None:
    view = shown(qapp, "15:40")
    dial, blocks = face(view), view.scene.week.on_day(THURSDAY)
    track = dial.track
    below, crossed = [], []
    for minute in range(0, 24 * 60, 10):
        dial.set_day(blocks, minute, view.scene.tokens, minute)
        box = dial.time_box()
        tip = on_ring(dial, minute, track.inner - 8)
        if any(box.contains(track.centre + (tip - track.centre) * (step / 100)) for step in range(101)):
            crossed.append(minute)
        if box.top() > track.centre.y():
            below.append(minute)
    assert crossed == []
    assert 15 * 60 + 40 in below and 12 * 60 in below and 6 * 60 in below
    # Around midnight the hand points down, and the time moves above the hub.
    assert not {23 * 60 + 50, 0, 10} & set(below)


def test_the_face_says_the_time_and_the_free_time_left(qapp: QApplication) -> None:
    assert face(shown(qapp, "15:40")).accessibleDescription() == "15:40. 3 h 20 min free until 22:00"
    assert face(shown(qapp, "19:00")).accessibleDescription() == "19:00. 45 min free until 22:00"
    assert face(shown(qapp, "22:30")).accessibleDescription() == "22:30"


def test_the_face_is_described_for_a_screen_reader(qapp: QApplication) -> None:
    dial = face(shown(qapp, "19:00"))
    assert dial.accessibleName() == "Thursday: School 08:00, Dinner 18:00, Essay-1 18:45, Chem-1 20:00"


def test_the_weeks_small_dials_are_labelled_with_todays_hand_and_past_days_paler(
    qapp: QApplication,
) -> None:
    view = shown(qapp, "19:00")
    tokens = view.scene.tokens
    strip = view.findChild(QWidget, "dialStrip")
    names = [item.text() for item in strip.findChildren(QLabel, "dialMiniName")]
    dates = strip.findChildren(QLabel, "dialMiniDate")
    assert list(zip(names, [item.text() for item in dates], strict=True)) == [
        ("Mon", "14"),
        ("Tue", "15"),
        ("Wed", "16"),
        ("Thu", "17"),
        ("Fri", "18"),
        ("Sat", "19"),
        ("Sun", "20"),
    ]
    assert [item.property("today") for item in dates] == [False, False, False, True, False, False, False]
    minis = [view.findChild(DialFace, f"dialMini{day}") for day in range(7)]
    seen = Seen(view)
    hubs = [near(seen.at(mini, mini.rect().center()), tokens["accent"], 20) for mini in minis]
    assert hubs == [False, False, False, True, False, False, False]
    school_fill, school_mark = paint(tokens, "class")
    monday, friday = minis[0], minis[4]
    assert near(seen.at(monday, on_ring(monday, 11 * 60)), school_fill)
    assert near(seen.at(friday, on_ring(friday, 11 * 60)), school_mark)


def test_a_small_dial_opens_that_day_and_today_is_one_press_back(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    QTest.mouseClick(view.findChild(DialFace, "dialMini0"), Qt.MouseButton.LeftButton)
    assert text(view, "dialKicker") == "Monday, September 14"
    assert text(view, "dialTitle") == "45 min planned · 45 min done"
    assert [(name, tag, state) for _time, name, _length, tag, state in rows(view)] == [
        ("School", "Done", "past"),
        ("Math-1", "Done", "past"),
        ("Dinner", "Done", "past"),
    ]
    view.findChild(QPushButton, "dialToday").click()
    assert text(view, "dialKicker") == "Now"


def test_in_another_week_it_shows_the_week_but_claims_no_now(qapp: QApplication) -> None:
    view = shown(qapp, "19:00", today=None)
    assert text(view, "dialKicker") == "Monday, September 14"
    assert text(view, "dialThen") == "This is not the current week, so there is no now to show."
    assert view.findChild(QPushButton, "dialToday") is None
    assert view.findChild(QPushButton, "dialFinished") is None
    assert view.findChild(QPushButton, "dialBack") is not None


def test_option_list_hidden_and_week_hidden_remove_them(qapp: QApplication) -> None:
    assert rows(shown(qapp, "19:00", list="hide")) == []
    assert len(shown(qapp, "19:00").findChildren(DialFace)) == 8
    assert len(shown(qapp, "19:00", week="hide").findChildren(DialFace)) == 1


def test_night_is_the_navy_colourway_saved_as_midnight(qapp: QApplication) -> None:
    def corner(view: DayDialView) -> str:
        return view.grab().toImage().pixelColor(3, 3).name()

    assert [(value, name) for value, name, _ in LAYOUTS["dial"].colourways] == [
        ("midnight", "Night"),
        ("daylight", "Daylight"),
    ]
    assert corner(shown(qapp, "19:00", colour="midnight")) == "#0b0f1d"
    assert corner(shown(qapp, "19:00", colour="daylight")) == "#f4f6fb"
    assert (
        corner(shown(qapp, "19:00", colour="match"))
        == resolved_palette("light-frost", False, None, "default")["window"]
    )


@pytest.mark.parametrize("colour", ["match", "midnight"])
def test_the_minutes_to_go_read_in_every_accent(qapp: QApplication, colour: str) -> None:
    """Accent words on a tenth of the accent: FlexWeek's blue read 4.33 to 1 on white's tint and
    3.2 on Night's, so the words take the least darker or lighter shade that reads."""
    failures = []
    for pack, accent in itertools.product(("light-frost", "dark-frost"), ACCENTS):
        palette = resolved_palette(pack, pack == "dark-frost", None, accent)
        view = shown(qapp, "15:40", palette=palette, colour=colour)
        pill = view.findChild(QLabel, "dialIn")
        ground = Seen(view).at(pill, QPoint(pill.width() // 2, 2)).name()
        words = pill.palette().color(QPalette.ColorRole.WindowText).name()
        if contrast(words, ground) < 4.5:
            failures.append((pack, accent, words, ground, round(contrast(words, ground), 2)))
    assert failures == []


def test_the_week_strip_survives_large_text(qapp: QApplication) -> None:
    """The strip is how another day is reached. At High contrast's larger text it used to be
    sliced in half by the scroller, with the day names off screen entirely."""
    options = options_for(None, "dial")
    palette = resolved_palette("light-frost", False, None, "default")
    view = DayDialView()
    view.resize(1366, 700)
    view.show()
    qapp.processEvents()
    view.show_week(
        Scene(
            build_week(WEEK, BLOCKS, HOMEWORK, TRACE),
            3,
            minute_of("13:40"),
            options,
            tokens_for("dial", options["colour"], palette),
            1.25,
        )
    )
    qapp.processEvents()
    strip = view.findChild(QWidget, "dialStrip")
    assert strip is not None and strip.isVisible()
    bottom = strip.mapTo(view, strip.rect().bottomLeft()).y()
    assert bottom <= view.height(), f"the strip runs {bottom - view.height()}px past the view"
    names = [label for label in strip.findChildren(QLabel) if label.objectName() == "dialMiniName"]
    assert len(names) == 7
    for label in names:
        edge = label.mapTo(view, label.rect().bottomLeft()).y()
        assert edge <= view.height(), f"{label.text()} is cut off"


@pytest.mark.parametrize("size", [(1280, 744), (1366, 560), (800, 700), (800, 560)])
def test_the_page_never_scrolls_sideways(qapp: QApplication, size: tuple[int, int]) -> None:
    view = shown(qapp, "19:00")
    view.resize(*size)
    qapp.processEvents()
    scroller = view.findChild(QWidget, "dialScroll")
    assert not scroller.horizontalScrollBar().isVisible()
    assert face(view).width() >= 240


def test_hiding_the_week_strip_still_works(qapp: QApplication) -> None:
    assert shown(qapp, "19:00", week="hide").findChild(QWidget, "dialStrip").isVisible() is False
    assert shown(qapp, "19:00").findChild(QWidget, "dialStrip").isVisible() is True
