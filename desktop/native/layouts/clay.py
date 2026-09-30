"""Clay deck: the week as a row of clay cards, one day at a time (0.17's Card carousel).

The day in front is a large card of its hours, which scroll and zoom. The days either side peek at 70 %,
laid out smaller rather than shrunk, so their words stay on the type scale, and they show the stretch
of the day the card in front shows, with its hours labelled. A card is whole or out of sight, never
cut by the window's edge. The round arrows beside the card, or the wheel over the row, slide
it a day at a time. Every card is live hours on the window's hand: a block goes to a neighbour by a
drop on it, and further by resting on an arrow while it is held, which slides the row. Homework not
placed yet rests in a pressed-in dish under the row.

Day is the same row with its day's card open wider: its hours, and beside them the day's hours by
kind and, today, what is left of it.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable
from datetime import date

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontInfo,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop.native import icons
from desktop.native.calendar import CATEGORIES, DAY_FULL, DAYS, category_icon
from desktop.native.fonts import at_scale, caption, time_font, weighted
from desktop.native.hours.canvas import (
    BOOK,
    HOMEWORK_CATEGORIES,
    INLINE_GAP,
    BlockPainter,
    Drawn,
    HoursCanvas,
    word_elide,
)
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.classic import open_hours
from desktop.native.hours.geometry import BETWEEN, FIRST, LAST, Axis, LinearTrack
from desktop.native.hours.hand import Hand
from desktop.native.hours.zoom import HoursScroll, Scale
from desktop.native.layouts.base import (
    LayoutView,
    Scene,
    base_sheet,
    css,
    empty,
    family,
    family_fill,
    label,
    plural,
    rules,
    scrolling,
)
from desktop.native.look import category_paint, contrast, readable_ink
from desktop.native.motion import app_level, between, duration, fade_away, hold_picture, moves
from desktop.native.tokens import (
    RADIUS_CARD,
    RADIUS_CONTROL,
    SHADOW_LARGE,
    WEIGHT_REGULAR,
    WEIGHT_STRONG,
    mix_oklab,
    type_pt,
)
from desktop.native.weekmodel import Occurrence, Waiting, WeekModel, clock_label, length_label, short_clock
from desktop.native.widgets import FlowLayout

# The card in front opens at the mock-up's 38 pixels an hour, Week and Day alike: 08:00 to 22:00 on a
# card as tall as the mock-up's.
WEEK_SCALE = Scale("clay.week", (30, 38, 48, 64, 96), 38)
DAY_SCALE = Scale("clay.day", (30, 38, 48, 64, 96), 38)
# The mock-up's measures at Normal text, in pixels: the card in front on Week and open on Day, the
# room between cards, above and below the one in front, the arrows, and each card's name row.
FRONT, OPEN = 452, 800
PEEK = 0.7
GAP = 32
# Above the card in front, and under it to the dish, where its shadow fades.
INSET, FOOT = 8, 24
ARROW = 44
FRONT_HEAD, PEEK_HEAD = 60, 48
# Inside a card, left, right and at its foot: the one in front, and a neighbour.
FRONT_PAD = (12, 16, 16)
PEEK_PAD = (8, 8, 12)
# The hour labels beside the hours in front, and room above and below them for the first and last.
LABELS = 56
# Beside a neighbour's labels: the 8 pixels hour labels keep from the hours, and 4 before them.
PEEK_LABEL_GAP = 12
END_ROOM = 20
# Day's hours by kind beside its hours, and the room between them.
SUMMARY, SUMMARY_GAP = 280, 24
# Round the page, at its sides and above and below; the dish's height; the fade at the row's ends.
AROUND = (20, 16)
DISH = 64
FADE = 80
# With less room than a card in front this wide and both neighbours whole, the one in front takes the
# row, keeping this much at its sides for the arrows.
LEAST = 340
SLIVER = 40
# A neighbour narrows to the room beside the card in front, but not below this; with less room it waits
# past the row's edge with the days further off.
PEEK_LEAST = 140
# At either end of the row, room kept clear of the cards, where the days further off slide in.
RESERVE = 24
RADIUS = 2 * RADIUS_CARD
RADIUS_BLOCK = round(1.2 * RADIUS_CARD)
SLIDE_MS = 240
# Resting a held block on an arrow this long slides the row a day.
DWELL_S = 0.5
# The stretch of the day Day's summary counts, as the mock-up does.
DAY_FROM, DAY_TO = 8 * 60, 22 * 60
# A block this short on the card in front says nothing; the mock-up's one line starts here.
LINE_LEAST = 15
TOP_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop


def _paint(tokens: dict[str, str], category: str) -> tuple[str, str]:
    """A category's fill and mark in the one family, on this design's cards."""
    fill, mark = category_paint(category, {"family": family(tokens), "panel": tokens["surface"]})
    return fill or tokens["surface"], mark or tokens["line"]


def _length(px: int) -> int:
    return round((LAST - FIRST) / 60 * px) + END_ROOM


def _covered(items: Iterable[Occurrence], start: int, end: int) -> int:
    """How many minutes from `start` to `end` any of `items` takes, each minute once."""
    taken, at = 0, start
    for item in sorted(items, key=lambda entry: entry.start):
        first, last = max(item.start, at), min(item.end, end)
        if last > first:
            taken += last - first
            at = last
    return taken


def day_kinds(week: WeekModel, day: int) -> list[tuple[str, int]]:
    """A day's minutes from 08:00 to 22:00 by category, the most first."""
    kinds: dict[str, int] = {}
    for item in week.on_day(day):
        minutes = min(item.end, DAY_TO) - max(item.start, DAY_FROM)
        if minutes > 0:
            kinds[item.category] = kinds.get(item.category, 0) + minutes
    return sorted(kinds.items(), key=lambda pair: -pair[1])


def left_today(week: WeekModel, day: int, minute: int) -> tuple[int, int, Occurrence | None]:
    """What is still ahead today until 22:00: the minutes planned, the minutes free, and what is next."""
    ahead = [item for item in week.on_day(day) if item.live and item.end > minute]
    planned = _covered(ahead, minute, DAY_TO)
    coming = min((item for item in ahead if item.start > minute), key=lambda item: item.start, default=None)
    return planned, max(DAY_TO - minute - planned, 0), coming


def slots(width: float, height: float, front: int, scale: float, *, wide: bool) -> dict[int, QRectF]:
    """Where each day's card lies in a row `width` by `height`: the day in front in the middle at full
    size, and each other day a step further out at 70 % of its height, the room between them kept. The
    card in front narrows so both its neighbours show whole; with too little room even for that, it
    takes the row. Open on Day, it keeps the mock-up's width while the row has it, and its neighbours
    narrow to the room beside it. A card is whole in the row or wholly past its ends, where the days
    further off wait to slide in: one cut by the window's edge read as clipped."""
    gap, sliver = GAP * scale, SLIVER * scale
    wanted = (OPEN if wide else FRONT) * scale
    whole = (width - 2 * gap - 2 * RESERVE * scale) / (1 + 2 * PEEK)
    if not wide and whole >= LEAST * scale:
        across = min(wanted, whole)
    else:
        across = min(wanted, width - 2 * (gap + sliver))
    across, tall = max(across, 1.0), max(height - (INSET + FOOT) * scale, 1.0)
    narrow, short = across * PEEK, tall * PEEK
    left, middle = (width - across) / 2, INSET * scale + tall / 2
    beside = left - gap - RESERVE * scale
    if beside >= PEEK_LEAST * scale:
        narrow = min(narrow, beside)
    found = {front: QRectF(left, middle - tall / 2, across, tall)}
    for day in range(7):
        step = day - front
        if step > 0:
            x = left + across + gap + (step - 1) * (narrow + gap)
        elif step < 0:
            x = left + step * (narrow + gap)
        else:
            continue
        found[day] = QRectF(x, middle - short / 2, narrow, short)
    # The first card each way that the edge would cut, and every card past it, move out past the edge.
    after = [day for day in range(front + 1, 7) if found[day].right() > width]
    if after:
        shift = max(width - found[after[0]].left(), 0.0)
        for day in after:
            found[day].translate(shift, 0)
    before = [day for day in range(front - 1, -1, -1) if found[day].left() < 0]
    if before:
        shift = min(-found[before[0]].right(), 0.0)
        for day in before:
            found[day].translate(shift, 0)
    return found


def _soft(
    painter: QPainter, rect: QRectF, radius: float, y: float, blur: float, spread: float, colour: QColor,
    alpha: float,
) -> None:
    """A soft shadow under a rounded rectangle, as CSS's box-shadow: layers from its inner edge to
    its outer edge, so it fades over the blur."""
    layers = 12
    shade = QColor(colour)
    shade.setAlphaF(alpha / layers)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shade)
    for layer in range(layers):
        grow = spread - blur / 2 + blur * (layer + 0.5) / layers
        if rect.width() + 2 * grow <= 0 or rect.height() + 2 * grow <= 0:
            continue
        around = rect.translated(0, y).adjusted(-grow, -grow, grow, grow)
        painter.drawRoundedRect(around, max(radius + grow, 0), max(radius + grow, 0))


def paint_clay(painter: QPainter, rect: QRectF, tokens: dict[str, str], radius: float, *, lifted: bool,
               shadow: bool = True) -> None:
    """Claymorphism, tempered as the mock-up draws it: the card's surface a touch deeper at its foot,
    a highlight along its top edge, a soft shade inside its foot, a hairline ring, and a soft shadow
    under it, stronger under the one lifted in front. On a dark page the shadow is the large one."""
    dark = family(tokens) == "dark"
    text, surface = tokens["text"], tokens["surface"]
    painter.save()
    if shadow:
        if dark:
            large = SHADOW_LARGE
            _soft(painter, rect, radius, large.y, large.blur, 0, QColor("#000000"), large.dark_opacity)
        else:
            ink = QColor(text)
            _soft(painter, rect, radius, 1 if not lifted else 2, 2 if not lifted else 4, 0, ink, 0.06)
            if lifted:
                _soft(painter, rect, radius, 22, 40, -16, ink, 0.32)
            else:
                _soft(painter, rect, radius, 12, 24, -14, ink, 0.24)
    shape = QPainterPath()
    shape.addRoundedRect(rect, radius, radius)
    ramp = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    ramp.setColorAt(0, QColor(surface))
    ramp.setColorAt(0.55, QColor(surface))
    ramp.setColorAt(1, QColor(mix_oklab(text, surface, 0.03)))
    painter.fillPath(shape, ramp)
    painter.setClipPath(shape)
    shade = QLinearGradient(QPointF(0, rect.bottom() - 8), QPointF(0, rect.bottom()))
    low = QColor(tokens["bg"] if dark else text)
    low.setAlphaF(0.0)
    shade.setColorAt(0, low)
    low.setAlphaF(0.45 if dark else 0.04)
    shade.setColorAt(1, low)
    painter.fillRect(QRectF(rect.left(), rect.bottom() - 8, rect.width(), 8), shade)
    shine = QColor("#ffffff") if not dark else QColor(text)
    shine.setAlphaF(1.0 if not dark else 0.10)
    painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 1.5), shine)
    painter.setClipping(False)
    ring = QColor(tokens["line"])
    ring.setAlphaF(0.8 if dark else 0.7)
    painter.setPen(QPen(ring, 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius - 0.5, radius - 0.5)
    if lifted and dark:
        painter.setPen(QPen(QColor(tokens["line"]), 1))
        painter.drawRoundedRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5), radius + 0.5, radius + 0.5)
    painter.restore()


class ClayPainter(BlockPainter):
    """Hours on a clay card: a faint rule at each hour, blocks as soft clay in the category family with
    the category's bar just inside their start edge, and the time now as an accent line from a dot,
    its time on a pill. The card in front says each block's times and length; a neighbour its times."""

    # The pill sits left of the hours, where their labels are: an hour label under it is left out.
    now_in_gutter = True

    def __init__(
        self, tokens: dict[str, str], *, full: bool = False, wide: bool = False, share: float = 1.0
    ) -> None:
        soft = mix_oklab(tokens["line"], tokens["surface"], 0.5)
        super().__init__(
            {
                "window": tokens["surface"],
                "hairline": soft,
                "rule": soft,
                "accent": tokens["accent"],
                "accent_ink": tokens["accent_ink"],
                "accent_text": tokens.get("accent_text", tokens["accent"]),
                "now": tokens.get("now", tokens["accent"]),
                "selection": tokens.get("selection", tokens["accent"]),
                "error": tokens["danger"],
                "text": tokens["text"],
                "muted": tokens["muted"],
            },
            wide=wide,
        )
        self.tokens = tokens
        self.full = full
        # The height of these hours against the card in front's, whose blocks the least a line needs is
        # measured on: a block that reads there reads here at the same length.
        self.share = share
        self.dark = family(tokens) == "dark"

    def background(self, painter: QPainter, rect: QRectF) -> None:
        """Nothing: the clay card under the hours is the row's."""

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        painter.setPen(QPen(self.c("rule"), 1))
        area = track.area
        for minute in range(-(-track.first // 60) * 60, track.last + 1, 60):
            at = area.top() + track.offset(minute)
            painter.drawLine(QPointF(area.left(), at), QPointF(area.right(), at))

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        mark = _paint(self.tokens, drawn.category)[1]
        fill = QColor(family_fill(drawn.category, self.tokens))
        if drawn.done or drawn.missed:
            fill = QColor(self.tokens["surface"])
        return fill, QColor(self.tokens["text"]), None, QColor(mark)

    def fonts(self, base: QFont) -> tuple[QFont, QFont]:
        """A block's title at 600 and its times, at the caption size on Week and the body size on Day.
        In a monospaced face, as Terminal's, letters sit 3 % closer, as the mock-up sets them, so a
        block's words still fit."""
        title, small = super().fonts(base)
        if self.wide:
            small = at_scale(time_font(base), "body", self.scale(base), WEIGHT_REGULAR)
        if QFontInfo(base).fixedPitch():
            for made in (title, small):
                made.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 97)
        return title, small

    def body(self, painter: QPainter, rect: QRectF, drawn: Drawn) -> None:
        fill, ink, _outline, edge = self.fills(drawn)
        assert edge is not None
        radius = min(RADIUS_BLOCK, rect.height() / 2, rect.width() / 2)
        shape = QPainterPath()
        shape.addRoundedRect(rect, radius, radius)
        under = QColor(self.tokens["bg"] if self.dark else edge)
        under.setAlphaF(0.6 if self.dark else 0.22)
        painter.fillPath(shape.translated(0, 1), under)
        painter.fillPath(shape, fill)
        painter.save()
        painter.setClipPath(shape)
        surface = self.tokens["surface"]
        shine = QColor(self.tokens["text"] if self.dark else mix_oklab(surface, fill.name(), 0.6))
        shine.setAlphaF(0.09 if self.dark else 1.0)
        painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 1), shine)
        painter.restore()
        tall = rect.height()
        inset = 2 if tall < 12 else 3 if tall < 30 else (6 if self.wide else 4)
        bar = QRectF(rect.left() + (7 if self.wide else 5), rect.top() + inset, 3, max(tall - 2 * inset, 2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(edge)
        painter.drawRoundedRect(bar, 1.5, 1.5)
        if drawn.held or drawn.chosen:
            refused = drawn.verdict is not None and not drawn.verdict.ok
            painter.setPen(QPen(self.c("error" if refused else "selection"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), max(radius - 1, 0), max(radius - 1, 0))
        if drawn.columns > 1 and not drawn.held:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            painter.drawEllipse(QPointF(rect.right() - 7, rect.top() + 7), 3.5, 3.5)

    def words(
        self,
        painter: QPainter,
        rect: QRectF,
        drawn: Drawn,
        ink: QColor,
        visible: QRectF,
        fill: QColor | None = None,
        edge: QColor | None = None,
    ) -> None:
        """As the mock-up writes a block: its title, then its times and on the card in front its length,
        each on its own line while the block is tall enough; "16:00–17:30 · 1 h 30 min" under the title
        on a shorter one; on one line the title and the most that fits after it; on a block shorter
        than a line, nothing, and its colour says it is there. A long title takes two lines where the
        block has room for them."""
        if drawn.held:
            super().words(painter, rect, drawn, ink, visible, fill, edge)
            return
        scale = self.scale(painter.font())
        title_font, small = self.fonts(painter.font())
        if self.wide and rect.height() + 0.5 < QFontMetricsF(title_font).height():
            # Too short for a line at the body size, as Dinner's half hour is: at the caption size.
            title_font = at_scale(painter.font(), "caption", scale, WEIGHT_STRONG)
            small = at_scale(time_font(painter.font()), "caption", scale, WEIGHT_REGULAR)
        tm, sm = QFontMetricsF(title_font), QFontMetricsF(small)
        tl, sl = tm.lineSpacing(), sm.lineSpacing()
        left, top, right = (18, 6, 12) if self.wide else (14, 4, 8)
        width = rect.width() - left - right
        tall = rect.height() - top - 3
        homework = category_icon(drawn.category) is not None
        book = round(tm.ascent())
        indent = book + 4 if homework else 0
        first_word = drawn.title.strip().split(" ", 1)[0]
        name_room = tm.horizontalAdvance(first_word + ("…" if first_word != drawn.title.strip() else ""))
        if homework and width - indent < name_room <= width:
            homework, indent = False, 0
        too_short = rect.height() + BETWEEN < (LINE_LEAST * scale + BETWEEN) * self.share
        if too_short or width < indent + tm.horizontalAdvance(drawn.title.strip()[:3]):
            return
        paper = fill if fill is not None else self.c("window")
        muted = QColor(mix_oklab(ink.name(), paper.name(), 0.74))
        said = [word for flag, word in ((drawn.done, "Finished"), (drawn.missed, "Missed")) if flag]
        times = drawn.times if self.full or not said else " · ".join([drawn.times, *said])
        extra = drawn.length + (" · Pinned" if drawn.pinned and not drawn.done else "")
        under: list[str] = []
        if self.full and tall + 0.5 >= tl + 2 * sl:
            under = [times, extra]
        elif tall + 0.5 >= tl + sl:
            joined = f"{times} · {extra}"
            under = [joined if self.full and sm.horizontalAdvance(joined) <= width else times]
        if under:
            most = 2 if tall + 0.5 >= 2 * tl + sl * len(under) else 1
            names = self._title_lines(drawn.title, tm, width, indent, most)
            y = rect.top() + top
            if rect.bottom() - visible.top() > 2 * tl:
                # The name stays in sight while the start of a long block is scrolled away.
                y = max(y, visible.top() + top)
            first = y
            painter.setFont(title_font)
            painter.setPen(ink)
            for at, name in enumerate(names):
                shift = indent if at == 0 else 0
                box = QRectF(rect.left() + left + shift, y, width - shift, tl)
                painter.drawText(box, TOP_LEFT, name)
                y += tl
            painter.setFont(small)
            painter.setPen(muted)
            for words in under:
                if y + sl > rect.bottom() + 1:
                    break
                shown = sm.elidedText(words, Qt.TextElideMode.ElideRight, width)
                painter.drawText(QRectF(rect.left() + left, y, width, sl), TOP_LEFT, shown)
                y += sl
        else:
            start = short_clock(drawn.span.start)
            ways = [f"{times} · {extra}", times, start] if self.full else [start]
            room = width - indent
            whole = tm.horizontalAdvance(drawn.title) + INLINE_GAP
            after = next((way for way in ways if whole + sm.horizontalAdvance(way) <= room), "")
            name = drawn.title if after else word_elide(drawn.title, tm, room)
            first = rect.top() + (rect.height() - tm.height()) / 2
            at = rect.left() + left + indent
            painter.setFont(title_font)
            painter.setPen(ink)
            painter.drawText(QRectF(at, first, room, tm.height()), TOP_LEFT, name)
            if after:
                beside = QRectF(
                    at + tm.horizontalAdvance(name) + INLINE_GAP,
                    first + max(tm.ascent() - sm.ascent(), 0.0),
                    sm.horizontalAdvance(after) + 1,
                    sm.height(),
                )
                painter.setFont(small)
                painter.setPen(muted)
                painter.drawText(beside, TOP_LEFT, after)
        if homework:
            at_book = QPointF(rect.left() + left, first + (tm.height() - book) / 2)
            self._book(painter, at_book, book, ink, paper, edge, category_icon(drawn.category) or BOOK)

    @staticmethod
    def _title_lines(title: str, metrics: QFontMetricsF, width: float, indent: float, most: int) -> list[str]:
        """The title on one line, or on two where there is room, broken at a word; shortened with "…"
        only where it must be."""
        words = title.split()
        if most == 1 or metrics.horizontalAdvance(title) <= width - indent:
            return [word_elide(title, metrics, width - indent)]
        for count in range(len(words) - 1, 0, -1):
            if metrics.horizontalAdvance(" ".join(words[:count])) <= width - indent:
                return [" ".join(words[:count]), word_elide(" ".join(words[count:]), metrics, width)]
        return [word_elide(title, metrics, width - indent)]

    def _book(self, painter: QPainter, at: QPointF, size: int, ink: QColor, paper: QColor,
              edge: QColor | None, icon_name: str = BOOK) -> None:
        """Keep the category icon readable against its block."""
        colour = edge if edge is not None and contrast(edge.name(), paper.name()) >= 4.5 else ink
        ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
        painter.drawPixmap(at, icons.pixmap(icon_name, colour.name(), size, ratio))

    def now(self, painter: QPainter, track: LinearTrack, minute: int) -> None:
        """An accent line across the day from a dot at its start, the time on a pill near the dot."""
        colour = self.c("now")
        area = track.area
        at = area.top() + track.offset(minute)
        painter.setPen(QPen(colour, 2))
        painter.drawLine(QPointF(area.left() - 2, at), QPointF(area.right(), at))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawEllipse(QPointF(area.left(), at), 4, 4)
        font = weighted(time_font(caption(painter.font())), WEIGHT_STRONG)
        words = clock_label(minute)
        metrics = QFontMetricsF(font)
        pill = QRectF(max(0, area.left() - metrics.horizontalAdvance(words) - 15),
                      at - (metrics.height() + 2) / 2, metrics.horizontalAdvance(words) + 12,
                      metrics.height() + 2)
        painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        painter.setPen(QColor(readable_ink(colour.name())))
        painter.setFont(font)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, words)


class ClayCanvas(HoursCanvas):
    """A card's hours. The rig and the tests find days through the row, which brings a day that is
    past its edge to the front first, as the arrows would."""

    def __init__(self, hand: Hand, painter: ClayPainter, lay_out, row: Row, *, gutter: float = 0) -> None:
        super().__init__(hand, painter, lay_out, gutter=gutter)
        self.row = row

    def day_name(self, day: int) -> QPoint:
        return self.row.name_point(day)

    def reveal(self, day: int, first: int, last: int) -> None:
        self.row.reveal(day, first, last)

    def in_view(self, day: int, minute: int) -> bool:
        return self.row.in_view(self, day, minute)


class Head(QPushButton):
    """A day's name with its date at the far end, today's in an accent chip, and on the card in front
    how much it holds. A click opens the day wherever that is not the view already. The name shortens
    to "Wed" before it would be cut."""

    def __init__(self, name: str, front: bool) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setProperty("kind", "head")
        self.setProperty("front", front)
        self.day = -1
        self._note = ""
        row = QHBoxLayout(self)
        row.setContentsMargins(4 if front else 6, 0, 4, 0)
        row.setSpacing(8)
        self.title = label("", "clayDayName")
        self.title.setProperty("front", front)
        self.note = label("", "clayNote")
        # Two labels shown in turn: Qt keeps a label's padding from its first styling.
        self.date = label("", "clayDate")
        self.chip = label("", "clayToday")
        for part in (self.title, self.note, self.date, self.chip):
            part.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            part.setIndent(0)
        row.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.note, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        row.addWidget(self.date, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_day(self, day: int, number: int, today: bool, note: str, opens: bool, dated: bool = True) -> None:
        """`dated` False leaves the date to the card's corner, as Day's open card has it past the hours."""
        self.day = day
        self._note = note
        self.note.setText(note)
        self.date.setText(str(number))
        self.chip.setText(str(number))
        self.date.setVisible(dated and not today)
        self.chip.setVisible(dated and today)
        self.setProperty("opens", opens)
        self.setProperty("day_target", day if opens else None)
        self.setCursor(Qt.CursorShape.PointingHandCursor if opens else Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if opens else Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(f"Show {DAY_FULL[day]}" if opens else DAY_FULL[day])
        self.setToolTip(f"Open {DAY_FULL[day]}" if opens else "")
        self.style().unpolish(self)
        self.style().polish(self)
        self._fit()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        """The whole name and the note; else the whole name alone; else "Wed", with the note if it fits."""
        if self.day < 0:
            return
        for part in (self.title, self.note, self.date, self.chip):
            part.ensurePolished()
        margins = self.layout().contentsMargins()
        tag = self.chip if self.chip.isVisibleTo(self) else self.date
        room = self.width() - margins.left() - margins.right() - 8
        if tag.isVisibleTo(self):
            room -= tag.sizeHint().width() + 8
        metrics = self.title.fontMetrics()
        note = self.note.fontMetrics().horizontalAdvance(self._note) + 8 if self._note else 0
        full, short = DAY_FULL[self.day], DAYS[self.day]
        for words, with_note in ((full, True), (full, False), (short, True), (short, False)):
            if metrics.horizontalAdvance(words) + (note if with_note else 0) <= room:
                break
        self.note.setVisible(bool(self._note) and with_note)
        self.title.setText(metrics.elidedText(words, Qt.TextElideMode.ElideRight, max(room, 0)))
        # At once, not on the next pass: a picture taken straight after, as setup's are, cut the name.
        self.layout().activate()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, super().minimumSizeHint().height())


class Card(QWidget):
    """A day beside the one in front: its name and date over its hours. The row paints its clay."""

    def __init__(self, day: int, row: Row, painter: ClayPainter) -> None:
        super().__init__(row)
        self.day = day
        box = QVBoxLayout(self)
        box.setSpacing(0)
        self.head = Head(f"clayDay{day}", front=False)
        self.head.clicked.connect(lambda _=False: row.opened.emit(self.day))
        self.hours = ClayCanvas(row.hand, painter, lambda area: row.peek_track(self.day, area), row)
        self.hours.setObjectName(f"clayPeek{day}")
        box.addWidget(self.head)
        box.addWidget(self.hours, 1)

    def dress(self, scale: float) -> None:
        """Its padding at this text size, and room left of its hours for their labels, as wide as the
        widest in the face and size they are written in and on the clock the student chose."""
        side, _right, foot = PEEK_PAD
        self.layout().setContentsMargins(round(side * scale), 0, round(side * scale), round(foot * scale))
        hours = self.hours
        hours.ensurePolished()
        base = hours.font()
        metrics = QFontMetricsF(at_scale(time_font(base), "caption", hours.painter.scale(base)))
        widest = max(metrics.horizontalAdvance(clock_label(hour * 60)) for hour in range(24))
        hours.gutter = math.ceil(widest) + PEEK_LABEL_GAP
        hours.relayout()


class Arrow(QPushButton):
    """A round clay button beside the card in front: the day before it, or the day after."""

    def __init__(self, name: str, icon: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.icon_name = icon
        self.tokens: dict[str, str] = {}
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self.tokens:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        paint_clay(painter, body, self.tokens, body.height() / 2, lifted=True, shadow=False)
        if self.underMouse() and self.isEnabled():
            hover = QColor(self.tokens["text"])
            hover.setAlphaF(0.06)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hover)
            painter.drawEllipse(body)
        if self.hasFocus() and self.property("keyfocus"):
            painter.setPen(QPen(QColor(self.tokens["accent"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(body.adjusted(1, 1, -1, -1))
        faint = mix_oklab(self.tokens["muted"], self.tokens["surface"], 0.5)
        colour = self.tokens["text"] if self.isEnabled() else faint
        side = round(body.height() * 20 / ARROW)
        picture = icons.pixmap(self.icon_name, colour, side, self.devicePixelRatioF())
        painter.drawPixmap(QPointF(body.center().x() - side / 2, body.center().y() - side / 2), picture)
        painter.end()


class Fade(QWidget):
    """The row's ends fading into the page, over the days two and more away."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.page = QColor("#ffffff")
        self.reach = FADE

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        clear = QColor(self.page)
        clear.setAlphaF(0.0)
        for start, end in ((0.0, self.reach), (float(self.width()), self.width() - self.reach)):
            ramp = QLinearGradient(QPointF(start, 0), QPointF(end, 0))
            ramp.setColorAt(0, self.page)
            ramp.setColorAt(1, clear)
            painter.fillRect(QRectF(min(start, end), 0, abs(end - start), self.height()), ramp)
        painter.end()


class Row(QWidget):
    """The days as cards in a row, one in front. It paints their clay; the cards and the hours in
    front draw what is on them. Week slides it here; Day asks the window for another day and slides
    when the window shows it."""

    # A day's name was clicked: open it on Day.
    opened = Signal(int)
    # On Day, the arrows, the wheel or a rest on an arrow moved to this day of the week, which may be
    # the Sunday before it (-1) or the Monday after (7).
    turned = Signal(int)

    def __init__(self, hand: Hand, keep: Callable[[HoursScroll], HoursScroll]) -> None:
        super().__init__()
        self.setObjectName("clayRow")
        self.setAccessibleName("The week as cards, one day at a time")
        self.hand = hand
        self._keep = keep
        self.scene: Scene | None = None
        self.tokens: dict[str, str] = {}
        self.scale = 1.0
        self._open = False
        self._peeks = True
        self._front = 0
        self._week_start = ""
        self._window = (DAY_FROM, DAY_TO)
        self._cards: dict[int, Card] = {}
        self._hours: dict[str, HoursScroll] = {}
        self._heads: dict[str, Head] = {}
        self._summary: QWidget | None = None
        self._rects: dict[int, QRectF] = {}
        self._from: dict[int, QRectF] = {}
        self._to: dict[int, QRectF] = {}
        self._wheel = 0
        self._fade = Fade(self)
        # Day's date, at the open card's far corner as the mock-up puts it: two labels shown in turn.
        self._date = label("", "clayDate")
        self._chip = label("", "clayToday")
        for stamp in (self._date, self._chip):
            stamp.setParent(self)
            stamp.hide()
        self.back = Arrow("clayBack", "chevron-left", self)
        self.ahead = Arrow("clayAhead", "chevron-right", self)
        self.back.clicked.connect(lambda _=False: self.turn(-1))
        self.ahead.clicked.connect(lambda _=False: self.turn(1))
        self._slide = QVariantAnimation(self)
        self._slide.setStartValue(0.0)
        self._slide.setEndValue(1.0)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.valueChanged.connect(self._slid)
        self._slide.finished.connect(lambda: self._put(self._to))
        self._dwell = QTimer(self)
        self._dwell.setInterval(50)
        self._dwell.timeout.connect(self._dwelt)
        self._dwell_on: QWidget | None = None
        self._dwell_since = 0.0
        hand.active_changed.connect(self._carrying)

    # What it shows

    @property
    def front(self) -> int:
        return self._front

    @property
    def hours(self) -> HoursScroll | None:
        """The hours in front: Week's or Day's."""
        return self._hours.get("day" if self._open else "week")

    def show_scene(self, scene: Scene, day: int | None, peeks: bool) -> None:
        """Show `scene`: on Day, `day` in front, open; on Week, the day already in front, or today or
        Monday when the week is new. A new day in the same week slides into place."""
        self.scene, self.tokens, self.scale = scene, scene.tokens, scene.scale
        self._build(scene)
        opened = day is not None
        mode = opened != self._open or peeks != self._peeks
        self._open, self._peeks = opened, peeks
        new_week = scene.week.week_start != self._week_start
        if new_week:
            self._week_start = scene.week.week_start
        if day is not None:
            front = day
        elif new_week:
            front = scene.today if scene.today is not None else 0
        else:
            front = self._front
        for key, scroll in self._hours.items():
            scroll.setVisible(key == ("day" if opened else "week"))
        self._fade.page = QColor(self.tokens["bg"])
        for arrow in (self.back, self.ahead):
            arrow.tokens = self.tokens
            arrow.setFixedSize(round(ARROW * self.scale), round(ARROW * self.scale))
        for card in self._cards.values():
            card.dress(self.scale)
            card.hours.set_painter(ClayPainter(self.tokens, share=PEEK))
        scroll = self.hours
        assert scroll is not None
        scroll.canvas.set_painter(ClayPainter(self.tokens, full=True, wide=opened))
        self._go(front, "slide" if not (mode or new_week) else "jump", force=True)
        week = scene.week
        if opened:
            open_hours(scroll, (week.week_start, front), week, scene.today, scene.minute, front)
        else:
            open_hours(scroll, week.week_start, week, scene.today, scene.minute)
        self._follow()
        self._fade.raise_()
        self.back.raise_()
        self.ahead.raise_()

    def set_summary(self, summary: QWidget | None) -> None:
        """What Day shows beside its hours, inside the open card."""
        if self._summary is not None:
            self._summary.setParent(None)
            self._summary.deleteLater()
        self._summary = summary
        if summary is not None:
            summary.setParent(self)
            summary.show()
            self._put(self._rects)
            self._fade.raise_()
            self.back.raise_()
            self.ahead.raise_()

    def _build(self, scene: Scene) -> None:
        if self._cards:
            return
        for day in range(7):
            self._cards[day] = Card(day, self, ClayPainter(scene.tokens, share=PEEK))
        for key, scale in (("week", WEEK_SCALE), ("day", DAY_SCALE)):
            canvas = ClayCanvas(
                self.hand, ClayPainter(scene.tokens, full=True, wide=key == "day"), self.front_track, self,
                gutter=round(LABELS * scene.scale),
            )
            canvas.setObjectName("clayHours")
            canvas.setAccessibleName("The day in front, hour by hour")
            name = f"clay{key.title()}"
            gutter = round(LABELS * scene.scale)
            scroll = self._keep(HoursScroll(canvas, scale, _length, name=name, gutter=gutter))
            scroll.setParent(self)
            head = Head(f"{name}Front", front=True)
            head.clicked.connect(lambda _=False, made=head: self._front_clicked(made))
            scroll.set_header(head)
            scroll.widget().setAutoFillBackground(False)
            scroll.verticalScrollBar().valueChanged.connect(lambda _value: self._follow())
            scroll.verticalScrollBar().rangeChanged.connect(lambda _low, _high: self._follow())
            self._hours[key] = scroll
            self._heads[key] = head

    def _front_clicked(self, head: Head) -> None:
        if head.property("opens"):
            self.opened.emit(head.day)

    def front_track(self, area: QRectF) -> list[LinearTrack]:
        return [LinearTrack(self._front, area.adjusted(0, END_ROOM / 2, 0, -END_ROOM / 2))]

    def peek_track(self, day: int, area: QRectF) -> list[LinearTrack]:
        """A neighbour's hours are the stretch the card in front shows, on the drag's step."""
        first, last = self._window
        return [LinearTrack(day, area.adjusted(0, 1, 0, -1), Axis.DOWN, first, last)]

    def _retarget(self) -> None:
        """Every card's words and blocks for the day now in front."""
        scene = self.scene
        if scene is None:
            return
        week, today = scene.week, scene.today
        for day, card in self._cards.items():
            card.head.set_day(day, week.date_of(day).day, day == today, "", True)
            card.hours.set_week(week.on_day(day), today, scene.minute)
            card.hours.setAccessibleName(f"{DAY_FULL[day]}'s hours, beside the day in front")
        scroll = self.hours
        assert scroll is not None
        front = self._front
        count = len(week.on_day(front))
        things = plural(count, "thing") if count else "Nothing planned"
        note = f"Today · {things}" if front == today else things
        number = week.date_of(front).day
        self._heads["day" if self._open else "week"].set_day(
            front, number, front == today, note, not self._open, dated=not self._open
        )
        self._date.setText(str(number))
        self._chip.setText(str(number))
        self._date.setVisible(self._open and front != today)
        self._chip.setVisible(self._open and front == today)
        scroll.canvas.relayout()
        scroll.canvas.set_week(week.on_day(front), today, scene.minute)
        scroll.canvas.setAccessibleName(f"{DAY_FULL[front]}, hour by hour")
        self._arrows()

    # Moving the row

    def turn(self, step: int) -> None:
        """The arrows and the wheel: Week slides a day; Day asks the window for the day, which slides
        when it is shown."""
        target = self._front + step
        if self._open:
            self.turned.emit(target)
        elif 0 <= target <= 6:
            self._go(target, "slide")

    def _go(self, day: int, how: str, force: bool = False) -> None:
        """Bring `day` to the front: sliding the row, fading to it under Reduce motion, or at once.
        `force` shows what the cards hold again when `day` is in front already."""
        if day == self._front:
            if force:
                self._retarget()
                if self._slide.state() != QAbstractAnimation.State.Running:
                    self._put(self._targets())
            return
        level = app_level()
        moving = how == "slide" and duration(SLIDE_MS, level) > 0 and self.isVisible() and bool(self._rects)
        moving = moving and not self.hand.busy
        slides = moving and moves(level)
        # Under Reduce motion the row changes where it is, under a picture of it that fades.
        picture = hold_picture(self, level) if moving and not slides else None
        before = dict(self._rects)
        self._slide.stop()
        self._front = day
        self._retarget()
        after = self._targets()
        if slides:
            self._from, self._to = before, after
            self._put(before)
            self._slide.setDuration(duration(SLIDE_MS, level))
            self._slide.start()
            return
        self._put(after)
        fade_away(picture, level, ms=SLIDE_MS)

    def _slid(self, value: object) -> None:
        share = float(value)
        self._put({day: between(self._from.get(day, rect), rect, share) for day, rect in self._to.items()})

    def _targets(self) -> dict[int, QRectF]:
        return slots(self.width(), self.height(), self._front, self.scale, wide=self._open)

    def _put(self, rects: dict[int, QRectF]) -> None:
        """Every card where `rects` puts it: the one in front as its hours, and Day's summary in it."""
        if not rects or not self._cards:
            return
        self._rects = dict(rects)
        scale = self.scale
        for day, card in self._cards.items():
            shown = day != self._front and self._peeks
            if shown:
                card.setGeometry(rects[day].toRect())
            card.setVisible(shown)
        front = rects[self._front]
        side, right, foot = (size * scale for size in FRONT_PAD)
        beside = (SUMMARY + SUMMARY_GAP) * scale if self._open and self._summary is not None else 0
        scroll = self.hours
        if scroll is not None:
            scroll.setGeometry(front.adjusted(side, 0, -right - beside, -foot).toRect())
        for stamp in (self._date, self._chip):
            stamp.adjustSize()
            stamp.move(
                round(front.right() - right - stamp.width()),
                round(front.top() + (FRONT_HEAD * scale - stamp.height()) / 2),
            )
        if self._summary is not None:
            top = front.top() + FRONT_HEAD * scale
            wide = SUMMARY * scale
            box = QRectF(front.right() - right - wide, top, wide, front.bottom() - foot - top)
            self._summary.setGeometry(box.toRect())
        self._fade.setGeometry(self.rect())
        self._place_arrows()
        self.update()

    def _place_arrows(self) -> None:
        """The arrows in the gaps either side of the card in front, halfway down; and the fade at the
        row's ends, over the room outside the cards in view, where the days further off slide in."""
        targets = self._targets()
        front = targets.get(self._front)
        if front is None:
            return
        gap, side = GAP * self.scale, self.back.width()
        middle = round(front.center().y() - side / 2)
        self.back.move(round(front.left() - gap / 2 - side / 2), middle)
        self.ahead.move(round(front.right() + gap / 2 - side / 2), middle)
        width = self.width()
        seen = [
            min(rect.left(), width - rect.right())
            for day, rect in targets.items()
            if day != self._front and self._peeks and rect.left() >= 0 and rect.right() <= width
        ]
        reach = min(seen) if seen else FADE * self.scale
        self._fade.reach = min(max(reach, RESERVE * self.scale), FADE * self.scale)

    def _arrows(self) -> None:
        scene = self.scene
        if scene is None:
            return
        first = self._open or self._front > 0
        last = self._open or self._front < 6
        self.back.setEnabled(first)
        self.ahead.setEnabled(last)
        for arrow, step in ((self.back, -1), (self.ahead, 1)):
            day = scene.week.date_of(self._front + step)
            name = DAY_FULL[day.weekday()]
            arrow.setToolTip(name)
            arrow.setAccessibleName(f"Show {name}")

    def _follow(self) -> None:
        """Neighbours show the stretch of the day the card in front shows, on the drag's step, so
        a block dropped at their top or foot still lands on it."""
        scroll = self.hours
        if scroll is None or not scroll.canvas.tracks:
            return
        track = scroll.canvas.tracks[0]
        top = scroll.verticalScrollBar().value()
        middle = track.area.center().x()
        first = track.minute_at(QPointF(middle, top))
        last = track.minute_at(QPointF(middle, top + scroll.viewport().height()))
        step = self.hand.step
        window = (
            max(FIRST, math.floor(first / step) * step),
            min(LAST, max(math.ceil(last / step) * step, math.floor(first / step) * step + step)),
        )
        if window != self._window:
            self._window = window
            for card in self._cards.values():
                card.hours.relayout()
                card.hours.update()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._slide.stop()
        self._put(self._targets())

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self.tokens or not self._rects:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = RADIUS * self.scale
        order = sorted((day for day in self._rects if day != self._front and self._peeks),
                       key=lambda day: -abs(day - self._front))
        for day in order:
            rect = self._rects[day]
            if rect.right() >= -FADE and rect.left() <= self.width() + FADE:
                paint_clay(painter, rect, self.tokens, radius, lifted=False)
        paint_clay(painter, self._rects[self._front], self.tokens, radius, lifted=True)
        for arrow in (self.back, self.ahead):
            if arrow.isVisible():
                body = QRectF(arrow.geometry())
                paint_clay(painter, body, self.tokens, body.height() / 2, lifted=False)
        painter.end()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """The wheel over the row slides it a day a notch. Over the card in front it is the hours'."""
        event.accept()
        front = self._rects.get(self._front)
        running = self._slide.state() == QAbstractAnimation.State.Running
        if front is not None and front.contains(event.position()) or running:
            self._wheel = 0
            return
        delta = event.angleDelta()
        self._wheel += delta.x() if abs(delta.x()) > abs(delta.y()) else delta.y()
        if abs(self._wheel) >= 120:
            step = -1 if self._wheel > 0 else 1
            self._wheel = 0
            self.turn(step)

    # While a block is held

    def _carrying(self, active: bool) -> None:
        if active and self.isVisible():
            self._dwell_on = None
            self._dwell.start()
            return
        self._dwell.stop()
        shown = self.scene
        if not active and self._open and shown is not None and self.isVisible():
            day = next((at for at in range(7) if shown.week.date_of(at).isoformat() == shown.iso_day), None)
            if day is not None and day != self._front:
                # Carried to another day on Day: the window follows it there once it is let go.
                self.turned.emit(self._front)

    def _dwelt(self) -> None:
        """A held block resting on an arrow slides the row a day, and again after as long."""
        at = QCursor.pos()
        over = next(
            (arrow for arrow in (self.back, self.ahead)
             if arrow.isVisible() and arrow.rect().contains(arrow.mapFromGlobal(at))),
            None,
        )
        now = time.monotonic()
        if over is not self._dwell_on:
            self._dwell_on, self._dwell_since = over, now
            return
        if over is None or now - self._dwell_since < DWELL_S:
            return
        self._dwell_since = now
        target = self._front + (-1 if over is self.back else 1)
        if 0 <= target <= 6:
            self._go(target, "jump")

    # For the rig and the tests

    def surfaces(self) -> list[QWidget]:
        """The hours in front first, then every other day's, left to right: past the row's edge too,
        where `reveal` brings them to the front."""
        scroll = self.hours
        found: list[QWidget] = [scroll.canvas] if scroll is not None and scroll.isVisible() else []
        found += [card.hours for _day, card in sorted(self._cards.items()) if card.isVisible()]
        return found

    def name_point(self, day: int) -> QPoint:
        """Where a day's name is on screen. A day whose name is past the row's edge comes to the front."""
        if day != self._front and day in self._cards:
            head = self._cards[day].head
            centre = head.mapTo(self, head.rect().center())
            if head.isVisible() and self.rect().contains(centre):
                return head.mapToGlobal(head.rect().center())
            self._go(day, "jump")
        head = self._heads["day" if self._open else "week"]
        return head.mapToGlobal(head.rect().center())

    def reveal(self, day: int, first: int, last: int) -> None:
        """Bring `day` to the front, at once, and this stretch of it into view."""
        if day != self._front and 0 <= day <= 6:
            self._go(day, "jump")
        scroll = self.hours
        if scroll is None:
            return
        canvas = scroll.canvas
        HoursCanvas.reveal(canvas, day, first, last)
        page = _page_of(self)
        track = canvas.track_for(day, first) or canvas.track_for(day)
        if page is None or track is None:
            return
        for minute in (last, first):
            local = track.point_for(min(max(minute, track.first), track.last)).toPoint()
            inside = canvas.mapTo(page.widget(), local)
            page.ensureVisible(inside.x(), inside.y(), 20, 60)

    def in_view(self, canvas: HoursCanvas, day: int, minute: int) -> bool:
        if not HoursCanvas.in_view(canvas, day, minute):
            return False
        track = canvas.track_for(day, minute)
        if track is None:
            return False
        local = track.point_for(minute).toPoint()
        if not self.rect().adjusted(-2, -2, 2, 2).contains(canvas.mapTo(self, local)):
            return False
        page = _page_of(self)
        if page is None:
            return True
        return page.viewport().rect().adjusted(-2, -2, 2, 2).contains(canvas.mapTo(page.viewport(), local))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, round(340 * self.scale))

    def sizeHint(self) -> QSize:  # noqa: N802
        # The dish's chips wrap, so the page is laid out at its preferred height: the row asks for its
        # least and takes what is left.
        return self.minimumSizeHint()


def _page_of(widget: QWidget | None) -> QScrollArea | None:
    """The page's scroll area holding the row."""
    found = widget.parentWidget() if widget is not None else None
    while found is not None and not isinstance(found, QScrollArea):
        found = found.parentWidget()
    return found


class Dish(QFrame):
    """A pressed-in tray: a shade inside its top edge and a highlight along its foot."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("clayDish")
        self.tokens: dict[str, str] = {}
        self.radius = float(RADIUS)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self.tokens:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        dark = family(self.tokens) == "dark"
        page, text, surface = self.tokens["bg"], self.tokens["text"], self.tokens["surface"]
        shape = QPainterPath()
        shape.addRoundedRect(body, self.radius, self.radius)
        tray = mix_oklab(page, surface, 0.55) if dark else mix_oklab(text, page, 0.04)
        painter.fillPath(shape, QColor(tray))
        painter.setClipPath(shape)
        shade = QLinearGradient(QPointF(0, body.top()), QPointF(0, body.top() + 8))
        low = QColor("#000000" if dark else text)
        low.setAlphaF(0.35 if dark else 0.09)
        shade.setColorAt(0, low)
        low.setAlphaF(0.0)
        shade.setColorAt(1, low)
        painter.fillRect(QRectF(body.left(), body.top(), body.width(), 8), shade)
        painter.fillRect(QRectF(body.left(), body.bottom() - 1, body.width(), 1), QColor(surface))
        painter.setClipping(False)
        if dark:
            ring = QColor(self.tokens["line"])
            ring.setAlphaF(0.7)
            painter.setPen(QPen(ring, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(body, self.radius, self.radius)
        painter.end()


class ClayChip(TrayChip):
    """Homework not placed yet as a clay chip: the book in its category's colour, its name, how long
    it takes, and a grip. Drag it onto a day to give it a time; a click opens it."""

    def __init__(self, hand: Hand, waiting: Waiting, tokens: dict[str, str], scale: float) -> None:
        super().__init__(hand, waiting)
        self.tokens, self.scale = tokens, scale
        self.length = length_label(waiting.minutes)
        self.fill, self.mark = _paint(tokens, waiting.category or "assignments")

    def _fit(self) -> None:
        # Painted whole each time: the title shortens in the paint.
        return

    def _fonts(self) -> tuple[QFont, QFont]:
        # Both weights named: the window's stylesheet sets a button's font at 600.
        return (
            at_scale(self.font(), "body", self.scale, WEIGHT_STRONG),
            at_scale(self.font(), "body", self.scale, WEIGHT_REGULAR),
        )

    def _measures(self) -> tuple[float, float, float, float]:
        """Its height, the book's circle, the grip, and the room between parts."""
        return 40 * self.scale, 28 * self.scale, 16 * self.scale, 8 * self.scale

    def sizeHint(self) -> QSize:  # noqa: N802
        title, small = self._fonts()
        tall, circle, grip, gap = self._measures()
        wide = 6 * self.scale + circle + gap + QFontMetricsF(title).horizontalAdvance(self._title) + gap
        wide += QFontMetricsF(small).horizontalAdvance(self.length) + gap + grip + gap
        return QSize(math.ceil(wide) + 2, math.ceil(tall) + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        hint = self.sizeHint()
        return QSize(min(hint.width(), round(160 * self.scale)), hint.height())

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tall, circle, grip, gap = self._measures()
        body = QRectF(1, 1, self.width() - 2, tall)
        dark = family(self.tokens) == "dark"
        shadow = QColor("#000000" if dark else self.tokens["text"])
        _soft(painter, body, tall / 2, 2, 4, -1, shadow, 0.4 if dark else 0.14)
        paint_clay(painter, body, self.tokens, tall / 2, lifted=False, shadow=False)
        if self.hasFocus() and self.property("keyfocus"):
            painter.setPen(QPen(QColor(self.tokens["accent"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(body.adjusted(1, 1, -1, -1), tall / 2 - 1, tall / 2 - 1)
        ring = QRectF(body.left() + 6 * self.scale, body.center().y() - circle / 2, circle, circle)
        painter.setPen(QPen(QColor(self.mark), 1.5))
        painter.setBrush(QColor(self.fill))
        painter.drawEllipse(ring.adjusted(0.75, 0.75, -0.75, -0.75))
        side = round(14 * self.scale)
        ratio = self.devicePixelRatioF()
        painter.drawPixmap(QPointF(ring.center().x() - side / 2, ring.center().y() - side / 2),
                           icons.pixmap(BOOK, self.tokens["text"], side, ratio))
        title, small = self._fonts()
        tm, sm = QFontMetricsF(title), QFontMetricsF(small)
        end = body.right() - gap - grip
        room = end - gap - (ring.right() + gap) - sm.horizontalAdvance(self.length) - gap
        name = tm.elidedText(self._title, Qt.TextElideMode.ElideRight, max(room, 0))
        left = ring.right() + gap
        line = QRectF(left, body.center().y() - tm.height() / 2, tm.horizontalAdvance(name) + 1, tm.height())
        painter.setFont(title)
        painter.setPen(QColor(self.tokens["text"]))
        painter.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        painter.setFont(small)
        painter.setPen(QColor(self.tokens["muted"]))
        after = QRectF(line.right() + gap - 1, line.top(), sm.horizontalAdvance(self.length) + 1, tm.height())
        painter.drawText(after, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.length)
        painter.drawPixmap(QPointF(end, body.center().y() - grip / 2),
                           icons.pixmap("grip-vertical", self.tokens["muted"], round(grip), ratio))
        painter.end()


class Bar(QWidget):
    """A day's hours by kind as one thin bar, each kind in its mark, free time last."""

    def __init__(self, parts: list[tuple[str, int]], scale: float) -> None:
        super().__init__()
        self.parts = parts
        self.setFixedHeight(round(8 * scale))

    def paintEvent(self, event: object) -> None:  # noqa: N802
        total = sum(minutes for _colour, minutes in self.parts)
        if total <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect())
        shape = QPainterPath()
        shape.addRoundedRect(body, body.height() / 2, body.height() / 2)
        painter.setClipPath(shape)
        room = body.width() - 2 * (len(self.parts) - 1)
        at = body.left()
        for colour, minutes in self.parts:
            wide = room * minutes / total
            painter.fillRect(QRectF(at, body.top(), wide, body.height()), QColor(colour))
            at += wide + 2
        painter.end()


class Dot(QWidget):
    """A category's dot, or free time's hollow ring."""

    def __init__(self, colour: str, hollow: bool, scale: float) -> None:
        super().__init__()
        self.colour, self.hollow = colour, hollow
        self.setFixedSize(round(10 * scale), round(10 * scale))

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        if self.hollow:
            painter.setPen(QPen(QColor(self.colour), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.colour))
        painter.drawEllipse(body)
        painter.end()


class ClayDeckView(LayoutView):
    layout_id = "clay"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        # A view's minimum height must not become the window's: inside a scroll area, what does not fit
        # scrolls and the window keeps its size.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._page = QWidget()
        self._page.setObjectName("clayPage")
        self._root = QVBoxLayout(self._page)
        outer.addWidget(scrolling(self._page, "clayScroll"))
        self.row = Row(self.hand, self.keep_zoom)
        self.row.opened.connect(self._open_day)
        self.row.turned.connect(self._open_day)
        self._root.setSpacing(0)
        self._root.addWidget(self.row, 1)
        self._dish = Dish()
        self._tray = QHBoxLayout(self._dish)
        # The row runs to the window's edges, where its ends fade; the dish keeps the page's margins.
        self._foot = QHBoxLayout()
        self._foot.addWidget(self._dish)
        self._root.addLayout(self._foot)

    def shown_day(self, scene: Scene) -> int:
        if scene.surface == "day" and scene.iso_day:
            for day in range(7):
                if scene.week.date_of(day).isoformat() == scene.iso_day:
                    return day
        return scene.today if scene.today is not None else 0

    def hours_surfaces(self) -> list[QWidget]:
        """The hours in front first: the one the zoom is on and the rig reads first."""
        return [widget for widget in self.row.surfaces() if widget.isVisible()]

    def render(self, scene: Scene, week_changed: bool) -> None:
        px = scene.px
        self.setStyleSheet(self._sheet(scene))
        self._root.setContentsMargins(0, px(AROUND[1]), 0, px(AROUND[1]))
        self._foot.setContentsMargins(px(AROUND[0]), 0, px(AROUND[0]), 0)
        is_day = scene.surface == "day"
        day = self.shown_day(scene) if is_day else None
        self.row.show_scene(scene, day, scene.options.get("peek") != "hide")
        self.row.set_summary(self._summary(scene, day) if day is not None else None)
        self._fill_dish(scene)

    def _open_day(self, day: int) -> None:
        if self._scene is not None:
            self.day_activated.emit(self._scene.week.date_of(day).isoformat())

    # The dish

    def _fill_dish(self, scene: Scene) -> None:
        px = scene.px
        self._dish.tokens = scene.tokens
        self._dish.radius = RADIUS * scene.scale
        self._dish.setMinimumHeight(px(DISH))
        empty(self._tray)
        self._tray.setContentsMargins(px(24), px(10), px(24), px(10))
        self._tray.setSpacing(px(24))
        head = QVBoxLayout()
        head.setSpacing(px(2))
        head.addWidget(label("Not placed yet", "clayTrayLabel"))
        waiting = scene.week.waiting
        due = _due_words(waiting)
        if due:
            head.addWidget(label(due, "clayDue"))
        self._tray.addLayout(head)
        if not waiting:
            self._tray.addWidget(label("Nothing is waiting for a time.", "clayEmpty"), 1)
            self.update()
            return
        chips = FlowLayout(gap=px(12))
        chips.setContentsMargins(0, 0, 0, 0)
        for index, item in enumerate(waiting):
            chip = ClayChip(self.hand, item, scene.tokens, scene.scale)
            chip.setObjectName(f"clayWaiting{index}")
            chip.clicked.connect(lambda _=False, block_id=item.block_id: self.block_activated.emit(block_id))
            chips.addWidget(chip)
        holder = QFrame()
        holder.setObjectName("clayChips")
        holder.setLayout(chips)
        self._tray.addWidget(holder, 1)
        self._tray.addWidget(label("Drag a chip onto a day.", "clayHint"), 0, Qt.AlignmentFlag.AlignVCenter)

    # Day's summary

    def _summary(self, scene: Scene, day: int) -> QFrame:
        """The day's hours by kind from 08:00 to 22:00 with its free time, as a bar and a row each;
        and today, what is left of it."""
        px, tokens, week = scene.px, scene.tokens, scene.week
        frame = QFrame()
        frame.setObjectName("claySummary")
        box = QVBoxLayout(frame)
        box.setContentsMargins(px(24), 0, 0, 0)
        box.setSpacing(px(12))
        title = f"{DAY_FULL[day]}, {clock_label(DAY_FROM)} to {clock_label(DAY_TO)}"
        box.addWidget(label(title, "claySumTitle"))
        kinds = day_kinds(week, day)
        free = DAY_TO - DAY_FROM - _covered(week.on_day(day), DAY_FROM, DAY_TO)
        free_bar = mix_oklab(tokens["text"], tokens["surface"], 0.14)
        parts = [(_paint(tokens, kind)[1], minutes) for kind, minutes in kinds]
        box.addWidget(Bar([*parts, (free_bar, free)], scene.scale))
        rows = QVBoxLayout()
        rows.setSpacing(0)
        for at, (kind, minutes) in enumerate(kinds):
            name = (CATEGORIES.get(kind) or {}).get("label") or "Other"
            dot = Dot(_paint(tokens, kind)[1], False, scene.scale)
            book = kind in HOMEWORK_CATEGORIES
            rows.addWidget(self._row(scene, dot, name, length_label(minutes), at == 0, book))
        rows.addWidget(self._row(scene, Dot(tokens["line"], True, scene.scale), "Free", length_label(free),
                                 not kinds))
        box.addLayout(rows)
        if day == scene.today and scene.minute < DAY_TO:
            planned, open_min, coming = left_today(week, day, scene.minute)
            box.addSpacing(px(12))
            box.addWidget(label("Left today", "clayLeftTitle"))
            left = QVBoxLayout()
            left.setSpacing(0)
            lines = [("clock", "Planned", length_label(planned)),
                     ("sun", f"Free until {clock_label(DAY_TO)}", length_label(open_min))]
            if coming is not None:
                lines.append(("skip-forward", f"Next at {clock_label(coming.start)}",
                              f"in {length_label(coming.start - scene.minute)}"))
            for at, (icon, words, value) in enumerate(lines):
                mark = QLabel()
                mark.setObjectName("clayLeftIcon")
                mark.setPixmap(icons.pixmap(icon, tokens["muted"], px(14), self.devicePixelRatioF()))
                left.addWidget(self._row(scene, mark, words, value, at == 0))
            box.addLayout(left)
        box.addStretch(1)
        return frame

    def _row(
        self, scene: Scene, mark: QWidget, words: str, value: str, first: bool, book: bool = False
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("claySumRow")
        row.setProperty("first", first)
        row.setFixedHeight(scene.px(30))
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(scene.px(8))
        line.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        line.addWidget(label(words, "claySumName"), 0, Qt.AlignmentFlag.AlignVCenter)
        if book:
            icon = QLabel()
            icon.setObjectName("claySumBook")
            icon.setPixmap(icons.pixmap(BOOK, scene.tokens["muted"], scene.px(12), self.devicePixelRatioF()))
            line.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        line.addStretch(1)
        line.addWidget(label(value, "claySumLength"), 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _sheet(self, scene: Scene) -> str:
        tokens = scene.tokens
        text, muted, accent, surface = tokens["text"], tokens["muted"], tokens["accent"], tokens["surface"]

        def size(role: str) -> str:
            return f"{type_pt(role, scene.scale)}pt"

        chip = round(24 * scene.scale)
        clear = css(background="transparent")
        caption_words = css(color=muted, font_size=size("caption"))
        return base_sheet(self.objectName(), tokens) + rules(
            self.objectName(),
            {
                "#clayScroll, #clayPage": css(background=tokens["bg"]),
                # Plain widgets on the cards, which the window's stylesheet would paint its page colour.
                "#clayWeekHeader, #clayDayHeader, #clayWeekZoom, #clayDayZoom, #clayChips": clear,
                "#qt_scrollarea_vcontainer, #qt_scrollarea_hcontainer": clear,
                "QLabel": css(color=text, font_size=size("body")),
                # A stylesheet's height beats setFixedHeight, so a name row's is set here.
                'QPushButton[kind="head"]': css(
                    background="transparent",
                    border="none",
                    border_radius=f"{RADIUS_CONTROL}px",
                    padding="0",
                    min_height=f"{scene.px(PEEK_HEAD)}px",
                    max_height=f"{scene.px(PEEK_HEAD)}px",
                ),
                'QPushButton[kind="head"][front="true"]': css(
                    min_height=f"{scene.px(FRONT_HEAD)}px", max_height=f"{scene.px(FRONT_HEAD)}px"
                ),
                'QPushButton[kind="head"][opens="true"]:hover': css(
                    background=mix_oklab(text, surface, 0.05)
                ),
                'QPushButton[kind="head"][keyfocus="true"]:focus': css(border=f"2px solid {accent}"),
                "QLabel#clayDayName": css(font_size=size("heading"), font_weight=WEIGHT_STRONG),
                'QLabel#clayDayName[front="true"]': css(font_size=size("title")),
                "QLabel#clayNote, QLabel#clayDate": css(color=muted),
                "QLabel#clayToday": css(
                    background=accent,
                    color=tokens["accent_ink"],
                    font_weight=WEIGHT_STRONG,
                    border_radius=f"{chip // 2}px",
                    padding=f"0 {round(8 * scene.scale)}px",
                    min_height=f"{chip}px",
                    max_height=f"{chip}px",
                ),
                "QLabel#clayTrayLabel, QLabel#claySumTitle, QLabel#clayLeftTitle": css(
                    font_weight=WEIGHT_STRONG
                ),
                "QLabel#clayDue, QLabel#clayHint, QLabel#clayEmpty": caption_words,
                "QLabel#claySumLength": css(color=muted),
                "QFrame#claySummary": css(border_left=f"1px solid {tokens['line']}"),
                'QFrame#claySumRow[first="false"]': css(border_top=f"1px solid {tokens['line']}"),
            },
        )


def _due_words(waiting: Iterable[Waiting]) -> str:
    """When what is not placed yet is due, as the dish says it: "Due Sun 27", or the soonest first."""
    dues = sorted({item.due[:10] for item in waiting if item.due})
    if not dues:
        return ""
    soonest = date.fromisoformat(dues[0])
    words = f"{DAYS[soonest.weekday()]} {soonest.day}"
    return f"Due {words}" if len(dues) == 1 else f"First due {words}"
