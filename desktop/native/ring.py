"""A countdown ring: the time left as an arc in the accent on a track, the number in the middle.

The focus screen draws its timer with it, and One thing's Countdown the next hour (decision 19 of
0.17), so the two screens look like one app. The ring draws and does not count: its owner says how
much is left each time the clock moves. Lines of the owner's own go in `above` and `below`, which sit
over and under the number inside the ring.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPaintEvent, QPen, QResizeEvent
from PySide6.QtWidgets import QSizePolicy, QSpacerItem, QVBoxLayout, QWidget

from desktop.native.motion import OUT, duration, moves
from desktop.native.tokens import WEIGHT_NUMBER, WEIGHT_STRONG, mix_oklab, type_pt

# The mock-up's ring (designs/one.js): 18 wide on a 340 circle in a 440 box, the scale outside it.
STROKE_SHARE = 18 / 440
SCALE_ROOM = 50 / 440
# The number is the display size several times over, as One thing's count is, and shrinks to fit.
NUMBER_TIMES = 3.2
# How far the track sits from the page towards the text, by the look's family.
TRACK_SHARE = {"light": 0.09, "dark": 0.15, "contrast": 0.32}
# A timer set but not started: its arc this share of the way from the track to the accent. Solid accent
# before Start read as a timer already finished.
WAITING_SHARE = 0.45
# How long the arc eases to a new minute at Normal, as the mock-up's does (designs/one.css).
ARC_MS = 300


@dataclass(frozen=True)
class RingColours:
    arc: str
    track: str
    number: str
    muted: str


def ring_colours(palette: dict) -> RingColours:
    """The ring in a look's colours: the accent on a soft track, the number in the text colour."""
    share = TRACK_SHARE.get(palette.get("family", "light"), TRACK_SHARE["light"])
    track = mix_oklab(palette["text"], palette["window"], share)
    return RingColours(palette["accent"], track, palette["text"], palette["muted"])


def arc_angles(left: float) -> tuple[int, int]:
    """Where the arc starts and how far it runs, in Qt's sixteenths of a degree: from the top,
    clockwise, as long as the share of the ring still to go."""
    share = min(max(left, 0.0), 1.0)
    return 90 * 16, -round(share * 360 * 16)


class CountdownRing(QWidget):
    """Square; the ring fills the smaller side. `set_left` takes the share still to go, 0 to 1."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("countdownRing")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._colours = RingColours("#3d6fc4", "#e6e8ec", "#111827", "#5b6474")
        self._left = 1.0
        self._waiting = False
        self._number = ""
        self._unit = ""
        self._scale = 1.0
        self._ticks = 0
        self._labels: tuple[str, ...] = ()
        self._ease = QVariantAnimation(self)
        self._ease.setEasingCurve(OUT)
        self._ease.valueChanged.connect(self._eased)
        column = QVBoxLayout(self)
        column.setSpacing(0)
        column.addStretch(1)
        self.above = QVBoxLayout()
        self.above.setSpacing(4)
        column.addLayout(self.above)
        self._slot = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        column.addItem(self._slot)
        self.below = QVBoxLayout()
        self.below.setSpacing(4)
        column.addLayout(self.below)
        column.addStretch(1)

    # --- what the owner says ------------------------------------------------------------------

    def set_colours(self, colours: RingColours) -> None:
        self._colours = colours
        self.update()

    def set_waiting(self, waiting: bool) -> None:
        """Set but not started: the arc is drawn softer, so the track still shows."""
        self._waiting = waiting
        self.update()

    def set_left(self, share: float) -> None:
        self._ease.stop()
        self._left = min(max(share, 0.0), 1.0)
        self.update()

    def run_down(self, since: float, share: float, level: str) -> None:
        """`share` left, the arc easing down to it from `since`, the share drawn before, where things
        may travel at `level`. A share that grew is a new countdown and is there at once: the arc run
        back round the ring would read as the clock going backwards."""
        self.set_left(share)
        length = duration(ARC_MS, level)
        if since <= self._left or length == 0 or not moves(level):
            return
        self._ease.setStartValue(min(since, 1.0))
        self._ease.setEndValue(self._left)
        self._ease.setDuration(length)
        self._ease.start()

    def _eased(self, share: object) -> None:
        self._left = float(share)
        self.update()

    def set_number(self, number: str, unit: str = "") -> None:
        self._number, self._unit = number, unit
        self.setAccessibleName(f"{number} {unit}".strip())
        self._place()
        self.update()

    def set_text_scale(self, scale: float) -> None:
        """The Text knob's factor, which the number grows and shrinks with, as every size does."""
        self._scale = scale
        self._place()
        self.update()

    def set_scale(self, ticks: int, labels: Sequence[str] = ()) -> None:
        """Marks around the outside, evenly from the top, and labels at every len(labels)-th: One
        thing's hour is 12 marks with "0", "15", "30" and "45"."""
        self._ticks, self._labels = ticks, tuple(labels)
        self._place()
        self.update()

    def lines_changed(self) -> None:
        """The owner's lines above or below the number changed their words or size: the number gives
        them the room they now need."""
        self._place()
        self.update()

    def number(self) -> str:
        return self._number

    def left(self) -> float:
        """The share the arc is drawn at now, part way there while it eases."""
        return self._left

    def inside(self) -> QSize:
        """The room inside the ring for the owner's lines and the number together."""
        inner = max(self._inner(), 0.0)
        return QSize(round(inner * 1.4), round(inner * 1.6))

    # --- geometry -------------------------------------------------------------------------------

    def _side(self) -> float:
        return float(min(self.width(), self.height()))

    def _stroke(self) -> float:
        return max(6.0, round(self._side() * STROKE_SHARE))

    def _radius(self) -> float:
        """The track's centre line."""
        room = self._side() * SCALE_ROOM if self._ticks else 2.0
        return self._side() / 2 - room - self._stroke() / 2

    def _inner(self) -> float:
        return self._radius() - self._stroke() / 2

    def _fonts(self) -> tuple[QFont, QFont]:
        number = QFont(self.font())
        number.setWeight(QFont.Weight(WEIGHT_NUMBER))
        number.setPointSizeF(type_pt("display", self._scale) * NUMBER_TIMES)
        unit = QFont(self.font())
        unit.setWeight(QFont.Weight(WEIGHT_STRONG))
        unit.setPointSizeF(type_pt("title", self._scale))
        # As wide as the inner circle allows at its middle, less a margin, with the unit beside it.
        room = self._inner() * 2 * 0.78
        wide = QFontMetricsF(number).horizontalAdvance(self._number) + self._unit_width(unit)
        if wide > room > 0:
            number.setPointSizeF(max(8.0, number.pointSizeF() * room / wide))
        # And no taller than the inner circle leaves once the owner's lines are in, or a two-line
        # title in a small ring ran into it.
        tall = self._number_room()
        high = QFontMetricsF(number).height() * 1.02
        if high > tall > 0:
            number.setPointSizeF(max(8.0, number.pointSizeF() * tall / high))
        return number, unit

    def _number_room(self) -> float:
        margins = self.layout().contentsMargins()
        width = self.width() - margins.left() - margins.right()
        lines = sum(
            part.heightForWidth(width) if part.hasHeightForWidth() else part.sizeHint().height()
            for part in (self.above, self.below)
        )
        return self.height() - margins.top() - margins.bottom() - lines

    def _unit_width(self, unit: QFont) -> float:
        if not self._unit:
            return 0.0
        return QFontMetricsF(unit).horizontalAdvance(" " + self._unit)

    def _place(self) -> None:
        """Keep the owner's lines inside the inner circle and make room for the number between them."""
        inner = self._inner()
        if inner <= 0:
            return
        side = self._side()
        across = round(side / 2 - inner * 0.7)
        down = round(side / 2 - inner * 0.8)
        self.layout().setContentsMargins(across, down, across, down)
        number, _unit = self._fonts()
        height = round(QFontMetricsF(number).height() * 1.02) if self._number else 0
        height = min(height, max(int(self._number_room()), 0))
        self._slot.changeSize(0, height, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.layout().invalidate()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place()

    # --- drawing --------------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        centre = QPointF(self.width() / 2, self.height() / 2)
        radius = self._radius()
        if radius <= 0:
            return
        box = QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius)
        colours = self._colours
        pen = QPen(QColor(colours.track), self._stroke())
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(box)
        if self._left > 0:
            arc = mix_oklab(colours.arc, colours.track, WAITING_SHARE) if self._waiting else colours.arc
            pen.setColor(QColor(arc))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap if self._left < 1 else Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            start, span = arc_angles(self._left)
            painter.drawArc(box, start, span)
        self._paint_scale(painter, centre, radius)
        self._paint_number(painter, centre)

    def _paint_scale(self, painter: QPainter, centre: QPointF, radius: float) -> None:
        if not self._ticks:
            return
        side = self._side()
        every = max(1, self._ticks // len(self._labels)) if self._labels else 0
        caption = QFont(self.font())
        caption.setPointSizeF(type_pt("caption", self._scale))
        painter.setFont(caption)
        metrics = QFontMetricsF(caption)
        for mark in range(self._ticks):
            turn = 2 * math.pi * mark / self._ticks
            major = bool(every) and mark % every == 0
            near = radius + side * 16 / 440
            far = radius + side * (26 if major else 22) / 440
            way = QPointF(math.sin(turn), -math.cos(turn))
            pen = QPen(QColor(self._colours.muted), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(centre + way * near, centre + way * far)
            if major and mark // every < len(self._labels):
                words = self._labels[mark // every]
                at = centre + way * (radius + side * 40 / 440)
                width = metrics.horizontalAdvance(words)
                painter.drawText(QPointF(at.x() - width / 2, at.y() + metrics.capHeight() / 2), words)

    def _paint_number(self, painter: QPainter, centre: QPointF) -> None:
        if not self._number:
            return
        number, unit = self._fonts()
        slot = self._slot.geometry()
        big = QFontMetricsF(number)
        wide = big.horizontalAdvance(self._number) + self._unit_width(unit)
        left = centre.x() - wide / 2
        baseline = slot.top() + (slot.height() - big.height()) / 2 + big.ascent()
        painter.setFont(number)
        painter.setPen(QColor(self._colours.number))
        painter.drawText(QPointF(left, baseline), self._number)
        if self._unit:
            painter.setFont(unit)
            painter.setPen(QColor(self._colours.muted))
            painter.drawText(QPointF(left + big.horizontalAdvance(self._number), baseline), " " + self._unit)
