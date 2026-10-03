"""What the pointer is doing: one gesture engine for every design's hours, chips and month.

Anything a student can pick up calls `Hand.press` with what it holds. From then on the hand follows
the pointer itself: it waits for a real drag, finds the hours under the pointer, snaps, asks the
window's rule, shows the result in place, scrolls a scroll area after the pointer rests at its
edge, and on release reports one change. Moves arrive through Qt's implicit grab (the widget pressed
keeps receiving the mouse until release), so no system drag-and-drop is involved and X11 and
Wayland behave alike.

A press that never becomes a drag is a tap, handed back to whoever pressed: on a block, a tap opens
it. A right-click asks for a block's menu and never picks anything up. Escape lets go.

What a block can land on is a surface: any widget that sets `takes_blocks` and answers `track_at`
with a `Track` under a point of its own. `HoursCanvas` is one; My day's dial and anything a design
draws itself can be others. The hand asks nothing else of them, so a design brings tracks and paint,
never its own rules for dragging.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from enum import Enum

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QWidget
from shiboken6 import isValid

from desktop.native.calendar import DAYS
from desktop.native.hours.geometry import DRAG_STEPS, Span, Track, snap
from desktop.native.weekmodel import clock_text, length_label

# A drag near a scroll area's edge scrolls it only after resting there this long, so passing
# through the edge on the way in never shifts the hours under the pointer. Once it starts, the hours
# move by time, not by pixels, so a zoomed-out day is as easy to aim at as a zoomed-in one.
EDGE_PX, DWELL_S, SCROLL_MINUTES_PER_S = 36, 0.3, 120
# The longest stretch one scroll step may cover, so a stalled event loop cannot jump the hours.
LONGEST_STEP_S = 0.1
SECOND_CLICK = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseButtonRelease)


class Gesture(Enum):
    MOVE = "move"
    RESIZE_START = "resize_start"
    RESIZE_END = "resize_end"
    CREATE = "create"
    PLACE = "place"
    MOVE_DATE = "move_date"


@dataclass(frozen=True)
class Verdict:
    """Whether a span can stand, and the words that say so or say why not."""

    ok: bool
    words: str


@dataclass(frozen=True)
class Held:
    """What the pointer holds, fixed at the press."""

    kind: Gesture
    title: str
    minutes: int
    block_id: str | None = None
    from_day: int = -1
    origin: Span | None = None
    grab: int = 0
    # For a Month chip: the date it was lifted from.
    from_iso: str = ""


@dataclass(frozen=True)
class Preview:
    held: Held
    span: Span
    verdict: Verdict


@dataclass(frozen=True)
class Move:
    """A block given a new day, start or end. `from_day` is the copy that was picked up."""

    block_id: str
    from_day: int
    span: Span


@dataclass(frozen=True)
class Place:
    """Homework that had no time, given this one."""

    block_id: str
    span: Span


@dataclass(frozen=True)
class Create:
    span: Span


@dataclass(frozen=True)
class MoveDate:
    block_id: str
    from_iso: str
    to_iso: str


Change = Move | Place | Create | MoveDate
Judge = Callable[[str, int, Span], Verdict]
# Whether a block can go from one date to another: its id, the date it is on, the date asked for.
DateJudge = Callable[[str, str, str], Verdict]


def is_surface(widget: object) -> bool:
    """Whether a widget takes blocks: it has tracks, and says which one lies under a point."""
    return isinstance(widget, QWidget) and bool(getattr(widget, "takes_blocks", False))


def is_date_surface(widget: object) -> bool:
    """Whether a widget takes dates: a month says which date lies under a point."""
    return isinstance(widget, QWidget) and bool(getattr(widget, "takes_dates", False))


def surface_at(at: QPoint) -> QWidget | None:
    """The surface a global point is over, if any: the widget there or the nearest one holding it."""
    widget = QApplication.widgetAt(at)
    while widget is not None and not is_surface(widget):
        widget = widget.parentWidget()
    return widget


class SecondClick(QObject):
    """For a double-click's length after a tap, a click where the tap was does nothing to a dialog the
    tap opened. A tap on a block opens its editor, so the second click of a double-click from habit
    lands on that editor, where it would press whatever is under the pointer."""

    def __init__(self, host: QObject, at: QPoint) -> None:
        super().__init__(host)
        self._at = at
        QApplication.instance().installEventFilter(self)
        ends = QTimer(self)
        ends.setSingleShot(True)
        ends.timeout.connect(self.stop)
        ends.start(QApplication.doubleClickInterval())

    def stop(self) -> None:
        QApplication.instance().removeEventFilter(self)
        self.deleteLater()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() not in SECOND_CLICK or not isinstance(event, QMouseEvent):
            return False
        away = (event.globalPosition().toPoint() - self._at).manhattanLength()
        near = away <= QApplication.startDragDistance()
        # Only over what the tap opened: a click on the hours again is a click like any other.
        return near and QApplication.activeModalWidget() is not None


def span_words(span: Span) -> str:
    return f"{DAYS[span.day]} {clock_text(span.start)}–{clock_text(span.end)} · {length_label(span.minutes)}"


class Hand(QObject):
    """The one pointer. The window owns it and applies what it reports."""

    committed = Signal(object)
    refused = Signal(str)
    opened = Signal(str)
    selected = Signal(str, int)
    # The keyboard moved off a block onto free time, so nothing is chosen.
    cleared = Signal()
    # A block's menu asked for: its id, its day (-1 for homework with no time yet), where to show it.
    menu_requested = Signal(str, int, QPoint)
    # An empty spot's menu asked for: its day, the minute under the pointer, where to show it.
    spot_menu_requested = Signal(int, int, QPoint)
    active_changed = Signal(bool)
    # From the press to the release: nothing the press started on may be rebuilt meanwhile.
    holding = Signal(bool)
    preview_changed = Signal()

    def __init__(self, judge: Judge, host: QWidget) -> None:
        super().__init__(host)
        # The host is the hand's Qt parent, not a reference of its own: a reference back to it made a
        # cycle that only the garbage collector could free, at a moment of its choosing.
        self._judge = judge
        # Minutes a move, a resize or a new block lands on. The window sets it from the account.
        self.step = DRAG_STEPS[0]
        self.preview: Preview | None = None
        self.selection: tuple[str, int] | None = None
        self.month_target: str | None = None
        self.month_verdict: Verdict | None = None
        # The window's rule for dates; with none, every date is taken.
        self.date_judge: DateJudge | None = None
        # The block the last drop moved or placed. It is already where it was let go, so the hours
        # draw it there at once rather than sliding it from where it was picked up.
        self.dropped: str | None = None
        self._opened: tuple[str, float] | None = None
        self._held: Held | None = None
        self._source: QWidget | None = None
        self._tap: Callable[[], None] | None = None
        self._pressed_at = QPoint()
        self._last = QPoint()
        self._active = False
        self._home: tuple[QWidget, Track] | None = None
        self._track: tuple[QWidget, Track] | None = None
        self._edge: tuple[QScrollArea, int, int, float] | None = None
        self._stepped_at = 0.0
        self._owed = 0.0
        self._scroller = QTimer(self)
        self._scroller.setInterval(16)
        self._scroller.timeout.connect(self._scroll_tick)
        self._chip = QLabel(host)
        self._chip.setObjectName("heldChip")
        self._chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._chip.hide()

    # What a picked-up thing calls

    @property
    def busy(self) -> bool:
        return self._held is not None

    @property
    def active(self) -> bool:
        return self._active

    def preview_held(self) -> Held | None:
        """What is held once it is being carried, for a surface to draw it lifted."""
        return self._held if self._active else None

    def press(
        self,
        source: QWidget,
        held: Held,
        at: QPoint,
        tap: Callable[[], None] | None = None,
        home: tuple[QWidget, Track] | None = None,
    ) -> None:
        """Pick something up at a global point. `home` is the surface and track it came from."""
        self._end(silent=True)
        self.dropped = None
        self._held, self._source, self._tap, self._home = held, source, tap, home
        self._pressed_at = self._last = at
        QApplication.instance().installEventFilter(self)
        self.holding.emit(True)

    def select(self, block_id: str, day: int) -> None:
        self.selection = (block_id, day)
        self.selected.emit(block_id, day)
        self.preview_changed.emit()

    def clear_selection(self) -> None:
        self.selection = None
        self.cleared.emit()
        self.preview_changed.emit()

    def open(self, block_id: str, second_click: bool = False) -> None:
        """Open a block. `second_click` is a double-click's second: the first, a tap, has opened it
        already, so it opens nothing more, and one double-click never makes two editors."""
        now = time.monotonic()
        last, self._opened = self._opened, (block_id, now)
        soon = QApplication.doubleClickInterval() / 1000
        if second_click and last is not None and last[0] == block_id and now - last[1] < soon:
            return
        self._end(silent=True)
        self.opened.emit(block_id)

    def ask_menu(self, block_id: str, day: int, at: QPoint) -> None:
        """A right-click on a block: it becomes the selection, and the window shows its menu. While
        something is carried, a right-click does nothing."""
        if self._active:
            return
        self._end(silent=True)
        if day >= 0:
            self.select(block_id, day)
        self.menu_requested.emit(block_id, day, at)

    def ask_spot_menu(self, day: int, minute: int, at: QPoint) -> None:
        """A right-click on free time: the window shows what can be added there. As for a block, while
        something is carried it does nothing."""
        if self._active:
            return
        self._end(silent=True)
        self.spot_menu_requested.emit(day, minute, at)

    def commit(self, change: Change) -> None:
        """For a tap that makes something, such as a click on free time."""
        self.committed.emit(change)

    def cancel(self) -> None:
        self._end(silent=True)

    # Following the pointer

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
            self._moved(event.globalPosition().toPoint())
        elif kind == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                self._released()
        elif kind == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Escape:
                self._end(silent=True)
                return True
        elif kind in (QEvent.Type.ApplicationDeactivate, QEvent.Type.WindowDeactivate):
            self._end(silent=True)
        return False

    def _moved(self, at: QPoint) -> None:
        if self._held is None:
            return
        self._last = at
        if not self._active:
            if (at - self._pressed_at).manhattanLength() < QApplication.startDragDistance():
                return
            self._active = True
            self.active_changed.emit(True)
        self._follow(at)
        self._watch_edge(at)

    def _released(self) -> None:
        held, active, preview, target = self._held, self._active, self.preview, self.month_target
        verdict = self.month_verdict
        tap = self._tap
        self._end(silent=True)
        if held is None:
            return
        if not active:
            if tap is not None:
                # Before the tap, which may open a dialog and wait in it.
                SecondClick(self, self._last)
                tap()
            return
        if held.kind is Gesture.MOVE_DATE:
            if target and held.block_id and target != held.from_iso:
                if verdict is not None and not verdict.ok:
                    if verdict.words:
                        self.refused.emit(verdict.words)
                    return
                self.committed.emit(MoveDate(held.block_id, held.from_iso, target))
            return
        if preview is None:
            return
        if not preview.verdict.ok:
            if preview.verdict.words:
                self.refused.emit(preview.verdict.words)
            return
        if held.kind is Gesture.CREATE:
            self.committed.emit(Create(preview.span))
        elif held.kind is Gesture.PLACE and held.block_id:
            self.dropped = held.block_id
            self.committed.emit(Place(held.block_id, preview.span))
        elif held.block_id and held.origin is not None and preview.span != held.origin:
            self.dropped = held.block_id
            self.committed.emit(Move(held.block_id, held.from_day, preview.span))

    # Where the pointer is

    def _follow(self, at: QPoint) -> None:
        held = self._held
        assert held is not None
        if held.kind is Gesture.MOVE_DATE:
            self._follow_month(at)
            return
        if held.kind in (Gesture.RESIZE_START, Gesture.RESIZE_END, Gesture.CREATE):
            found = self._home
        else:
            found = self._hours_at(at) or (self._track if held.kind is Gesture.MOVE else None)
        self._track = found or self._track
        if found is None:
            self._show(None)
            self._float(held.title, at)
            return
        self._chip.hide()
        surface, track = found
        minute = track.minute_at(QPointF(surface.mapFromGlobal(at)))
        self._show(self._span_for(held, track, minute))

    def _span_for(self, held: Held, track: Track, minute: float) -> Span:
        """Where the held thing would go, on the step. Every bound is the track's own: a block stops
        at the ends of the tile or column it is over, not at midnight, and a resize or a new block
        stays inside the track it began on. A resized edge stays a step or more from the other one,
        on a step even when the other edge is not."""
        origin, first, last, step = held.origin, track.first, track.last, self.step
        if held.kind is Gesture.RESIZE_START and origin is not None:
            latest = (origin.end - step) // step * step
            return replace(origin, start=max(min(snap(minute - held.grab, step), latest), first))
        if held.kind is Gesture.RESIZE_END and origin is not None:
            earliest = -(-(origin.start + step) // step) * step
            return replace(origin, end=min(max(snap(minute - held.grab, step), earliest), last))
        if held.kind is Gesture.CREATE and origin is not None:
            here = min(max(snap(minute, step), first), last)
            anchor = origin.start
            start, end = (anchor, max(here, anchor + step)) if here >= anchor else (here, anchor + step)
            return Span(origin.day, start, end)
        # Longer than the track: it starts where the track starts and runs past its end.
        start = max(min(snap(minute - held.grab, step), last - held.minutes), first)
        return Span(track.day, start, start + held.minutes)

    def _show(self, span: Span | None) -> None:
        held = self._held
        if held is None or span is None:
            changed = self.preview is not None
            self.preview = None
        else:
            if held.kind is Gesture.CREATE:
                verdict = Verdict(True, span_words(span))
            else:
                verdict = self._judge(held.block_id or "", held.from_day, span)
            fresh = Preview(held, span, verdict)
            changed = fresh != self.preview
            self.preview = fresh
        if changed:
            self.preview_changed.emit()

    def _hours_at(self, at: QPoint) -> tuple[QWidget, Track] | None:
        """The surface and track under a global point. Cards laid at an angle overlap, so a surface
        whose rectangle is under the pointer but whose track is not passes to its siblings."""
        widget = surface_at(at)
        if widget is None:
            return None
        tried = [widget]
        parent = widget.parentWidget()
        if parent is not None:
            tried += [
                sibling
                for sibling in reversed(
                    parent.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
                )
                if sibling is not widget and is_surface(sibling) and sibling.isVisible()
            ]
        for surface in tried:
            track = surface.track_at(QPointF(surface.mapFromGlobal(at)))
            if track is not None:
                return surface, track
        return None

    def _follow_month(self, at: QPoint) -> None:
        """Over a date, the hand asks the window whether the block can go there, and says so."""
        widget = QApplication.widgetAt(at)
        while widget is not None and not is_date_surface(widget):
            widget = widget.parentWidget()
        target = widget.date_at(QPointF(widget.mapFromGlobal(at))) if widget is not None else None
        held = self._held
        assert held is not None
        verdict = None
        if target and held.block_id and target != held.from_iso and self.date_judge is not None:
            verdict = self.date_judge(held.block_id, held.from_iso, target)
        words = f"{clock_text(held.origin.start) if held.origin else ''} {held.title}".strip()
        if verdict is not None and not verdict.ok and verdict.words:
            words = verdict.words
        elif target and target != held.from_iso:
            words += f" → {DAYS[date.fromisoformat(target).weekday()]} {int(target[8:])}"
        self._float(words, at, refused=verdict is not None and not verdict.ok)
        if (target, verdict) != (self.month_target, self.month_verdict):
            self.month_target, self.month_verdict = target, verdict
            self.preview_changed.emit()

    def _float(self, words: str, at: QPoint, refused: bool = False) -> None:
        if bool(self._chip.property("refused")) != refused:
            # Red while the place under the pointer says no, as the hours draw a refused block.
            self._chip.setProperty("refused", refused)
            self._chip.style().unpolish(self._chip)
            self._chip.style().polish(self._chip)
        self._chip.setText(words)
        self._chip.adjustSize()
        # Beside the pointer, and never past the window's edge, where its words would be cut off.
        host = self.parent()
        spot = host.mapFromGlobal(at) + QPoint(14, 10)
        room = host.rect()
        spot.setX(max(room.left(), min(spot.x(), room.right() - self._chip.width() - 4)))
        spot.setY(max(room.top(), min(spot.y(), room.bottom() - self._chip.height() - 4)))
        self._chip.move(spot)
        self._chip.show()
        self._chip.raise_()

    # Scrolling while held

    def _watch_edge(self, at: QPoint) -> None:
        found = _edge_at(at)
        if found is None:
            self._edge = None
            self._scroller.stop()
            return
        area, direction = found
        if self._edge is None or self._edge[0] is not area or self._edge[1:3] != direction:
            now = time.monotonic()
            self._edge = (area, *direction, now)
            self._stepped_at, self._owed = now + DWELL_S, 0.0
            self._scroller.start()

    def _scroll_tick(self) -> None:
        if self._edge is None or self._held is None:
            self._scroller.stop()
            return
        area, dx, dy, since = self._edge
        if not isValid(area):
            self._edge = None
            return
        now = time.monotonic()
        if now - since < DWELL_S:
            return
        found = self._track or self._home
        if found is None:
            return
        # Whole pixels only, so what a step falls short of is owed to the next one.
        seconds = min(now - self._stepped_at, LONGEST_STEP_S)
        self._stepped_at = now
        self._owed += _pixels_per_minute(found[1]) * SCROLL_MINUTES_PER_S * seconds
        pixels = int(self._owed)
        self._owed -= pixels
        if dy:
            area.verticalScrollBar().setValue(area.verticalScrollBar().value() + dy * pixels)
        if dx:
            area.horizontalScrollBar().setValue(area.horizontalScrollBar().value() + dx * pixels)
        self._follow(self._last)

    # Letting go

    def _end(self, silent: bool) -> None:
        was_active, was_holding = self._active, self._held is not None
        if was_holding:
            QApplication.instance().removeEventFilter(self)
        self._held = self._source = self._tap = None
        self._home = self._track = None
        self._active = False
        self._edge = None
        self._owed = 0.0
        self._scroller.stop()
        self._chip.hide()
        had = self.preview is not None or self.month_target is not None
        self.preview = None
        self.month_target = None
        self.month_verdict = None
        if had:
            self.preview_changed.emit()
        if was_active:
            self.active_changed.emit(False)
        if was_holding:
            self.holding.emit(False)


def _pixels_per_minute(track: Track) -> float:
    """How many pixels a minute takes along a track, however it is laid, from its two ends."""
    a, b = track.point_for(track.first), track.point_for(track.last)
    return math.hypot(b.x() - a.x(), b.y() - a.y()) / (track.last - track.first)


def _edge_at(at: QPoint) -> tuple[QScrollArea, tuple[int, int]] | None:
    """The scroll area to scroll with the pointer at a global point, and which way: the nearest one
    holding the point that is within `EDGE_PX` of an edge it has room to scroll towards. Hours that
    scroll sideways on a page that scrolls down leave the page's bottom edge to the page."""
    widget = QApplication.widgetAt(at)
    while widget is not None:
        if isinstance(widget, QScrollArea):
            direction = _edge_direction(widget, at)
            if direction != (0, 0):
                return widget, direction
        widget = widget.parentWidget()
    return None


def _edge_direction(area: QScrollArea, at: QPoint) -> tuple[int, int]:
    inside = area.viewport().mapFromGlobal(at)
    port = area.viewport().rect()
    if area.verticalScrollBar().maximum() > 0:
        return 0, -1 if inside.y() < EDGE_PX else 1 if inside.y() > port.height() - EDGE_PX else 0
    if area.horizontalScrollBar().maximum() > 0:
        return -1 if inside.x() < EDGE_PX else 1 if inside.x() > port.width() - EDGE_PX else 0, 0
    return 0, 0
