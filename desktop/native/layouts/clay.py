"""Clay deck: one large Day card and seven live cards in a Week fan."""

from __future__ import annotations

from math import radians, sin

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLayout, QPushButton, QVBoxLayout, QWidget

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
    css,
    empty,
    family_fill,
    label,
    mark_of,
    plan_buttons,
    rules,
    scrolling,
)
from desktop.native.weekmodel import Waiting

CARD_KEYS = ("card_a", "card_b", "card_c", "card_d")
FAN_TURNS = (-8.0, -5.0, -2.0, 0.0, 2.0, 5.0, 8.0)
DAY_SCALE = Scale("clay.day", (72, 96, 120, 144), 96)
WEEK_SCALE = Scale("clay.week", (48, 64, 80, 96), 64)


def card_colour(tokens: dict[str, str], day: int) -> str:
    return tokens[CARD_KEYS[day % len(CARD_KEYS)]]


class ClayPainter(BlockPainter):
    def __init__(self, tokens: dict[str, str]) -> None:
        super().__init__({
            "window": tokens["bg"], "grid": tokens["line"], "hairline": tokens["line"],
            "accent": tokens["accent"], "accent_ink": tokens["accent_ink"],
            "error": tokens["danger"], "text": tokens["text"], "muted": tokens["muted"],
        })
        self.tokens = tokens

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        area = track.area
        shadow = QColor(self.tokens["text"])
        shadow.setAlpha(28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(area.translated(3, 5), 16, 16)
        painter.setBrush(QColor(card_colour(self.tokens, track.day)))
        painter.drawRoundedRect(area, 16, 16)
        painter.save()
        path = QPainterPath()
        path.addRoundedRect(area.adjusted(1, 1, -1, -1), 15, 15)
        painter.setClipPath(path)
        super().track(painter, track, today)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(self.tokens["surface"]), 3 if today else 2))
        painter.drawRoundedRect(area.adjusted(1, 1, -1, -1), 16, 16)

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        mark = QColor(mark_of(drawn.category))
        fill = QColor(family_fill(drawn.category, self.tokens))
        if drawn.done or drawn.missed:
            fill = QColor(self.tokens["surface"])
        return fill, QColor(self.tokens["text"]), QColor(self.tokens["surface"]), mark

    def block(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> None:
        painter.save()
        shadow = QColor(self.tokens["text"])
        shadow.setAlpha(34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(rect.translated(2, 3), 8, 8)
        super().block(painter, rect, drawn, visible)
        painter.restore()


class ClayCanvas(HoursCanvas):
    """The fixed name row names the tilted tracks even when the hours have scrolled."""

    def __init__(self, hand: Hand, painter: ClayPainter, lay_out, *, gutter: int = 0) -> None:
        super().__init__(hand, painter, lay_out, gutter=gutter)
        self.day_buttons: dict[int, QPushButton] = {}

    def day_name(self, day: int) -> QPoint:
        button = self.day_buttons.get(day)
        return button.mapToGlobal(button.rect().center()) if button is not None else super().day_name(day)


def _detach(layout: QLayout, widget: QWidget) -> bool:
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


class ClayDeckView(LayoutView):
    layout_id = "clay"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._page = QWidget()
        self._page.setObjectName("clayPage")
        self._root = QVBoxLayout(self._page)
        self._root.setContentsMargins(16, 12, 16, 12)
        outer.addWidget(scrolling(self._page, "clayScroll"))
        self._scrolls: dict[str, HoursScroll] = {}

    def shown_day(self, scene: Scene) -> int:
        if scene.surface == "day" and scene.iso_day:
            for day in range(7):
                if scene.week.date_of(day).isoformat() == scene.iso_day:
                    return day
        return scene.today if scene.today is not None else 0

    def _tracks(self, area: QRectF, day: int, week: bool, tilted: bool) -> list[LinearTrack]:
        if not week:
            return [LinearTrack(day, area.adjusted(8, 8, -8, -8))]
        turns = FAN_TURNS if tilted else (0.0,) * 7
        lean = abs(sin(radians(8))) * area.height() / 2 if tilted else 0
        margin = min(lean + 8, max(0.0, (area.width() - 7 * 48 - 6 * 8) / 2))
        gap = 8.0
        width = max(48.0, (area.width() - 2 * margin - 6 * gap) / 7)
        first_x = area.left() + margin
        tracks = []
        for index, turn in enumerate(turns):
            raised = index == 3
            x = first_x + index * (width + gap)
            card = QRectF(x, area.top() + (4 if raised else 13), width, area.height() - 22)
            tracks.append(LinearTrack(index, card, Axis.DOWN, FIRST, LAST, turn))
        return tracks

    def _hours(self, scene: Scene, day: int, week: bool) -> HoursScroll:
        key = "week" if week else "day"
        if key not in self._scrolls:
            canvas = ClayCanvas(self.hand, ClayPainter(scene.tokens), lambda area: self._tracks(
                area, day, week, scene.options.get("tilt") != "off"
            ), gutter=0 if week else scene.px(54))
            canvas.setObjectName("clayHours")
            canvas.setAccessibleName("Seven day cards" if week else "One day card")
            canvas.day_opened.connect(
                lambda target: self.day_activated.emit(self.scene.week.date_of(target).isoformat())
            )
            scale = WEEK_SCALE if week else DAY_SCALE
            scroll = self.keep_zoom(HoursScroll(
                canvas, scale, lambda px: round((LAST - FIRST) / 60 * px) + 32,
                name="clayWeek" if week else "clayDay", gutter=0, axis=Axis.DOWN,
            ))
            if week:
                scroll.set_header(self._names(scene, scroll))
                scroll.zoomed.connect(lambda _key, _px: self._align_names(scroll, self.scene.options))
            self._scrolls[key] = scroll
        scroll = self._scrolls[key]
        canvas = scroll.canvas
        canvas._lay_out = lambda area: self._tracks(area, day, week, scene.options.get("tilt") != "off")
        canvas.set_painter(ClayPainter(scene.tokens))
        canvas.relayout()
        if week:
            self._align_names(scroll, scene.options)
            for target, pick in canvas.day_buttons.items():
                pick.setText(f"{DAYS[target]} {scene.week.date_of(target).day}")
                pick.setStyleSheet(f"background: {card_colour(scene.tokens, target)};")
        canvas.set_week(
            scene.week.occurrences if week else [item for item in scene.week.occurrences if item.day == day],
            scene.today, scene.minute,
        )
        shown = None if week else day
        opens = opening_minute(scene.week, scene.today, scene.minute, shown)
        scroll.open_at((scene.week.week_start, shown), opens, above=120)
        scroll.setMinimumHeight(scene.px(390) if week else scene.px(430))
        return scroll

    def _tray(self, scene: Scene) -> QVBoxLayout:
        dish = QVBoxLayout()
        dish.setSpacing(scene.px(8))
        dish.addWidget(label("Not placed yet · in the dish", "clayTrayLabel"))
        for index, waiting in enumerate(scene.week.waiting):
            dish.addWidget(self._chip(waiting, index))
        dish.addStretch(1)
        return dish

    def _chip(self, waiting: Waiting, index: int) -> TrayChip:
        chip = TrayChip(self.hand, waiting)
        chip.setObjectName(f"clayWaiting{index}")
        chip.setProperty("kind", "chip")
        chip.clicked.connect(lambda _=False, block_id=waiting.block_id: self.block_activated.emit(block_id))
        return chip

    def _align_names(self, scroll: HoursScroll, options: dict[str, str]) -> None:
        row = scroll.header.findChild(QWidget, "clayNames").layout()
        lean = abs(sin(radians(8))) * (24 * scroll.px + 10) / 2 if options.get("tilt") != "off" else 0
        margin = round(lean + 8) if lean else 0
        row.setContentsMargins(margin, 0, margin, 0)

    def _names(self, scene: Scene, scroll: HoursScroll) -> QWidget:
        names = QWidget()
        names.setObjectName("clayNames")
        row = QHBoxLayout(names)
        row.setSpacing(scene.px(8))
        for target, word in enumerate(DAYS):
            pick = QPushButton(f"{word} {scene.week.date_of(target).day}")
            pick.setObjectName(f"clayDay{target}")
            pick.setProperty("kind", "day")
            pick.setProperty("day_target", target)
            pick.setAccessibleName(f"Show {DAY_FULL[target]}")
            pick.setToolTip(f"Open {DAY_FULL[target]}")
            pick.setStyleSheet(f"background: {card_colour(scene.tokens, target)};")
            pick.clicked.connect(lambda _=False, chosen=target: self.day_activated.emit(
                self.scene.week.date_of(chosen).isoformat()
            ))
            row.addWidget(pick, 1)
            scroll.canvas.day_buttons[target] = pick
        return names

    def render(self, scene: Scene, week_changed: bool) -> None:
        tokens, name = scene.tokens, self.objectName()
        self.setStyleSheet(base_sheet(name, tokens) + rules(name, {
            "#clayScroll, #clayPage": css(background=tokens["bg"]),
            "#clayTitle": css(font_size=f"{scene.px(23)}px", font_weight=800, color=tokens["bg_ink"]),
            "#clayTrayLabel": css(font_size=f"{scene.px(13)}px", font_weight=700, color=tokens["text"]),
            "#clayDish": css(background=tokens["surface"], border_radius=f"{scene.px(18)}px"),
            "QPushButton": css(background=tokens["surface"], color=tokens["text"],
                               border=f"2px solid {tokens['surface']}", border_radius=f"{scene.px(12)}px",
                               padding=f"0 {scene.px(7)}px", min_height=f"{scene.px(32)}px"),
            'QPushButton[zoom="true"]': css(min_height="0", padding="0"),
            'QPushButton[kind="day"]': css(font_size=f"{scene.px(12)}px", font_weight=700,
                                            border=f"2px solid {tokens['line']}"),
            'QPushButton[kind="chip"]': css(text_align="left", font_weight=600),
            'QPushButton[kind="main"]': css(background=tokens["accent"], color=tokens["accent_ink"]),
            "QPushButton:focus": css(border=f"2px solid {tokens['accent']}"),
        }))
        for kept in self._scrolls.values():
            _detach(self._root, kept)
        empty(self._root)
        self._root.setSpacing(scene.px(10))
        week = scene.surface != "day"
        day = self.shown_day(scene)
        if week:
            title = "Your week, fanned" if scene.options.get("tilt") != "off" else "Your week, laid out"
        else:
            title = f"{DAY_FULL[day]} {scene.week.date_of(day).day} · one day, up close"
        heading = QHBoxLayout()
        heading.addWidget(label(title, "clayTitle"))
        heading.addStretch(1)
        for made in plan_buttons(self, "clay", "Add homework"):
            heading.addWidget(made)
        self._root.addLayout(heading)
        scroll = self._hours(scene, day, week)
        if week:
            self._root.addWidget(scroll, 1)
            dish = QHBoxLayout()
            dish.addWidget(label("Not placed yet · in the dish", "clayTrayLabel"))
            for index, waiting in enumerate(scene.week.waiting):
                dish.addWidget(self._chip(waiting, index))
            dish.addStretch(1)
            self._root.addLayout(dish)
        else:
            body = QHBoxLayout()
            body.addWidget(scroll, 1)
            side = QFrame()
            side.setObjectName("clayDish")
            side.setFixedWidth(scene.px(210))
            side.setLayout(self._tray(scene))
            side.layout().setContentsMargins(scene.px(12), scene.px(12), scene.px(12), scene.px(12))
            body.addWidget(side)
            self._root.addLayout(body, 1)
        scroll.show()
