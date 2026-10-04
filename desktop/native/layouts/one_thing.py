"""One thing: a day screen. The whole window is the thing that is on now, or next if nothing is,
counted down on a ring.

It deliberately cannot plan. Its value is that it shows less, so the only way out is back to planning.
It can move the day's own blocks, though, through the window's hand: drag one along the day bar, or
drag the thing itself onto it, to put it later, as Running late does.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QKeyEvent, QMouseEvent, QPainter, QPen, QResizeEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from desktop.native.fonts import at_scale
from desktop.native.hours.canvas import BlockPainter, Drawn, HoursCanvas
from desktop.native.hours.geometry import Axis, LinearTrack, Span
from desktop.native.hours.hand import Gesture, Hand, Held
from desktop.native.icons import pixmap
from desktop.native.layouts.base import (
    LayoutView,
    Scene,
    base_sheet,
    css,
    day_buttons,
    empty,
    family,
    label,
    plural,
    rules,
)
from desktop.native.look import category_paint
from desktop.native.motion import app_level
from desktop.native.ring import CountdownRing, ring_colours
from desktop.native.tokens import RADIUS_CARD, SPACING, WEIGHT_STRONG, type_pt
from desktop.native.weekmodel import Occurrence, Waiting, clock_label, length_label, range_label
from desktop.native.widgets import FittedLabel

DAY_START, DAY_END = 6 * 60, 22 * 60
BAR_TALL = 22
# The ring's side in the mock-up at Normal text. Then's rows give way before it goes under RING_ROOMY.
RING_MAX, RING_ROOMY, RING_MIN = 440, 320, 200
THEN_ROWS = 4
# The most of the ring's inside the title may take, so the number stays the thing that is read.
TITLE_SHARE = 0.4


def _small(font: QFont) -> QFont:
    """The words on the carried block's pill, a little under the bar's own font."""
    made = QFont(font)
    made.setPointSizeF(max(made.pointSizeF() * 0.86, 7))
    return made


class BarPainter(BlockPainter):
    """The day as one thin bar: every block a segment, the thing on screen in the accent, now as a
    tick. A carried block is drawn where it would land, outlined, with its words on a pill above."""

    def __init__(self, tokens: dict[str, str], chosen: str | None) -> None:
        super().__init__(
            {
                "track": tokens["line"],
                "other": tokens["bg_muted"],
                "accent": tokens["accent"],
                "accent_ink": tokens["accent_ink"],
                "error": tokens["danger"],
                "tick": tokens["bg_ink"],
                "block_edge": tokens["block_edge"],
            }
        )
        self.chosen = chosen
        self._middle = 0.0

    def background(self, painter: QPainter, rect: QRectF) -> None:
        pass

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        area = track.area
        self._middle = area.center().y()
        painter.fillRect(QRectF(area.left(), self._middle - 5, area.width(), 10), self.c("track"))

    def hour_labels(
        self,
        painter: QPainter,
        track: LinearTrack,
        room: float,
        every: int = 60,
        visible: QRectF | None = None,
    ) -> None:
        pass

    def block(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> None:
        tall = min(10.0, rect.height())
        # On the bar, or in its share of the bar's height where blocks overlap.
        middle = self._middle if drawn.columns == 1 else rect.center().y()
        segment = QRectF(rect.left(), middle - tall / 2, max(rect.width(), 2), tall)
        if drawn.held:
            ok = drawn.verdict is None or drawn.verdict.ok
            colour = self.c("accent" if ok else "error")
            painter.fillRect(segment, colour)
            painter.setPen(QPen(colour, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(segment.left(), segment.top() - 4, max(segment.width(), 4), tall + 8))
        else:
            painter.fillRect(segment, self.c("accent" if drawn.block_id == self.chosen else "other"))
        # A segment has no words: the tick for now goes over its colour, or the thing on now hid it.
        self.crossing(painter, rect)

    def hint(self, painter: QPainter, rect: QRectF, big: bool) -> None:
        pass

    def now(self, painter: QPainter, track: LinearTrack, minute: int) -> None:
        area = track.area
        painter.fillRect(
            QRectF(area.left() + track.offset(minute) - 1.5, area.top(), 3, area.height()), self.c("tick")
        )

    def label(self, painter: QPainter, beside: QRectF, words: str, ok: bool, room: QRectF) -> None:
        """Above the carried segment, in the room left over the bar for it."""
        plain = _small(painter.font())
        metrics = QFontMetrics(plain)
        width, height = metrics.horizontalAdvance(words) + 20, metrics.height() + 10
        left = min(max(beside.center().x() - width / 2, room.left()), room.right() - width)
        pill = QRectF(left, max(beside.top() - 8 - height, room.top()), width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.c("accent" if ok else "error"))
        painter.drawRoundedRect(pill, height / 2, height / 2)
        painter.setPen(self.c("accent_ink"))
        painter.setFont(plain)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, words)


class DayBar(HoursCanvas):
    """Today from 06:00 to 22:00 as one track across. A segment can be carried along it to a new
    time, and a tap on one opens it. Free time makes nothing: this screen does not plan."""

    block_clicked = Signal(str)

    def __init__(self, hand: Hand, day: int, tokens: dict[str, str], chosen: str | None) -> None:
        super().__init__(
            hand,
            BarPainter(tokens, chosen),
            lambda area: [LinearTrack(day, area, Axis.ACROSS, DAY_START, DAY_END)],
        )
        self.setObjectName("oneDayBar")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(f"Today from {clock_label(DAY_START)} to {clock_label(DAY_END)}")
        self.setAccessibleDescription("Drag a block along the bar to move it, or click it to open it.")
        # Room over the bar for the carried block's words.
        self.header = QFontMetrics(_small(self.font())).height() + 18
        self.setFixedHeight(round(self.header) + BAR_TALL)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hit = self._block_at(event.position())
        if hit is None:
            return
        drawn, _rect, track = hit
        span = drawn.span
        held = Held(
            Gesture.MOVE,
            drawn.title,
            span.minutes,
            drawn.block_id,
            span.day,
            span,
            round(track.minute_at(event.position()) - span.start),
        )
        self.hand.press(
            self,
            held,
            event.globalPosition().toPoint(),
            tap=lambda: self.block_clicked.emit(drawn.block_id),
            home=(self, track),
        )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # The first click of the two has opened it already.
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.hand.busy:
            over = self._block_at(event.position()) is not None
            self.setCursor(Qt.CursorShape.OpenHandCursor if over else Qt.CursorShape.ArrowCursor)


class Thing(QLabel):
    """The thing itself, as large as the window allows. Like a tray chip, it can be picked up and
    let go on the day bar: a block with a time moves there, homework with none is given that time."""

    def __init__(self, hand: Hand) -> None:
        super().__init__("")
        self.hand = hand
        self.held: Held | None = None
        self.setObjectName("oneTitle")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)

    def carry(self, thing: Occurrence | Waiting | None) -> None:
        if isinstance(thing, Occurrence):
            span = Span(thing.day, thing.start, thing.end)
            self.held = Held(Gesture.MOVE, thing.title, thing.minutes, thing.block_id, thing.day, span)
        elif isinstance(thing, Waiting):
            self.held = Held(Gesture.PLACE, thing.title, thing.minutes, thing.block_id)
        else:
            self.held = None
        self.setProperty("block_id", self.held.block_id if self.held is not None else None)
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.held is not None else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.held is not None:
            self.hand.press(self, self.held, event.globalPosition().toPoint())
            return
        super().mousePressEvent(event)


def countdown(minutes: int) -> tuple[str, str]:
    """The ring's number and its unit: 20 min, and from an hour 3 h or 3:20 h."""
    if minutes < 60:
        return str(max(minutes, 0)), "min"
    hours, rest = divmod(minutes, 60)
    return (f"{hours}:{rest:02d}" if rest else str(hours)), "h"


def shortened(words: str, metrics: QFontMetrics, width: int, lines: int) -> str:
    """`words` in one line, or two, the last shortened with an ellipsis: the first of two is whole
    words."""
    first, rest = "", words.split()
    while lines > 1 and rest and metrics.horizontalAdvance(f"{first} {rest[0]}".strip()) <= width:
        first = f"{first} {rest.pop(0)}".strip()
    if not first:
        return metrics.elidedText(words, Qt.TextElideMode.ElideRight, width)
    if not rest:
        return first
    return f"{first}\n{metrics.elidedText(' '.join(rest), Qt.TextElideMode.ElideRight, width)}"


class OneThingView(LayoutView):
    """The thing as a countdown (0.17's Countdown): the ring is the hour ahead, like a kitchen timer,
    its arc the minutes to go, and what comes after is listed under it."""

    layout_id = "one"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        self._skip = 0
        self._title = Thing(self.hand)
        self._title_words = ""
        self._ring: CountdownRing | None = None
        self._then: QWidget | None = None
        self._rows: list[QWidget] = []
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(SPACING[5] * 2, SPACING[4], SPACING[5] * 2, SPACING[5])
        self._root.setSpacing(0)

    def _queue(self, scene: Scene) -> tuple[tuple[Occurrence, ...], Occurrence | None]:
        if scene.today is None:
            return (), None
        found = scene.week.day_queue(scene.today, scene.minute)
        if scene.options.get("lead") == "next" and found.current is not None:
            return found.queue[1:], None
        return found.queue, found.current

    def render(self, scene: Scene, week_changed: bool) -> None:
        if week_changed:
            self._skip = 0
        queue, current = self._queue(scene)
        self._skip = min(self._skip, max(len(queue) - 1, 0))
        item = queue[self._skip] if queue else None
        is_now = item is not None and item == current
        self.setStyleSheet(self._sheet(scene))
        # The ring is made again below: the new one carries on from what this one draws.
        drawn = self._ring.left() if self._ring is not None else None
        empty(self._root)
        top = QHBoxLayout()
        top.addWidget(label(f"Now {clock_label(scene.minute)}", "oneDate"))
        top.addStretch()
        top.addWidget(label(self._left_text(scene), "oneLeft"))
        self._root.addLayout(top)
        self._root.addStretch(1)
        self._ring = self._dial(scene, item, is_now, current is not None, drawn)
        self._root.addWidget(self._ring, 0, Qt.AlignmentFlag.AlignHCenter)
        self._root.addSpacing(scene.px(SPACING[4]))
        self._then = self._then_list(scene, queue[self._skip + 1 : self._skip + 1 + THEN_ROWS])
        self._root.addWidget(self._then, 0, Qt.AlignmentFlag.AlignHCenter)
        self._root.addSpacing(scene.px(SPACING[4]))
        self._root.addLayout(self._actions(scene, item))
        self._root.addStretch(1)
        if scene.options.get("daybar") != "hide" and scene.today is not None:
            bar = DayBar(self.hand, scene.today, scene.tokens, item.block_id if item is not None else None)
            bar.set_week(scene.week.on_day(scene.today), scene.today, scene.minute)
            bar.block_clicked.connect(self.block_activated.emit)
            self._root.addWidget(bar)
        self._fit()

    def _sheet(self, scene: Scene) -> str:
        tokens = scene.tokens

        def size(role: str) -> str:
            return f"{type_pt(role, scene.scale)}pt"

        ink, muted, strong = tokens["bg_ink"], tokens["bg_muted"], WEIGHT_STRONG
        quiet = f"2px solid {tokens['line']}"
        return base_sheet(self.objectName(), tokens) + rules(
            self.objectName(),
            {
                "#oneDate, #oneLeft, #oneLine, #oneRowTime, #oneRowLength": css(
                    color=muted, font_size=size("body")
                ),
                "#oneLabel": css(color=muted, font_size=size("heading"), font_weight=strong),
                "#oneTitle": css(color=ink, font_size=size("title"), font_weight=strong),
                "#oneThenLabel": css(color=muted, font_size=size("body"), font_weight=strong),
                "#oneRowName": css(color=ink, font_size=size("body"), font_weight=strong),
                "#oneRule": css(background=tokens["line"]),
                "#oneRow": css(border_bottom=f"1px solid {tokens['line']}"),
                "QPushButton": css(
                    background="transparent",
                    color=ink,
                    border=quiet,
                    border_radius=f"{RADIUS_CARD}px",
                    padding=f"0 {scene.px(SPACING[4])}px 0 {scene.px(SPACING[3])}px",
                    min_height=f"{scene.px(40)}px",
                    font_size=size("body"),
                    font_weight=strong,
                ),
                "QPushButton:hover": css(background=tokens["surface"]),
                'QPushButton[kind="main"]': css(
                    background=tokens["accent"], color=tokens["accent_ink"], border_color=tokens["accent"]
                ),
                # Rung only when reached with the keyboard, as every button in the app is.
                'QPushButton[keyfocus="true"]:focus': css(border_color=tokens["accent"]),
                'QPushButton[kind="main"][keyfocus="true"]:focus': css(border_color=ink),
            },
        )

    def _dial(
        self, scene: Scene, item: Occurrence | None, is_now: bool, has_current: bool, drawn: float | None
    ) -> CountdownRing:
        tokens = scene.tokens
        ring = CountdownRing()
        ring.set_colours(
            ring_colours(
                {
                    "family": family(tokens),
                    "text": tokens["bg_ink"],
                    "window": tokens["bg"],
                    "accent": tokens["accent"],
                    "muted": tokens["bg_muted"],
                }
            )
        )
        ring.set_text_scale(scene.scale)
        ring.set_scale(12, ("0", "15", "30", "45"))
        heading, line = self._words(scene, item, is_now, has_current)
        self._title = Thing(self.hand)
        self._title_words = item.title if item else self._empty_title(scene)
        self._title.setText(self._title_words)
        if item is not None:
            self._title.setAccessibleDescription("Press Enter to open it")
        # The thing itself can be carried onto the day bar, to a later time.
        needs_time = scene.today is not None and scene.week.leftover_kind(scene.today) == "needs_time"
        self._title.carry(item or (scene.week.due_today_unplaced(scene.today)[0] if needs_time else None))
        kicker = label(heading, "oneLabel")
        kicker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if heading == self._title_words:
            kicker.hide()
        ring.above.addWidget(kicker)
        ring.above.addWidget(self._title)
        when = label(line, "oneLine", wrap=True)
        when.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ring.below.addWidget(when)
        to_go = 0 if item is None else (item.end if is_now else item.start) - scene.minute
        share = min(to_go, 60) / 60
        ring.run_down(share if drawn is None else drawn, share, app_level())
        if item is not None:
            ring.set_number(*countdown(to_go))
            ring.setAccessibleName(f"{length_label(to_go)} {'left' if is_now else 'until it starts'}")
        return ring

    def _then_list(self, scene: Scene, then: tuple[Occurrence, ...]) -> QWidget:
        """What comes after, a row each: its time, its category's dot, its name and its length."""
        box = QWidget()
        box.setObjectName("oneThen")
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(label("Then", "oneThenLabel"))
        column.addSpacing(scene.px(SPACING[1]))
        rule = QFrame()
        rule.setObjectName("oneRule")
        rule.setFixedHeight(1)
        column.addWidget(rule)
        tokens = scene.tokens
        paint = {"family": family(tokens), "panel": tokens["surface"]}
        times = QFontMetrics(at_scale(self.font(), "body", scene.scale))
        time_width = max((times.horizontalAdvance(clock_label(entry.start)) for entry in then), default=0)
        self._rows = []
        for entry in then:
            row = QFrame()
            row.setObjectName("oneRow")
            row.setMinimumHeight(scene.px(36))
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(scene.px(SPACING[2]))
            when = label(clock_label(entry.start), "oneRowTime")
            when.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            when.setFixedWidth(time_width + 2)
            line.addWidget(when)
            dot = QFrame()
            dot.setFixedSize(10, 10)
            mark = category_paint(entry.category, paint)[1] or tokens["bg_muted"]
            dot.setStyleSheet(f"background: {mark}; border-radius: 5px;")
            line.addWidget(dot)
            if entry.work:
                book = QLabel()
                book.setPixmap(pixmap("book-open", tokens["bg_muted"], 14, self.devicePixelRatioF()))
                line.addWidget(book)
            name = FittedLabel(minimum=40)
            name.setObjectName("oneRowName")
            name.set_full_text(entry.title)
            line.addWidget(name, 1)
            line.addWidget(label(length_label(entry.minutes), "oneRowLength"))
            column.addWidget(row)
            self._rows.append(row)
        return box

    def _left_text(self, scene: Scene) -> str:
        if scene.today is None:
            return "Another week"
        left = sum(1 for item in scene.week.on_day(scene.today) if item.live and item.end > scene.minute)
        return f"{plural(left, 'thing')} left today" if left else "Nothing left today"

    def _empty_title(self, scene: Scene) -> str:
        if scene.today is None:
            return "Day screens show today"
        return scene.week.leftover_parts(scene.today)[1]

    def _words(
        self, scene: Scene, item: Occurrence | None, is_now: bool, has_current: bool
    ) -> tuple[str, str]:
        if scene.today is None:
            return "Not this week", "Go back to planning and open this week to see today."
        if item is None:
            heading, _title, line = scene.week.leftover_parts(scene.today)
            tomorrow = scene.week.on_day(scene.today + 1)
            if scene.week.leftover_kind(scene.today) == "calendar_only" and scene.today < 6 and tomorrow:
                line = f"Tomorrow starts with {tomorrow[0].title} at {clock_label(tomorrow[0].start)}"
            return heading, line or heading
        if is_now:
            return "Now", range_label(item.start, item.end)
        first_upcoming = 1 if has_current else 0
        heading = "Up next" if self._skip == first_upcoming else "Later today"
        return heading, range_label(item.start, item.end)

    def _actions(self, scene: Scene, item: Occurrence | None) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(scene.px(SPACING[2]))
        row.addStretch()
        for entry in day_buttons(self, scene, item, "one"):
            row.addWidget(entry)
        row.addStretch()
        return row

    def _fit(self) -> None:
        """The ring as large as the window allows, up to its size in the mock-up. Then's rows give way
        from the bottom before the ring goes under RING_ROOMY, so a short window keeps the countdown."""
        ring, then = self._ring, self._then
        if ring is None or then is None:
            return
        scale = self._scene.scale if self._scene else 1.0
        for child in self.findChildren(QWidget):
            child.ensurePolished()
        margins = self._root.contentsMargins()
        across = self.width() - margins.left() - margins.right()
        ring.setFixedSize(RING_MIN, RING_MIN)
        shown = len(self._rows)
        while True:
            for index, row in enumerate(self._rows):
                row.setVisible(index < shown)
            then.setVisible(shown > 0)
            self._root.invalidate()
            others = self._root.totalMinimumSize().height() - RING_MIN
            side = min(across, round(RING_MAX * scale), self.height() - others)
            if shown == 0 or side >= round(RING_ROOMY * scale):
                break
            shown -= 1
        side = max(side, RING_MIN)
        ring.setFixedSize(side, side)
        then.setFixedWidth(max(min(across, round(RING_MAX * scale)), 0))
        self._fit_title()

    def _fit_title(self) -> None:
        """Inside the ring, in at most TITLE_SHARE of its height and two lines: at the title size, at
        the heading size when it needs more, and past that shortened, with the whole name in its
        tooltip. The number takes the height left over."""
        ring, title = self._ring, self._title
        if ring is None:
            return
        scale = self._scene.scale if self._scene else 1.0
        inside = ring.inside()
        width, budget = max(inside.width(), 40), inside.height() * TITLE_SHARE
        words = shown = self._title_words
        for role in ("title", "heading"):
            metrics = QFontMetrics(at_scale(title.font(), role, scale, WEIGHT_STRONG))
            tall = metrics.boundingRect(QRect(0, 0, width, 10_000), int(Qt.TextFlag.TextWordWrap), words)
            if round(tall.height() / metrics.lineSpacing()) <= 2 and tall.height() <= budget:
                break
        else:
            lines = 2 if metrics.lineSpacing() * 2 <= budget else 1
            shown = shortened(words, metrics, width, lines)
        title.setStyleSheet(f"font-size: {type_pt(role, scale)}pt;")
        title.setText(shown)
        title.setToolTip(words if shown != words else "")
        title.setAccessibleName(words)
        ring.lines_changed()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        scene = self._scene
        if scene is not None and event.key() == Qt.Key.Key_Space:
            queue, _ = self._queue(scene)
            self._skip = 0 if self._skip + 1 >= len(queue) else self._skip + 1
            self.render(scene, False)
            event.accept()
            return
        if scene is not None and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            queue, _ = self._queue(scene)
            if queue:
                self.block_activated.emit(queue[self._skip].block_id)
                event.accept()
                return
        super().keyPressEvent(event)
