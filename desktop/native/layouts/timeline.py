"""Timeline: ink on paper. Day is one ruled column; Week is seven lines of hours down the page.

Day keeps the big day heading. Under it the day is a ruled column like a notebook page, with ink
cards on it and NOW in red, and homework with no time waits in the margin on the right. Week reads
down the page like an article: each day a big heading with its hours running across beside it. The
seven lines are one canvas, so a block carried to another day's line never leaves the surface it
started on. Both are the shared hours, on the window's hand.
"""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from desktop.native.calendar import DAY_FULL, DAYS
from desktop.native.hours.canvas import BlockPainter, Drawn, HoursCanvas
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.geometry import FIRST, LAST, Axis, LinearTrack
from desktop.native.hours.hand import Hand
from desktop.native.hours.zoom import HoursScroll, Scale, opening_minute
from desktop.native.layouts.base import (
    LayoutView,
    Scene,
    base_sheet,
    button,
    css,
    empty,
    label,
    mark_of,
    plan_buttons,
    rules,
    scrolling,
)
from desktop.native.weekmodel import Occurrence, Waiting, planned_line

DAY_SCALE = Scale("timeline.day", (72, 96, 120, 144), 96)
WEEK_SCALE = Scale("timeline.week", (48, 64, 80, 96), 64)
# Room above and below the column, and either side of each line, for the first and last hour's label.
END_ROOM = 24
# The page scrolls a held block's day this far clear of its edge, so the neighbouring days show too.
NEIGHBOURS = 1.2


class TimelinePainter(BlockPainter):
    """A white ruled page. Homework is an ink card, anything else a white card outlined in ink, each
    with its category's colour down its start edge. The held block is lifted on a hard shadow."""

    def __init__(self, tokens: dict[str, str], rule: float = 0.0) -> None:
        super().__init__({
            "window": tokens["bg"], "grid": tokens["line"], "hairline": tokens["line"],
            "accent": tokens["accent"], "accent_ink": tokens["accent_ink"],
            "error": tokens["danger"], "text": tokens["text"], "muted": tokens["bg_muted"],
        })
        self.tokens = tokens
        # How far below each line of the week its section ends, where a rule divides it from the next.
        self.rule = rule

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        area = track.area
        painter.fillRect(area, QColor(self.tokens["surface"]))
        # Only the week's lines tint today: Day shows one day, and its page stays white.
        super().track(painter, track, today and track.axis is Axis.ACROSS)
        painter.setPen(QPen(QColor(self.tokens["line"]), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(area.adjusted(0, 0, -1, -1))
        if self.rule and track.axis is Axis.ACROSS:
            below = area.bottom() + self.rule
            painter.drawLine(QPointF(area.left() - END_ROOM, below), QPointF(area.right() + END_ROOM, below))

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        # Anything else is a card of the paper the page is printed on, so it stands off the white page.
        mark = QColor(mark_of(drawn.category))
        ink, paper = QColor(self.tokens["text"]), QColor(self.tokens["surface"])
        if drawn.done or drawn.missed:
            return QColor(self.tokens["bg"]), QColor(self.tokens["muted"]), QColor(self.tokens["line"]), mark
        if drawn.work:
            return ink, paper, None, mark
        return QColor(self.tokens["bg"]), ink, ink, mark

    def block(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> None:
        # Both under the card: an ink ring round an ink card cannot be seen, and a ring clear of the
        # card can, on the white page, whatever the card's colour.
        painter.save()
        ink = QColor(self.tokens["text"])
        if drawn.held:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            painter.drawRoundedRect(rect.translated(4, 4), 5, 5)
        elif drawn.chosen:
            painter.setPen(QPen(ink, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 7, 7)
        painter.restore()
        super().block(painter, rect, drawn, visible)

    def now(self, painter: QPainter, track: LinearTrack, minute: int) -> None:
        super().now(painter, track, minute)
        room = track.area.left() - 8
        if track.axis is not Axis.DOWN or track.turn or room < 24:
            return
        # In the hour labels' gutter, over whichever label is there.
        at = track.area.top() + track.offset(minute)
        box = QRectF(2, at - 9, room, 18)
        painter.fillRect(box, QColor(self.tokens["bg"]))
        bold = QFont(painter.font())
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor(self.tokens["danger"]))
        painter.drawText(box, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "NOW")


def _column(day: int, area: QRectF) -> list[LinearTrack]:
    return [LinearTrack(day, area.adjusted(0, END_ROOM / 2, -12, -END_ROOM / 2))]


def _column_length(px: int) -> int:
    return round((LAST - FIRST) / 60 * px) + END_ROOM


def _lines(pad: float, area: QRectF) -> list[LinearTrack]:
    tall = area.height() / 7
    return [
        LinearTrack(
            day,
            QRectF(area.left() + END_ROOM, area.top() + day * tall + pad,
                   area.width() - 2 * END_ROOM, tall - 2 * pad),
            Axis.ACROSS,
        )
        for day in range(7)
    ]


def _line_length(px: int) -> int:
    return round((LAST - FIRST) / 60 * px) + 2 * END_ROOM


def _page_of(widget: QWidget | None) -> QScrollArea | None:
    """The scroll area holding this one: the page, where the hours' own scroll is inside it."""
    found = widget.parentWidget() if widget is not None else None
    while found is not None and not isinstance(found, QScrollArea):
        found = found.parentWidget()
    return found


class TimelineCanvas(HoursCanvas):
    """Hours on a page that scrolls too. A time is brought on screen in the hours and then in the
    page, and the week's day names are the headings beside its lines."""

    def __init__(self, hand: Hand, painter: TimelinePainter, lay_out, *, gutter: float = 0) -> None:
        super().__init__(hand, painter, lay_out, gutter=gutter)
        self.headings: dict[int, DayHeading] = {}

    def day_name(self, day: int) -> QPoint:
        heading = self.headings.get(day)
        return heading.mapToGlobal(heading.rect().center()) if heading is not None else super().day_name(day)

    def reveal(self, day: int, first: int, last: int) -> None:
        area = self._scroll_area()
        track = self.track_for(day, first) or self.track_for(day)
        if area is None or track is None:
            return
        across = track.axis is Axis.ACROSS
        page = _page_of(area)
        for minute in (last, first):
            local = track.point_for(min(max(minute, track.first), track.last)).toPoint()
            # Clear of the edge where a held block starts the hours scrolling.
            area.ensureVisible(local.x(), local.y(), 60 if across else 20, 20 if across else 60)
        if page is None:
            return
        reach = round(track.area.height() * NEIGHBOURS) if across else 60
        for minute in (last, first):
            local = track.point_for(min(max(minute, track.first), track.last)).toPoint()
            inside = self.mapTo(page.widget(), local)
            page.ensureVisible(inside.x(), inside.y(), 0, reach)

    def in_view(self, day: int, minute: int) -> bool:
        if not super().in_view(day, minute):
            return False
        page = _page_of(self._scroll_area())
        track = self.track_for(day, minute)
        if page is None or track is None:
            return True
        port = page.viewport()
        at = self.mapTo(port, track.point_for(minute).toPoint())
        return port.rect().adjusted(-2, -2, 2, 2).contains(at)


class DayHeading(QPushButton):
    """A day's big name with its date under it, beside its line of hours. Clicked, it opens the day."""

    opened = Signal(int)

    def __init__(self, day: int) -> None:
        super().__init__()
        self.day = day
        self.setObjectName(f"timelineWeekDay{day}")
        self.setProperty("kind", "heading")
        self.setProperty("day_target", day)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Show {DAY_FULL[day]}")
        self.setToolTip(f"Open {DAY_FULL[day]}")
        # As tall as its line of hours, whatever its words would like.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        stack = QVBoxLayout(self)
        stack.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        stack.setContentsMargins(4, 0, 8, 0)
        stack.setSpacing(0)
        self.title = label(DAY_FULL[day], "timelineHeadingName")
        self.date = label("", "timelineHeadingDate")
        stack.addStretch(1)
        # No indent once today's underline gives the name a frame, so it stays in line with the others.
        self.title.setIndent(0)
        for part in (self.title, self.date):
            part.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            stack.addWidget(part, 0, Qt.AlignmentFlag.AlignLeft)
        stack.addStretch(1)
        self.clicked.connect(self._open)

    def _open(self, _checked: bool = False) -> None:
        self.opened.emit(self.day)


def _detach(layout: QLayout, widget: QWidget) -> bool:
    """Take a kept scroll out of the page before the page is cleared."""
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            layout.takeAt(index)
            widget.hide()
            return True
        inner = item.layout()
        if inner is not None and _detach(inner, widget):
            return True
    return False


class TimelineView(LayoutView):
    layout_id = "timeline"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._page = QWidget()
        self._page.setObjectName("timelinePage")
        self._root = QVBoxLayout(self._page)
        self._root.setContentsMargins(16, 8, 16, 10)
        outer.addWidget(scrolling(self._page, "timelineScroll"))
        self._scrolls: dict[str, HoursScroll] = {}
        # The text size each was made at: its gutter is fixed when it is made.
        self._made_at: dict[str, float] = {}

    def shown_day(self, scene: Scene) -> int:
        if scene.surface == "day" and scene.iso_day:
            for day in range(7):
                if scene.week.date_of(day).isoformat() == scene.iso_day:
                    return day
        return scene.today if scene.today is not None else 0

    def render(self, scene: Scene, week_changed: bool) -> None:
        compact = scene.options.get("density") == "compact"
        self._style(scene, compact)
        for kept in self._scrolls.values():
            _detach(self._root, kept)
        empty(self._root)
        self._root.setSpacing(scene.px(6 if compact else 10))
        if scene.surface == "day":
            self._render_day(scene)
        else:
            self._render_week(scene, compact)

    def _style(self, scene: Scene, compact: bool) -> None:
        tokens, name = scene.tokens, self.objectName()
        pad = scene.px(6 if compact else 10)
        self.setStyleSheet(
            base_sheet(name, tokens)
            + rules(
                name,
                {
                    "#timelineScroll, #timelinePage": css(background=tokens["bg"]),
                    "#timelineDay, #timelineWeekTitle": css(
                        font_size=f"{scene.px(30 if compact else 42)}px",
                        font_weight=900,
                        letter_spacing="-1px",
                    ),
                    "#timelineWeekTitle": css(font_size=f"{scene.px(26 if compact else 34)}px"),
                    "#timelineSub, #timelineTrayHint, #timelineHeadingDate": css(
                        color=tokens["bg_muted"], font_size=f"{scene.px(14)}px"
                    ),
                    "#timelineTrayHint, #timelineHeadingDate": css(font_size=f"{scene.px(12)}px"),
                    "#timelineTrayLabel": css(font_size=f"{scene.px(13)}px", font_weight=800),
                    "#timelineMargin": css(border_left=f"2px solid {tokens['bg_ink']}"),
                    "#timelineHeadingName": css(
                        font_size=f"{scene.px(18 if compact else 22)}px",
                        font_weight=900,
                        letter_spacing="-0.5px",
                    ),
                    "QPushButton": css(
                        background=tokens["surface"],
                        color=tokens["text"],
                        border=f"2px solid {tokens['text']}",
                        border_radius=f"{scene.px(12)}px",
                        padding=f"0 {scene.px(16)}px",
                        min_height=f"{scene.px(40)}px",
                        font_size=f"{scene.px(14)}px",
                        font_weight=600,
                    ),
                    'QPushButton[zoom="true"]': css(min_height="0", padding="0", border_radius="4px"),
                    'QPushButton[kind="main"]': css(background=tokens["accent"], color=tokens["accent_ink"]),
                    'QPushButton[kind="day"]': css(
                        border=f"2px solid {tokens['line']}",
                        padding=f"{scene.px(4)}px",
                        min_height=f"{scene.px(28)}px",
                        font_size=f"{scene.px(12)}px",
                    ),
                    'QPushButton[kind="day"][chosen="true"]': css(
                        background=tokens["accent"], color=tokens["accent_ink"],
                        border=f"2px solid {tokens['accent']}", font_weight=800,
                    ),
                    'QPushButton[kind="chip"]': css(
                        border=f"1px dashed {tokens['text']}",
                        border_left=f"4px solid {tokens['danger']}",
                        border_radius="3px",
                        text_align="left",
                        padding=f"0 {pad}px",
                        min_height=f"{scene.px(34)}px",
                        font_size=f"{scene.px(13)}px",
                    ),
                    'QPushButton[kind="heading"]': css(
                        background="transparent",
                        border="none",
                        border_bottom=f"1px solid {tokens['line']}",
                        border_radius="0",
                        padding="0",
                        min_height="0",
                    ),
                    "QPushButton:focus": css(border=f"3px solid {tokens['danger']}"),
                    'QFrame[role="track"]': css(background=tokens["line"], border_radius="3px"),
                    'QFrame[role="load"]': css(background=tokens["text"], border_radius="3px"),
                },
            )
        )

    # Day: Column rule

    def _render_day(self, scene: Scene) -> None:
        day = self.shown_day(scene)
        head = QHBoxLayout()
        head.addWidget(label(DAY_FULL[day], "timelineDay"))
        head.addStretch(1)
        for made in plan_buttons(self, "timeline", "+ Add homework"):
            head.addWidget(made, 0, Qt.AlignmentFlag.AlignVCenter)
        self._root.addLayout(head)
        date = scene.week.date_of(day)
        load = _load(scene.week.on_day(day))
        self._root.addWidget(label(f"{date.strftime('%B')} {date.day} · {load}", "timelineSub"))
        self._root.addLayout(self._strip(scene, day))
        body = QHBoxLayout()
        body.setSpacing(scene.px(18))
        scroll = self._day_hours(scene, day)
        body.addWidget(scroll, 1)
        body.addWidget(self._margin(scene))
        self._root.addLayout(body, 1)
        scroll.show()

    def _day_hours(self, scene: Scene, day: int) -> HoursScroll:
        scroll = self._kept("day", scene)
        if scroll is None:
            canvas = TimelineCanvas(self.hand, TimelinePainter(scene.tokens), partial(_column, day))
            canvas.setObjectName("timelineHours")
            canvas.setAccessibleName("The day's page")
            scroll = self.keep_zoom(HoursScroll(
                canvas, DAY_SCALE, _column_length, name="timelineColumn", gutter=scene.px(56),
            ))
            self._keep("day", scroll, scene)
        canvas = scroll.canvas
        canvas._lay_out = partial(_column, day)
        canvas.set_painter(TimelinePainter(scene.tokens))
        canvas.relayout()
        canvas.set_week(_shown(scene, scene.week.on_day(day)), scene.today, scene.minute)
        opens = opening_minute(scene.week, scene.today, scene.minute, day)
        scroll.open_at((scene.week.week_start, day), opens, above=120)
        scroll.setMinimumHeight(scene.px(260))
        return scroll

    def _strip(self, scene: Scene, shown: int) -> QHBoxLayout:
        strip = QHBoxLayout()
        strip.setSpacing(scene.px(6))
        most = max([scene.week.load_min(day) for day in range(7)] + [1])
        for day, name in enumerate(DAYS):
            cell = QVBoxLayout()
            cell.setSpacing(2)
            pick = button(f"{name} {scene.week.date_of(day).day}", f"timelineDay{day}", "day")
            pick.setProperty("chosen", "true" if day == shown else "false")
            pick.setProperty("day_target", day)
            pick.setAccessibleName(f"Show {DAY_FULL[day]}, {scene.week.load_min(day)} minutes of homework")
            pick.clicked.connect(lambda _=False, target=day: self._open_day(target))
            cell.addWidget(pick)
            if scene.options.get("strip") != "names":
                # A bare 4px stub under each button read as debris. The bar sits in a track of its own,
                # so a light day is a short bar in a slot rather than a stray mark.
                track = QFrame()
                track.setProperty("role", "track")
                track.setFixedHeight(scene.px(6))
                inside = QHBoxLayout(track)
                inside.setContentsMargins(0, 0, 0, 0)
                inside.setSpacing(0)
                bar = QFrame()
                bar.setProperty("role", "load")
                share = scene.week.load_min(day) / most
                inside.addWidget(bar, max(round(share * 100), 3))
                inside.addStretch(max(round((1 - share) * 100), 0))
                cell.addWidget(track)
            strip.addLayout(cell)
        return strip

    def _margin(self, scene: Scene) -> QFrame:
        margin = QFrame()
        margin.setObjectName("timelineMargin")
        margin.setFixedWidth(scene.px(210))
        inner = QVBoxLayout(margin)
        inner.setContentsMargins(scene.px(14), scene.px(8), 0, 0)
        inner.setSpacing(scene.px(8))
        inner.addWidget(label("Not placed yet · in the margin", "timelineTrayLabel", wrap=True))
        waiting = scene.week.waiting
        words = "Drag one onto the page to give it a time." if waiting else "Nothing is waiting for a time."
        inner.addWidget(label(words, "timelineTrayHint", wrap=True))
        for index, item in enumerate(waiting):
            inner.addWidget(self._chip(item, index))
        inner.addStretch(1)
        return margin

    def _chip(self, waiting: Waiting, index: int) -> TrayChip:
        chip = TrayChip(self.hand, waiting)
        chip.setObjectName(f"timelineWaiting{index}")
        chip.setProperty("kind", "chip")
        chip.clicked.connect(lambda _=False, block_id=waiting.block_id: self.block_activated.emit(block_id))
        return chip

    # Week: Continuous scroll

    def _render_week(self, scene: Scene, compact: bool) -> None:
        week = scene.week
        head = QHBoxLayout()
        head.setSpacing(scene.px(14))
        head.addWidget(label("This week", "timelineWeekTitle"))
        first, last = week.date_of(0), week.date_of(6)
        span = f"{first.day} {first:%B} – {last.day} {last:%B}"
        sub = label(f"{span} · {_load(week.occurrences)}", "timelineSub")
        head.addWidget(sub, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        for made in plan_buttons(self, "timeline", "+ Add homework"):
            head.addWidget(made, 0, Qt.AlignmentFlag.AlignVCenter)
        self._root.addLayout(head)
        scroll = self._week_hours(scene, compact)
        self._root.addWidget(scroll, 1)
        tray = QHBoxLayout()
        tray.setSpacing(scene.px(8))
        tray.addWidget(label("Not placed yet · in the margin", "timelineTrayLabel"))
        for index, item in enumerate(week.waiting):
            tray.addWidget(self._chip(item, index))
        if not week.waiting:
            tray.addWidget(label("Nothing is waiting for a time.", "timelineTrayHint"))
        tray.addStretch(1)
        self._root.addLayout(tray)
        scroll.show()

    def _week_hours(self, scene: Scene, compact: bool) -> HoursScroll:
        pad = scene.px(4 if compact else 6)
        scroll = self._kept("week", scene)
        if scroll is None:
            canvas = TimelineCanvas(self.hand, TimelinePainter(scene.tokens, pad), partial(_lines, pad))
            canvas.setObjectName("timelineLines")
            canvas.setAccessibleName("The week, a line of hours for each day")
            canvas.setAccessibleDescription(
                "Drag along a day's line to change the time, or onto another day's line. Pull a block's "
                "left or right end to resize it, or drag empty time to add something. Click a block to "
                "open it."
            )
            scroll = self.keep_zoom(HoursScroll(
                canvas, WEEK_SCALE, _line_length, name="timelineWeek", gutter=scene.px(170), axis=Axis.ACROSS,
            ))
            scroll.set_header(self._headings(canvas))
            self._keep("week", scroll, scene)
        canvas = scroll.canvas
        canvas._lay_out = partial(_lines, pad)
        canvas.set_painter(TimelinePainter(scene.tokens, pad))
        canvas.relayout()
        for day, heading in canvas.headings.items():
            date = scene.week.date_of(day)
            heading.date.setText(f"{date.day} {date:%B}")
            today = day == scene.today
            heading.title.setStyleSheet(
                f"border-bottom: {scene.px(4)}px solid {scene.tokens['danger']};" if today else ""
            )
        canvas.set_week(_shown(scene, scene.week.occurrences), scene.today, scene.minute)
        opens = opening_minute(scene.week, scene.today, scene.minute)
        scroll.open_at(scene.week.week_start, opens, above=180)
        # Seven lines share what the window has; below this each line is too thin to hold a block's
        # name, and the page scrolls instead.
        scroll.setMinimumHeight(scene.px(30) + 7 * scene.px(38 if compact else 46))
        return scroll

    def _headings(self, canvas: TimelineCanvas) -> QWidget:
        names = QWidget()
        names.setObjectName("timelineHeadings")
        column = QVBoxLayout(names)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for day in range(7):
            heading = DayHeading(day)
            heading.opened.connect(self._open_day)
            column.addWidget(heading, 1)
            canvas.headings[day] = heading
        return names

    # Shared

    def _open_day(self, day: int) -> None:
        if self._scene is not None:
            self.day_activated.emit(self._scene.week.date_of(day).isoformat())

    def _kept(self, key: str, scene: Scene) -> HoursScroll | None:
        """The hours this tab made before, unless the text size has changed since: their gutter was
        sized for the old one, so they are made again, at the zoom the window remembers."""
        scroll = self._scrolls.get(key)
        if scroll is not None and self._made_at.get(key) != scene.scale:
            del self._scrolls[key]
            scroll.deleteLater()
            return None
        return scroll

    def _keep(self, key: str, scroll: HoursScroll, scene: Scene) -> None:
        self._scrolls[key] = scroll
        self._made_at[key] = scene.scale


def _load(items: tuple[Occurrence, ...]) -> str:
    work = [item for item in items if item.work]
    return planned_line(sum(item.minutes for item in work), sum(item.minutes for item in work if item.done))


def _shown(scene: Scene, items: tuple[Occurrence, ...]) -> list[Occurrence]:
    """What the hours draw: everything, or with Finished and past items hidden, what is still ahead."""
    if scene.options.get("finished") != "hide":
        return list(items)
    today = scene.today

    def over(item: Occurrence) -> bool:
        if today is None:
            return False
        return item.day < today or (item.day == today and item.end <= scene.minute)

    return [item for item in items if item.live and not over(item)]
