"""Mission control: a horizontal scope on Day and seven live lanes on Week."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QHelpEvent, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLayout, QPushButton, QToolTip, QVBoxLayout, QWidget

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
    family_fill,
    label,
    mark_of,
    plan_buttons,
    rules,
    scrolling,
)
from desktop.native.weekmodel import clock_label, due_label

DAY_SCALE = Scale("mission.day", (72, 96, 120, 144), 96)
WEEK_SCALE = Scale("mission.week", (64, 80, 96, 112), 80)
AXIS = 32


class MissionPainter(BlockPainter):
    """The shared hours geometry dressed as Mission's dark scope."""

    def __init__(self, tokens: dict[str, str]) -> None:
        super().__init__({
            "window": tokens["bg"], "grid": tokens["line"], "hairline": tokens["line"],
            "accent": tokens["accent"], "accent_ink": tokens["accent_ink"],
            "error": tokens["danger"], "text": tokens["text"], "muted": tokens["bg_muted"],
        })
        self.tokens = tokens

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        painter.fillRect(track.area, QColor(self.tokens["surface"]))
        super().track(painter, track, today)
        painter.setPen(QPen(QColor(self.tokens["line"]), 1))
        painter.drawRect(track.area.adjusted(0, 0, -1, -1))

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        mark = QColor(mark_of(drawn.category))
        fill = QColor(self.tokens["surface"]).lighter(135)
        if not drawn.done and not drawn.missed:
            fill = QColor(family_fill(drawn.category, self.tokens))
        return fill, QColor(self.tokens["text"]), QColor(self.tokens["line"]), mark

    def block(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> None:
        super().block(painter, rect, drawn, visible)
        if not drawn.held and rect.width() < 22:
            # A quarter-hour still has a visible mark when its name cannot fit.
            painter.save()
            painter.setPen(QColor(self.tokens["text"]))
            painter.setFont(QFont("DejaVu Sans Mono", 8))
            painter.drawText(rect.adjusted(5, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter, drawn.title[:1])
            painter.restore()


def _lanes(area: QRectF) -> list[LinearTrack]:
    height = area.height() / 7
    return [LinearTrack(day, QRectF(area.left() + 30, area.top() + day * height + 2,
                                    area.width() - 34, height - 4), Axis.ACROSS)
            for day in range(7)]


class MissionCanvas(HoursCanvas):
    """Horizontal hours whose fixed day names belong to the scroll's side strip."""

    def __init__(self, hand: Hand, painter: MissionPainter,
                 lay_out: Callable[[QRectF], list[LinearTrack]]) -> None:
        super().__init__(hand, painter, lay_out, header=AXIS)
        self._day_buttons: dict[int, QPushButton] = {}

    def day_name(self, day: int) -> QPoint:
        pick = self._day_buttons.get(day)
        if pick is None:
            return super().day_name(day)
        return pick.mapToGlobal(pick.rect().center())

    def event(self, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            hit = self._block_at(QPointF(event.pos()))
            if hit is not None:
                QToolTip.showText(event.globalPos(), hit[0].title, self)
                return True
        return super().event(event)

    def reveal(self, day: int, first: int, last: int) -> None:
        """Leave room beyond the last minute so a held bar does not start edge scrolling."""
        area = self._scroll_area()
        track = self.track_for(day, first)
        if area is None or track is None:
            return
        for minute in (last, first):
            local = track.point_for(min(max(minute, track.first), track.last)).toPoint()
            area.ensureVisible(local.x(), local.y(), 60, 20)


def _detach(layout: QLayout, widget: QWidget) -> bool:
    """Take a retained scroll out of nested layouts before clearing the page."""
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


class MissionView(LayoutView):
    layout_id = "mission"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        # A view's minimum height must not become the window's: three designs pushed it past a 768 pixel
        # laptop screen. Inside a scroll area, what does not fit scrolls and the window keeps its size.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._page = QWidget()
        self._page.setObjectName("missionPage")
        self._root = QVBoxLayout(self._page)
        self._root.setContentsMargins(14, 10, 14, 10)
        outer.addWidget(scrolling(self._page, "missionScroll"))
        self._scrolls: dict[str, HoursScroll] = {}

    def shown_day(self, scene: Scene) -> int:
        if scene.surface == "day" and scene.iso_day:
            for day in range(7):
                if scene.week.date_of(day).isoformat() == scene.iso_day:
                    return day
        return scene.today if scene.today is not None else 0

    def render(self, scene: Scene, week_changed: bool) -> None:
        tokens, name = scene.tokens, self.objectName()
        mono = "DejaVu Sans Mono, Noto Sans Mono, monospace"
        self.setStyleSheet(
            base_sheet(name, tokens)
            + rules(
                name,
                {
                    "#missionScroll, #missionPage": css(background=tokens["bg"]),
                    "QLabel": css(
                        font_size=f"{scene.px(12)}px", letter_spacing="1px", color=tokens["bg_muted"]
                    ),
                    "#missionTitle": css(
                        color=tokens["bg_ink"], font_size=f"{scene.px(15)}px", font_weight=800
                    ),
                    "#missionClock, #missionPlaced": css(
                        color=tokens["accent"], font_family=mono, font_weight=700
                    ),
                    "#missionSide": css(background=tokens["surface"], border=f"1px solid {tokens['line']}"),
                    "QPushButton": css(
                        background=tokens["surface"],
                        color=tokens["accent"],
                        border=f"1px solid {tokens['accent']}",
                        border_radius="0",
                        padding=f"0 {scene.px(12)}px",
                        min_height=f"{scene.px(34)}px",
                        font_family=mono,
                        font_size=f"{scene.px(12)}px",
                        font_weight=700,
                    ),
                    'QPushButton[zoom="true"]': css(min_height="0", padding="0"),
                    'QPushButton[kind="main"]': css(background=tokens["accent"], color=tokens["accent_ink"]),
                    'QPushButton[kind="row"], QPushButton[kind="chip"], QPushButton[kind="day"]': css(
                        color=tokens["text"],
                        border=f"1px solid {tokens['line']}",
                        text_align="left",
                        font_family="inherit",
                        font_weight=500,
                    ),
                    'QPushButton[kind="row"][risk="danger"]': css(
                        border_left=f"4px solid {tokens['danger']}"
                    ),
                    'QPushButton[kind="row"][risk="tight"]': css(border_left=f"4px solid {tokens['accent']}"),
                    'QPushButton[kind="day"][chosen="true"]': css(
                        border=f"1px solid {tokens['accent']}", color=tokens["accent"], font_weight=800
                    ),
                    'QPushButton[kind="chip"][state="past"]': css(
                        color=tokens["muted"], text_decoration="line-through"
                    ),
                    "QPushButton:focus": css(border=f"2px solid {tokens['bg_ink']}"),
                    'QFrame[role="load"]': css(background=tokens["accent"]),
                },
            )
        )
        # The hours keep their viewport and zoom when a refreshed scene redraws the HUD.
        for kept in self._scrolls.values():
            _detach(self._root, kept)
        empty(self._root)
        self._root.setSpacing(scene.px(8))
        week, day = scene.week, self.shown_day(scene)
        placed = len({item.block_id for item in week.occurrences if item.work})
        head = QHBoxLayout()
        head.setSpacing(scene.px(16))
        title = (f"FLEXWEEK / DAY / {DAY_FULL[day].upper()} {week.date_of(day).day}"
                 if scene.surface == "day" else f"FLEXWEEK / WEEK {week.date_of(0).isocalendar().week}")
        head.addWidget(label(title, "missionTitle"))
        head.addWidget(label(f"LOCAL {clock_label(scene.minute)}", "missionClock"))
        head.addWidget(label(f"PLAN {placed}/{placed + len(week.waiting)} PLACED", "missionPlaced"))
        head.addStretch(1)
        for made in plan_buttons(self, "mission", "+ ADD"):
            head.addWidget(made)
        self._root.addLayout(head)
        body = QHBoxLayout()
        body.setSpacing(scene.px(12))
        left = QVBoxLayout()
        is_day = scene.surface == "day"
        key = "day" if is_day else "week"
        if key not in self._scrolls:
            layout = (
                (lambda area: [LinearTrack(day, area.adjusted(30, 4, -4, -4), Axis.ACROSS)])
                if is_day else _lanes
            )
            canvas = MissionCanvas(self.hand, MissionPainter(tokens), layout)
            canvas.setObjectName("missionHours")
            canvas.setAccessibleName("Scope lane" if is_day else "Seven day lanes")
            canvas.setAccessibleDescription(
                "Drag a block to move it, pull its left or right end to resize it, "
                "or drag empty time to add something. Click a block to open it."
            )
            canvas.day_opened.connect(
                lambda target: self.day_activated.emit(self.scene.week.date_of(target).isoformat())
            )
            scale = DAY_SCALE if is_day else WEEK_SCALE
            scroll = HoursScroll(canvas, scale, lambda px: round((LAST - FIRST) / 60 * px) + 34,
                                 name="missionDay" if is_day else "missionWeek",
                                 gutter=scene.px(96), axis=Axis.ACROSS)
            self.keep_zoom(scroll)
            if not is_day:
                names = QWidget()
                name_column = QVBoxLayout(names)
                name_column.setContentsMargins(0, 0, 0, 0)
                name_column.setSpacing(0)
                for target, word in enumerate(DAYS):
                    pick = button(f"{word.upper()} {week.date_of(target).day}", f"missionDay{target}", "day")
                    pick.setAccessibleName(f"Show {DAY_FULL[target]}")
                    pick.setProperty("day_target", target)
                    pick.clicked.connect(
                        lambda _=False, chosen=target:
                        self.day_activated.emit(self.scene.week.date_of(chosen).isoformat())
                    )
                    name_column.addWidget(pick, 1)
                    canvas._day_buttons[target] = pick
                scroll.set_header(names)
            self._scrolls[key] = scroll
        scroll = self._scrolls[key]
        canvas = scroll.canvas
        canvas.set_painter(MissionPainter(tokens))
        if is_day:
            canvas._lay_out = lambda area: [LinearTrack(day, area.adjusted(30, 4, -4, -4), Axis.ACROSS)]
            canvas.relayout()
            scroll.setMinimumHeight(scene.px(320))
        else:
            scroll.setFixedHeight(470)
            for target, pick in canvas._day_buttons.items():
                pick.setText(f"{DAYS[target].upper()} {week.date_of(target).day}")
        canvas.set_week(
            [item for item in week.occurrences if not is_day or item.day == day],
            scene.today, scene.minute,
        )
        shown = day if is_day else None
        scroll.open_at((week.week_start, shown), opening_minute(week, scene.today, scene.minute, shown))
        left.addWidget(scroll, 1)
        if is_day:
            cargo = QFrame()
            cargo.setObjectName("missionCargo")
            hold = QVBoxLayout(cargo)
            hold.addWidget(label("NOT PLACED YET · CARGO BAY", "missionUnplaced"))
            hold.addLayout(self._tray(scene))
            left.addWidget(cargo)
        body.addLayout(left, 1)
        # The radar is the first thing to go when there is no room: the lanes are the point, and
        # everything the radar says is also in the unplaced strip and the day row.
        if not is_day and scene.options.get("side") != "hide" and not self.cramped:
            body.addWidget(self._side(scene))
        self._root.addLayout(body, 1)
        scroll.show()
        if not is_day and (scene.options.get("side") == "hide" or self.cramped):
            cargo = QFrame()
            cargo.setObjectName("missionCargo")
            hold = QVBoxLayout(cargo)
            hold.addWidget(label("NOT PLACED YET · PENDING", "missionUnplaced"))
            hold.addLayout(self._tray(scene))
            self._root.addWidget(cargo)

    def _tray(self, scene: Scene) -> QHBoxLayout:
        row = QHBoxLayout()
        for index, waiting in enumerate(scene.week.waiting):
            chip = TrayChip(self.hand, waiting)
            chip.setObjectName(f"missionWaiting{index}")
            chip.setProperty("kind", "chip")
            chip.clicked.connect(
                lambda _=False, block_id=waiting.block_id: self.block_activated.emit(block_id)
            )
            row.addWidget(chip)
        row.addStretch(1)
        return row

    def _side(self, scene: Scene) -> QFrame:
        side = QFrame()
        side.setObjectName("missionSide")
        side.setFixedWidth(scene.px(290))
        inner = QVBoxLayout(side)
        inner.setContentsMargins(scene.px(10), scene.px(10), scene.px(10), scene.px(10))
        inner.addWidget(label("NOT PLACED YET · PENDING", "missionUnplaced"))
        inner.addLayout(self._tray(scene))
        inner.addWidget(label("DEADLINE RADAR", "missionRadarTitle"))
        work = list(scene.week.open_work())
        seen = {item.block_id for item in work}
        waiting = [item for item in scene.week.waiting if item.block_id not in seen]
        for index, item in enumerate(work):
            due = due_label(item.due, scene.week.week_start)
            extra = f" · {item.slack_words.upper()}" if item.slack_words else ""
            row = button(f"{item.title}\n{due}{extra}", f"missionRadar{index}", "row")
            row.clicked.connect(lambda _=False, block_id=item.block_id: self.block_activated.emit(block_id))
            row.setProperty("risk", item.slack or "")
            row.setStyleSheet(f"min-height: {scene.px(40)}px;")
            room = scene.px(220)
            title = QFontMetrics(row.font()).elidedText(item.title, Qt.TextElideMode.ElideRight, room)
            row.setText(f"{title}\n{due}{extra}")
            row.setToolTip(item.title)
            inner.addWidget(row)
        offset = len(work)
        for index, item in enumerate(waiting):
            due = due_label(item.due, scene.week.week_start)
            row = button(f"{item.title}\n{due} · {item.reason}", f"missionRadar{offset + index}", "row")
            row.clicked.connect(lambda _=False, block_id=item.block_id: self.block_activated.emit(block_id))
            row.setProperty("risk", "danger")
            inner.addWidget(row)
        if not work and not waiting:
            heading, title, line = scene.week.leftover_parts(scene.today)
            inner.addWidget(label((line or heading or title).upper(), "missionRadarEmpty"))
        inner.addSpacing(scene.px(10))
        inner.addWidget(label("HOMEWORK LOAD / DAY", "missionLoadTitle"))
        bars = QHBoxLayout()
        most = max([scene.week.load_min(day) for day in range(7)] + [1])
        for day, name in enumerate(DAYS):
            column = QVBoxLayout()
            column.addStretch(1)
            bar = QFrame()
            bar.setProperty("role", "load")
            bar.setFixedHeight(max(round(scene.px(54) * scene.week.load_min(day) / most), 2))
            column.addWidget(bar)
            column.addWidget(label(name[0], f"missionLoad{day}"), 0, Qt.AlignmentFlag.AlignHCenter)
            bars.addLayout(column)
        inner.addLayout(bars)
        inner.addStretch(1)
        return side
