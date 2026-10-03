"""How close the hours are: the levels a surface offers, the one it shows, and a scroll that keeps
the same minute in place while that changes.

A surface's hours sit in an `HoursScroll`. Ctrl and the wheel zoom about the pointer; Ctrl with =, -
or 0, the window's shortcuts for whichever hours it shows, zoom about the middle of what is on
screen, as do the two buttons in the corner. Hours that run
down scroll up and down, with a header, such as the week's day names, kept above them and exactly as
wide as the hours, so a name sits over its column whether or not a scroll bar shows. Hours that run
across scroll sideways, the plain wheel included, with the day names kept in a strip to their left,
below the corner, so they stay beside their lanes.

Each surface remembers its level on this device, in the look file, as pixels an hour. A level that
is no longer offered is read as the nearest one that is.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QVBoxLayout,
    QWidget,
)

from desktop.native import icons
from desktop.native.hours.canvas import HoursCanvas
from desktop.native.hours.geometry import FIRST, LAST, Axis
from desktop.native.look import ZOOM_PILL_PX
from desktop.native.motion import EASE_MS, OUT, duration, moves
from desktop.native.weekmodel import WeekModel
from desktop.native.widgets import overlay_scroll_bars

KEY = re.compile(r"[a-z]+\.[a-z]+")
# With Ctrl, anywhere in the window: zoom in, out, or back to the surface's own level.
ZOOM_KEYS = {Qt.Key.Key_Equal: 1, Qt.Key.Key_Plus: 1, Qt.Key.Key_Minus: -1, Qt.Key.Key_0: 0}
# Hours with neither now nor a block to show open at 08:00.
OPENS = 8 * 60
# Minutes shown before now when hours open with now near the start of what shows.
NOW_MARGIN = 45
# The zoom pill's minus and plus, as the mock-up draws them.
ZOOM_ICON_PX = 14


@dataclass(frozen=True)
class Scale:
    """The pixels an hour a surface offers, smallest first, and the one it opens at."""

    key: str
    levels: tuple[int, ...]
    default: int

    def __post_init__(self) -> None:
        if KEY.fullmatch(self.key) is None or len(self.key) > 40:
            raise ValueError(f"{self.key!r} cannot be kept in the look file: use design.surface, a to z")

    def nearest(self, px: object) -> int:
        if not isinstance(px, int) or isinstance(px, bool):
            return self.default
        return min(self.levels, key=lambda level: (abs(level - px), level))

    def step(self, px: int, by: int) -> int:
        at = self.levels.index(self.nearest(px))
        return self.levels[min(max(at + by, 0), len(self.levels) - 1)]


def sanitize_zoom(raw: object) -> dict[str, int]:
    """The remembered levels, whatever the file on disk says."""
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, int] = {}
    for key, px in raw.items():
        if len(clean) >= 32:
            break
        named = isinstance(key, str) and len(key) <= 40 and KEY.fullmatch(key) is not None
        if named and isinstance(px, int) and not isinstance(px, bool) and 8 <= px <= 480:
            clean[key] = px
    return clean


def opening_minute(week: WeekModel, today: int | None, now: int | None, day: int | None = None) -> int:
    """Where hours open: now, on today or on this week; otherwise the first block of the day shown,
    or of the week; otherwise the start of a school day."""
    if today is not None and now is not None and day in (None, today):
        return now
    items = week.occurrences if day is None else week.on_day(day)
    return min((item.start for item in items), default=OPENS)


class ZoomButton(QPushButton):
    """A square button whose natural size is the square it is drawn at."""

    side = 24

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.side, self.side)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()


class ZoomButtons(QWidget):
    """Zoom out and zoom in for the corner above the hour labels: a small "− +" pill (decision 12)."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(f"{name}Zoom")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.pill = QWidget()
        self.pill.setProperty("zoomPill", True)
        self.pill.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.pill.setFixedHeight(ZOOM_PILL_PX)
        inside = QHBoxLayout(self.pill)
        inside.setContentsMargins(1, 1, 1, 1)
        inside.setSpacing(0)
        self.out = self._button("minus", f"{name}ZoomOut", "Zoom out", "Ctrl+-")
        self.into = self._button("plus", f"{name}ZoomIn", "Zoom in", "Ctrl+=")
        divider = QWidget()
        divider.setObjectName("zoomDivider")
        divider.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        divider.setFixedSize(1, ZOOM_PILL_PX // 2)
        inside.addWidget(self.out)
        inside.addWidget(divider, 0, Qt.AlignmentFlag.AlignVCenter)
        inside.addWidget(self.into)
        row.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

    def _button(self, icon: str, name: str, words: str, keys: str) -> ZoomButton:
        button = ZoomButton()
        button.setObjectName(name)
        button.setProperty("zoom", True)
        button.side = ZOOM_PILL_PX - 2
        button.setFixedSize(button.side, button.side)
        button.setIconSize(QSize(ZOOM_ICON_PX, ZOOM_ICON_PX))
        icons.tint(button, icon)
        button.setToolTip(f"{words} on the hours ({keys}; Ctrl+0 goes back)")
        button.setAccessibleName(f"{words} on the hours")
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        return button


class HoursScroll(QScrollArea):
    """Hours that scroll and zoom along the way their time runs, with a header kept beside them."""

    # A level the student chose, to remember: the scale's key and its pixels an hour.
    zoomed = Signal(str, int)

    def __init__(
        self,
        canvas: HoursCanvas,
        scale: Scale,
        length_for: Callable[[int], int],
        *,
        name: str,
        gutter: float,
        axis: Axis = Axis.DOWN,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(f"{name}Scroll")
        self.canvas, self.scale, self.axis = canvas, scale, axis
        self.px = scale.default
        self._length_for = length_for
        self._gutter = gutter
        self._pending: tuple[int, int | None, bool, int | None] | None = None
        # The minute at the start of what showed when the hours were hidden, until it is put back,
        # and where the bar stopped while there was no room yet to put it back.
        self._kept: float | None = None
        self._short_at: int | None = None
        # A minute opened in the middle of what shows, or at its end, and where the bar was put for
        # it: kept there while what shows changes size, as a new look's taller header makes it,
        # until the student scrolls.
        self._centre: float | None = None
        self._at_end = False
        self._keep: int | None = None
        self._placed: int | None = None
        # The week, or day, these hours last opened on.
        self._opened: object = None
        # Where the student left each week or day these hours showed: the minute at its start.
        self._positions: dict[object, float] = {}
        # The minute at the start of what showed when the bar last moved. Hours with no room cannot
        # say where they are, and a day is left while they have none (see `_left_at`).
        self._top: float | None = None
        # The header first: the scroll area starts filtering events as soon as it holds the hours.
        self.buttons = ZoomButtons(name)
        self.buttons.out.clicked.connect(lambda: self.zoom_by(-1))
        self.buttons.into.clicked.connect(lambda: self.zoom_by(1))
        self.header = QWidget(self)
        self.header.setObjectName(f"{name}Header")
        self._row: QBoxLayout = QHBoxLayout(self.header) if self._down else QVBoxLayout(self.header)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        self._row.addWidget(self.buttons, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.header.installEventFilter(self)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # The hours inside it are the Tab stop; the sheet around them is not a second one.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        overlay_scroll_bars(self)
        self.setWidgetResizable(True)
        across = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        (self.setHorizontalScrollBarPolicy if self._down else self.setVerticalScrollBarPolicy)(across)
        self.setWidget(canvas)
        self._fix_length(length_for(self.px))
        # Connected before any design's own listener, such as Retro's drawn bar, so it sees the value
        # the range is about to cut.
        self._bar().rangeChanged.connect(self._cut)
        self._bar().valueChanged.connect(self._moved)
        canvas.zoom_asked.connect(self._asked)
        canvas.labels_changed.connect(self._place_header)
        self._show_limits()

    @property
    def _down(self) -> bool:
        return self.axis is Axis.DOWN

    def _bar(self) -> QScrollBar:
        return self.verticalScrollBar() if self._down else self.horizontalScrollBar()

    def _port_length(self) -> int:
        return self.viewport().height() if self._down else self.viewport().width()

    def _fix_length(self, length: int) -> None:
        if self._down:
            self.canvas.setFixedHeight(length)
        else:
            self.canvas.setFixedWidth(length)

    def set_header(self, content: QWidget) -> None:
        """What is kept beside the hours: over them, right of the corner, and exactly as wide as
        they are, when time runs down; left of them, under the corner, and exactly as tall as they
        are below the canvas's own header, when time runs across."""
        self._row.addWidget(content, 1)
        self._place_header()

    # Zoom

    def restore(self, remembered: Mapping[str, int]) -> None:
        """The level this device last chose for this surface, if any. Nothing is remembered again."""
        if self.scale.key in remembered:
            self._apply(self.scale.nearest(remembered[self.scale.key]), None)

    def zoom_by(self, steps: int, anchor: float | None = None) -> None:
        """Zoom in (positive) or out, keeping the minute at `anchor`, a height in the viewport, in
        place. Without one, the middle of what is on screen stays put. Nothing moves while a drag is
        under way: the block under the pointer must stay under it."""
        if self.canvas.hand.busy:
            return
        px = self.scale.default if steps == 0 else self.scale.step(self.px, steps)
        if px != self.px:
            self._apply(px, anchor)
            self.zoomed.emit(self.scale.key, px)

    def _asked(self, steps: int, at: object) -> None:
        if isinstance(at, QPointF):
            along = at.y() if self._down else at.x()
            self.zoom_by(steps, along - self._bar().value())
        else:
            self.zoom_by(steps)

    def _apply(self, px: int, anchor: float | None) -> None:
        bar = self._bar()
        length = self._port_length()
        at = length / 2 if anchor is None else min(max(anchor, 0.0), float(length))
        minute = self._minute_at(bar.value() + at)
        self.px = px
        self._fix_length(self._length_for(px))
        self._show_limits()
        if not self.isVisible():
            return
        self._lay_out_now()
        if minute is not None and self.canvas.tracks:
            bar.setValue(round(self._y_for(minute) - at))

    def _lay_out_now(self) -> None:
        """Give the hours their size and the scroll bar its range now rather than on the next pass,
        so a time can be put on screen straight away."""
        length = self._length_for(self.px)
        port = self.viewport()
        self.canvas.resize(port.width(), length) if self._down else self.canvas.resize(length, port.height())
        self.canvas.relayout()
        self._bar().setRange(0, max(0, length - self._port_length()))

    def _show_limits(self) -> None:
        self.buttons.out.setEnabled(self.px > self.scale.levels[0])
        self.buttons.into.setEnabled(self.px < self.scale.levels[-1])

    # Scrolling to a time

    def scroll_to(
        self, minute: int, above: int | None = 90, end: bool = False, keep: int | None = None
    ) -> None:
        """Put `minute` near the start of what shows, with `above` minutes of the day before it, or
        in the middle of what shows when `above` is None, or at the end of what shows when `end` is
        set; with `end`, `keep` is a minute that stays on screen, NOW_MARGIN minutes from the start,
        when the end and it do not both fit. Hours that are not on screen yet do it when they are
        shown, and only then. Shown while their page is still being laid out, they may not reach it
        yet; they do once they can."""
        self._pending = (minute, above, end, keep)
        self._kept = self._short_at = None
        self._centre = minute if above is None or end else None
        self._at_end, self._keep = end, keep
        if not self.isVisible():
            return
        self._lay_out_now()
        if self.canvas.tracks:
            self._pending = None
            half = self._port_length() / 2 / self.canvas.tracks[0].per_minute()
            self._kept = self._start_for_end(minute) if end else minute - (half if above is None else above)
            self._put_back()
            self._placed = self._bar().value()

    def _start_for_end(self, end: float) -> float:
        """The minute at the start of what shows when `end` is at its end, or `_keep` would be less than
        NOW_MARGIN minutes from the start."""
        start = end - self._port_length() / self.canvas.tracks[0].per_minute()
        if self._keep is not None:
            start = min(start, self._keep - NOW_MARGIN)
        return max(start, 0)

    def reveal(self, minute: int, above: int, level: str) -> None:
        """Bring `minute` into sight as `scroll_to` puts it, easing there where things may travel, and
        not at all when it already shows with `above` minutes before it: after a plan the grid jumped
        to homework that was already on screen (Grok Bot's 0.17.0 audit, T7)."""
        bar = self._bar()
        start = bar.value()
        top = self._minute_at(start)
        if top is not None and self.canvas.tracks:
            shown = self._port_length() / self.canvas.tracks[0].per_minute()
            if top + min(above, shown / 4) <= minute <= top + shown - 60:
                return
        self.scroll_to(minute, above)
        end = bar.value()
        length = duration(EASE_MS + 60, level)
        if end == start or length == 0 or not moves(level):
            return
        glide = QVariantAnimation(self)
        glide.setStartValue(start)
        glide.setEndValue(end)
        glide.setDuration(length)
        glide.setEasingCurve(OUT)
        glide.valueChanged.connect(lambda value: bar.setValue(round(value)))
        bar.setValue(start)
        glide.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def open_at(
        self, key: object, minute: int, above: int | None = 90, end: bool = False, keep: int | None = None
    ) -> None:
        """Open a new week or day once, and restore its position when it is visited again."""
        if key != self._opened:
            if self._opened is not None:
                left = self._left_at()
                if left is None:
                    self._positions.pop(self._opened, None)
                else:
                    self._positions[self._opened] = left
            self._opened = key
            if key in self._positions:
                self._pending = self._centre = None
                self._kept = self._positions[key]
                self._short_at = None
                if self.isVisible():
                    self._put_back()
            else:
                self.scroll_to(minute, above, end, keep)

    def take_places(self, before: HoursScroll) -> None:
        """Go back where the student left each week and day on `before`, the hours these replace."""
        self._positions = dict(before._positions)
        left = before._left_at() if before._opened is not None else None
        if left is not None:
            self._positions[before._opened] = left

    def forget(self, week_start: str | None = None) -> None:
        """Reopen a week's hours, or forget the whole session when no week is given."""
        if week_start is None:
            self._opened = None
            self._positions.clear()
            return
        self._positions = {key: position for key, position in self._positions.items()
                           if (key[0] if isinstance(key, tuple) else key) != week_start}
        opened_week = self._opened[0] if isinstance(self._opened, tuple) else self._opened
        if opened_week == week_start:
            self._opened = None

    def _left_at(self) -> float | None:
        """The minute to come back to: the one waiting to be put at the start of what shows, else the
        one there now, else the last one there while the hours had room, as Clay's open card has none
        when the day it slid away from is left. None when a time was asked for and never shown: the
        student has not seen these hours, and they open afresh."""
        if self._pending is not None:
            return None
        bar = self._bar()
        if self._kept is not None and (
            self._short_at is None or bar.value() == min(self._short_at, bar.maximum())
        ):
            return self._kept
        shown = self._minute_at(bar.value())
        return self._top if shown is None else shown

    def _moved(self, value: int) -> None:
        shown = self._minute_at(value)
        if shown is not None:
            self._top = shown

    def focusNextPrevChild(self, next: bool) -> bool:  # noqa: N802
        # QScrollArea's own then scrolls to show the child that had the focus: for hours longer than
        # what shows, a jump to their middle on Tab and whenever the hours are hidden.
        return QWidget.focusNextPrevChild(self, next)

    def hideEvent(self, event: object) -> None:  # noqa: N802
        super().hideEvent(event)
        self._kept, self._short_at = self._minute_at(self._bar().value()), None
        self._centre = None

    def _keep_centre(self) -> None:
        """The minute opened in the middle, or at the end, stays there through a resize, unless the student
        scrolled."""
        if self._centre is None or not self.isVisible() or not self.canvas.tracks:
            return
        bar = self._bar()
        if bar.value() != self._placed:
            self._centre = None
            return
        self._lay_out_now()
        if self._at_end:
            bar.setValue(round(self._y_for(self._start_for_end(self._centre))))
        else:
            bar.setValue(round(self._y_for(self._centre) - self._port_length() / 2))
        self._placed = bar.value()

    def showEvent(self, event: object) -> None:  # noqa: N802
        """Hours shown again start at the minute they started at when hidden, however the design
        parked them, unless a time was asked for meanwhile."""
        super().showEvent(event)
        self._place_header()
        if self._pending is not None:
            self.scroll_to(*self._pending)
        elif self._kept is not None:
            self._put_back()

    def _put_back(self) -> None:
        """Put the kept minute at the start of what shows. A design still laying out its page can
        show the hours wider than they end up, with no room to start there, or with no room at all:
        the bar stops where it can, and the minute is put back when they have the room, unless the
        student has scrolled."""
        self._lay_out_now()
        kept, bar = self._kept, self._bar()
        if kept is None:
            return
        if not self.canvas.tracks:
            self._short_at = bar.value()
            return
        wanted = round(self._y_for(kept))
        bar.setValue(wanted)
        if bar.value() == wanted:
            self._kept = self._short_at = None
        else:
            self._short_at = bar.value()

    def _cut(self, _low: int, high: int) -> None:
        """A page still laying itself out, as Retro's is after a drop, can give the hours a little less
        to scroll for a moment, and the bar is cut back to that shorter end. Where they were is kept,
        and put back when the room returns, unless the student scrolls first. Qt says the range
        changed before it cuts the value, so the value here is still the one on screen."""
        bar = self._bar()
        if self._kept is None and self.isVisible() and self.canvas.tracks and bar.value() > high:
            self._kept, self._short_at = self._minute_at(bar.value()), high

    def _minute_at(self, along: float) -> float | None:
        """The minute at a distance along the hours, down or across."""
        track = self.canvas.tracks[0] if self.canvas.tracks else None
        if track is None:
            return None
        start = track.area.top() if self._down else track.area.left()
        return track.first + (along - start) / track.per_minute()

    def _y_for(self, minute: float) -> float:
        """How far along the hours, down or across, a minute lies."""
        track = self.canvas.tracks[0]
        start = track.area.top() if self._down else track.area.left()
        return start + track.offset(minute)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        # Lanes have nothing to scroll up and down, so the wheel moves them through the day.
        if self._down or event.angleDelta().x():
            super().wheelEvent(event)
            return
        bar = self._bar()
        bar.setValue(bar.value() - round(event.angleDelta().y() / 120 * 3 * bar.singleStep()))
        event.accept()

    # The header and the corner

    def _place_header(self) -> None:
        row = self.buttons.layout()
        corner = max(self._gutter, float(self.buttons.pill.sizeHint().width() + 10))
        if self._down:
            first = min((track.first for track in self.canvas.tracks), default=FIRST)
            last = max((track.last for track in self.canvas.tracks), default=LAST)
            needed = self.canvas.painter.hour_gutter(self.canvas.font(), first, last, self.canvas.now_min)
            corner = max(corner, float(ceil(needed)))
        self.buttons.setFixedWidth(round(corner))
        row.setContentsMargins(4, 0, 0, 0)
        if not self._down:
            self._place_side(round(corner))
            return
        if corner != self.canvas.gutter:
            self.canvas.gutter = corner
            self.canvas.relayout()
        tall = max(30, self.header.sizeHint().height())
        if self.viewportMargins().top() != tall:
            self.setViewportMargins(0, tall, 0, 0)
        port = self.viewport().geometry()
        self.header.setGeometry(QRect(port.left(), port.top() - tall, port.width(), tall))

    def _place_side(self, wide: int) -> None:
        """Across: the corner sits over the strip, as tall as the canvas's own header of hours, and
        the strip is as tall as the lanes, so each name sits beside its lane."""
        tall = max(30, self.buttons.sizeHint().height() + 6)
        if tall > self.canvas.header:
            self.canvas.header = tall
            self.canvas.relayout()
        self.buttons.setFixedHeight(round(self.canvas.header))
        if self.viewportMargins().left() != wide:
            self.setViewportMargins(wide, 0, 0, 0)
        port = self.viewport().geometry()
        self.header.setGeometry(QRect(port.left() - wide, port.top(), wide, port.height()))

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_header()
        if self._pending is not None and self.isVisible():
            # Asked for a time while they had no room, as Clay's open card sliding in from a narrow
            # neighbour: they go there once they have some.
            self.scroll_to(*self._pending)
        if self._short_at is not None and self.isVisible():
            # Hours that grew pull the bar back with them; that is not the student scrolling.
            if self._bar().value() == min(self._short_at, self._bar().maximum()):
                self._put_back()
            else:
                self._kept = self._short_at = None
        self._keep_centre()

    def viewportEvent(self, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            # A scroll bar that comes or goes changes the width the hours have.
            self._place_header()
            self._keep_centre()
        return super().viewportEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.header and event.type() in (
            QEvent.Type.LayoutRequest,
            QEvent.Type.StyleChange,
            QEvent.Type.FontChange,
        ):
            self._place_header()
        return super().eventFilter(watched, event)
