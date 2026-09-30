"""The contract between the one hand and whatever a design draws its hours on.

A test design here shows the week on every kind of surface at once: columns that run down, lanes
that run across, a card laid at an angle, a day cut into two tiles, and a dial. The same hand has to
land a block on each, keep it inside each tile's own hours, open a day from its name either way time
runs, and hold the design's renders from the moment of the press.
"""

from __future__ import annotations

import importlib.util
import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QWidget

    from desktop.native.hours.canvas import BlockPainter, HoursCanvas
    from desktop.native.hours.geometry import Axis, DialTrack, LinearTrack, Span
    from desktop.native.hours.hand import Create, Gesture, Hand, Held, Move, Place, Verdict, span_words
    from desktop.native.layouts.base import LayoutView
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import Occurrence

HOURS = Path(__file__).resolve().parents[1] / "native" / "hours"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-targets-test"])


def occurrence(block_id: str, day: int, start: int, end: int) -> Occurrence:
    return Occurrence(
        block_id, block_id.title(), "class", day, start, end, False, False, False, None, None, None
    )


class Dial(QWidget):
    """The least a surface needs: it takes blocks and says which track lies under a point."""

    takes_blocks = True

    def __init__(self, day: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.track = DialTrack(day, QPointF(90, 90), 50, 85, first=6 * 60, last=22 * 60)

    def track_at(self, point: QPointF) -> DialTrack | None:
        return self.track if self.track.contains(point) else None

    def track_for(self, day: int, minute: int | None = None) -> DialTrack | None:
        return self.track if day == self.track.day else None


class Everything(LayoutView):
    """Monday and Tuesday down, Wednesday and Thursday across, Friday on a tilted card, Saturday in
    a morning tile and an afternoon tile, Sunday on a dial."""

    layout_id = "targets"

    def __init__(self, hand: Hand) -> None:
        super().__init__(hand=hand)
        painter = BlockPainter(resolved_palette("system", False, None))

        def columns(area: QRectF) -> list[LinearTrack]:
            half = area.width() / 2
            return [
                LinearTrack(day, QRectF(area.left() + day * half, area.top(), half, area.height()))
                for day in (0, 1)
            ]

        def lanes(area: QRectF) -> list[LinearTrack]:
            half = area.height() / 2
            return [
                LinearTrack(
                    day, QRectF(area.left(), area.top() + (day - 2) * half, area.width(), half), Axis.ACROSS
                )
                for day in (2, 3)
            ]

        def card(area: QRectF) -> list[LinearTrack]:
            return [LinearTrack(4, area.adjusted(30, 20, -30, -20), turn=8)]

        def tile(first: int, last: int):
            return lambda area: [LinearTrack(5, area, first=first, last=last)]

        self.down = HoursCanvas(hand, painter, columns, gutter=40, header=24, parent=self)
        self.down.setGeometry(QRect(0, 0, 300, 500))
        self.across = HoursCanvas(hand, painter, lanes, gutter=60, header=20, parent=self)
        self.across.setGeometry(QRect(310, 0, 440, 160))
        self.card = HoursCanvas(hand, painter, card, parent=self)
        self.card.setGeometry(QRect(310, 170, 200, 330))
        self.morning = HoursCanvas(hand, painter, tile(6 * 60, 12 * 60), parent=self)
        self.morning.setGeometry(QRect(520, 170, 110, 160))
        self.afternoon = HoursCanvas(hand, painter, tile(12 * 60, 18 * 60), parent=self)
        self.afternoon.setGeometry(QRect(520, 340, 110, 160))
        self.dial = Dial(6, self)
        self.dial.setGeometry(QRect(0, 520, 180, 180))
        self.morning.set_week([occurrence("run", 5, 8 * 60, 9 * 60)])


class Stage:
    def __init__(self, qapp: QApplication) -> None:
        self.window = QWidget()
        # Inside the offscreen screen (800 by 800), where QApplication.widgetAt can find it.
        self.window.setGeometry(QRect(0, 0, 760, 720))
        self.said: list[object] = []
        self.hand = Hand(lambda block_id, from_day, span: Verdict(True, span_words(span)), self.window)
        # A pixel of the morning tile is over two minutes, too coarse to aim within a 5-minute step.
        # What these prove, bounds and targets, holds at any step.
        self.hand.step = 15
        self.hand.committed.connect(self.said.append)
        self.view = Everything(self.hand)
        self.view.setParent(self.window)
        self.view.setGeometry(self.window.rect())
        self.window.show()
        qapp.processEvents()
        for canvas in (
            self.view.down,
            self.view.across,
            self.view.card,
            self.view.morning,
            self.view.afternoon,
        ):
            canvas.relayout()

    def send(self, widget: QWidget, kind: QEvent.Type, at: QPoint, held: bool) -> None:
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        event = QMouseEvent(
            kind,
            QPointF(widget.mapFromGlobal(at)),
            QPointF(at),
            Qt.MouseButton.LeftButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(widget, event)

    def carry(self, start: QPoint, end: QPoint, source: QWidget) -> None:
        for step in range(1, 9):
            self.send(source, QEvent.Type.MouseMove, start + (end - start) * step / 8, True)
        self.send(source, QEvent.Type.MouseButtonRelease, end, False)

    def place(self, day: int, minute: int, surface: QWidget) -> None:
        """Homework with no time, carried from nowhere in particular and let go at a day and minute."""
        start = QPoint(750, 700)
        self.hand.press(self.window, Held(Gesture.PLACE, "Essay", 60, "essay"), start)
        self.carry(
            start,
            surface.mapToGlobal(surface.track_for(day, minute).point_for(minute).toPoint()),
            self.window,
        )


def test_one_hand_lands_a_block_on_every_kind_of_surface(qapp: QApplication) -> None:
    stage = Stage(qapp)
    view = stage.view
    for day, minute, surface in (
        (0, 10 * 60, view.down),
        (3, 10 * 60, view.across),
        (4, 10 * 60, view.card),
        (5, 7 * 60, view.morning),
        (5, 14 * 60, view.afternoon),
        (6, 9 * 60, view.dial),
    ):
        stage.place(day, minute, surface)
    starts = [(change.span.day, change.span.start) for change in stage.said]
    assert all(isinstance(change, Place) for change in stage.said)
    # Carried by the middle of nothing, a block's start is where it is let go, to the quarter hour.
    assert [(day, round(start / 15) * 15) for day, start in starts] == [
        (0, 600),
        (3, 600),
        (4, 600),
        (5, 420),
        (5, 840),
        (6, 540),
    ]


def test_a_design_lists_every_surface_it_shows(qapp: QApplication) -> None:
    stage = Stage(qapp)
    shown = stage.view.hours_surfaces()
    days = sorted({day for surface in shown for day in range(7) if surface.track_for(day) is not None})
    assert days == [0, 1, 2, 3, 4, 5, 6]
    assert len(shown) == 6


def test_a_tile_keeps_a_block_inside_its_own_hours(qapp: QApplication) -> None:
    """The morning tile runs 06:00 to 12:00. A block carried to its end stops at noon; one resized
    past its end, or drawn past it, stops there too, whatever lies under the pointer."""
    stage = Stage(qapp)
    tile, track = stage.view.morning, stage.view.morning.tracks[0]
    box = tile.block_rect("run", 5)
    grab = box.center()
    near_end = tile.mapToGlobal(track.point_for(11 * 60 + 50).toPoint())
    stage.send(tile, QEvent.Type.MouseButtonPress, grab, True)
    stage.carry(grab, near_end, tile)
    edge = QPoint(box.center().x(), box.bottom() - 2)
    below = stage.view.afternoon.mapToGlobal(stage.view.afternoon.tracks[0].point_for(15 * 60).toPoint())
    stage.send(tile, QEvent.Type.MouseButtonPress, edge, True)
    stage.carry(edge, below, tile)
    free = tile.mapToGlobal(track.point_for(10 * 60).toPoint()) + QPoint(0, 2)
    stage.send(tile, QEvent.Type.MouseButtonPress, free, True)
    stage.carry(free, below, tile)
    assert stage.said == [
        Move("run", 5, Span(5, 11 * 60, 12 * 60)),
        Move("run", 5, Span(5, 8 * 60, 12 * 60)),
        Create(Span(5, 10 * 60, 12 * 60)),
    ]


def test_a_click_near_a_tiles_end_makes_only_what_fits_in_it(qapp: QApplication) -> None:
    stage = Stage(qapp)
    tile, track = stage.view.morning, stage.view.morning.tracks[0]
    at = tile.mapToGlobal(track.point_for(11 * 60 + 30).toPoint()) + QPoint(0, 2)
    stage.send(tile, QEvent.Type.MouseButtonPress, at, True)
    stage.send(tile, QEvent.Type.MouseButtonRelease, at, False)
    assert stage.said == [Create(Span(5, 11 * 60 + 30, 12 * 60))]


def test_a_days_name_opens_it_whichever_way_its_time_runs(qapp: QApplication) -> None:
    stage = Stage(qapp)
    opened: list[int] = []
    for canvas in (stage.view.down, stage.view.across):
        canvas.day_opened.connect(opened.append)
    for day, canvas in (
        (0, stage.view.down),
        (1, stage.view.down),
        (2, stage.view.across),
        (3, stage.view.across),
    ):
        try:
            at = canvas.day_name(day)
        except LookupError as error:
            raise AssertionError(f"day {day} has no name to click: {error}") from None
        QTest.mouseClick(
            canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, canvas.mapFromGlobal(at)
        )
    assert opened == [0, 1, 2, 3]
    with pytest.raises(LookupError):
        stage.view.card.day_name(4)


def test_renders_are_held_from_the_press_until_the_hand_lets_go(qapp: QApplication) -> None:
    """A tap holds them too: a rebuild between press and release would delete what was pressed."""
    stage = Stage(qapp)
    held: list[bool] = []
    stage.hand.holding.connect(held.append)
    tile = stage.view.morning
    grab = tile.block_rect("run", 5).center()
    stage.send(tile, QEvent.Type.MouseButtonPress, grab, True)
    assert held == [True], "held before the pointer has moved at all"
    stage.send(tile, QEvent.Type.MouseButtonRelease, grab, False)
    stage.send(tile, QEvent.Type.MouseButtonPress, grab, True)
    QTest.keyClick(tile, Qt.Key.Key_Escape)
    stage.send(tile, QEvent.Type.MouseButtonPress, grab, True)
    stage.hand.cancel()
    assert held == [True, False, True, False, True, False]


def test_the_shared_hours_have_one_set_of_drag_rules() -> None:
    """Only the hand decides when a press becomes a drag, only geometry snaps, and nothing in the
    shared hours uses Qt's system drag and drop."""
    sources = {path.name: path.read_text() for path in HOURS.glob("*.py")}
    assert not [name for name, text in sources.items() if re.search(r"\bQDrag\b|\bQMimeData\b", text)]
    assert [name for name, text in sources.items() if "startDragDistance" in text] == ["hand.py"]
    assert [name for name, text in sources.items() if re.search(r"^def snap\b", text, re.M)] == [
        "geometry.py"
    ]


def test_nothing_in_the_app_uses_system_drag_and_drop() -> None:
    """Every block moves through the one hand. Qt's system drag and drop is where Wayland and X11
    differ and where the rig cannot see what the student sees, so nothing may take it up again."""
    app = HOURS.parent
    system_drag = r"\bQDrag\b|\bQMimeData\b|\bsetAcceptDrops\b|\bdropEvent\b"
    found = [
        f"{path.relative_to(app)}: {match.group()}"
        for path in sorted(app.rglob("*.py"))
        for match in re.finditer(system_drag, path.read_text())
    ]
    assert found == []
