"""Menus in the look (decision 22 of 0.17): an icon on every row, the shortcut on the right, red for
deleting, the look's colours and corners, and the large shadow.

A style sheet paints every row of a QMenu in the menu's one text colour, so it cannot make Delete red.
The panel and the rows are painted here instead, from QMenu's own layout: where each row is, which one
the pointer or the keys are on, and what it says. The window is see-through round the panel, with room
for the shadow on every side (`look.MENU_EDGE`), and is moved up and left by that room as it opens, so
the panel lands where Qt placed the menu.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QActionEvent,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPaintEvent,
    QPen,
    QShowEvent,
)
from PySide6.QtWidgets import QMenu, QWidget, QWidgetAction

from desktop.native import icons
from desktop.native.elevation import lift
from desktop.native.fonts import caption
from desktop.native.look import MENU_EDGE, hover_tint
from desktop.native.tokens import RADIUS_CARD, RADIUS_CONTROL, SHADOW_LARGE

ICON = "iconName"
DANGER = "danger"
ICON_PX = 16
PAD = 8
GAP = 8


@dataclass(frozen=True)
class MenuColours:
    panel: str
    line: str
    text: str
    muted: str
    danger: str
    hover: str
    accent: str
    corner: int
    lifted: bool
    dark: bool


def menu_colours(palette: dict, *, lifted: bool = True, corner: int = RADIUS_CARD) -> MenuColours:
    """A menu in a look. `lifted` is whether the look draws shadows; `corner` its cards' radius."""
    return MenuColours(
        panel=palette["panel"],
        line=palette["hairline_strong" if palette.get("family") == "contrast" else "hairline"],
        text=palette["text"],
        muted=palette["muted"],
        danger=palette["error"],
        hover=hover_tint(palette),
        accent=palette["accent"],
        corner=corner,
        lifted=lifted,
        dark=palette.get("axis") == "dark",
    )


LIGHT = MenuColours(
    "#ffffff", "#e4e7ec", "#111827", "#5b6474", "#c42b1c", "#eeeff1", "#3d6fc4", RADIUS_CARD, True, False
)


def words_and_keys(action: QAction) -> tuple[str, str]:
    """A row's words and the shortcut after its tab, as QMenu writes them."""
    words, _, keys = action.text().partition("\t")
    return words, keys


class Menu(QMenu):
    def __init__(self, parent: QWidget | None = None, title: str = "") -> None:
        super().__init__(title, parent)
        self.setProperty("drawn", True)
        self.setToolTipsVisible(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._colours = LIGHT
        self.set_colours(LIGHT)

    def add(
        self, words: str, icon: str = "", *, keys: str = "", danger: bool = False, name: str = ""
    ) -> QAction:
        """A row: its words, a Lucide icon's name, the shortcut shown on the right, red if it deletes."""
        action = self.addAction(words + (f"\t{keys}" if keys else ""))
        if name:
            action.setObjectName(name)
        mark(action, icon, danger=danger)
        return action

    def add_menu(self, words: str, icon: str = "") -> Menu:
        inner = Menu(self, words)
        mark(self.addMenu(inner), icon)
        inner.set_colours(self._colours)
        return inner

    def colours(self) -> MenuColours:
        return self._colours

    def set_colours(self, colours: MenuColours) -> None:
        self._colours = colours
        if colours.lifted:
            lift(self, SHADOW_LARGE, colours.dark)
        else:
            self.setGraphicsEffect(None)
        for action in self.actions():
            inner = action.menu()
            if isinstance(inner, Menu):
                inner.set_colours(colours)
        self.update()

    # --- size and place -------------------------------------------------------------------------

    def actionEvent(self, event: QActionEvent) -> None:  # noqa: N802
        super().actionEvent(event)
        self._fit()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._fit()

    def _fit(self) -> None:
        """Wide enough for the widest row as it is painted here, whatever the style measured."""
        metrics = QFontMetrics(self.font())
        small = QFontMetrics(self._key_font())
        widest = 0
        for action in self.actions():
            if action.isSeparator() or isinstance(action, QWidgetAction):
                continue
            words, keys = words_and_keys(action)
            wide = 2 * PAD + ICON_PX + GAP + metrics.horizontalAdvance(words)
            if keys:
                wide += 3 * GAP + small.horizontalAdvance(keys)
            if action.menu() is not None or action.isCheckable():
                wide += GAP + ICON_PX
            widest = max(widest, wide)
        self.setMinimumWidth(widest + 2 * (MENU_EDGE + 4))

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        # Before the window is on screen: Qt placed the whole window where the panel belongs.
        if not event.spontaneous():
            self.move(self.pos() - QPoint(MENU_EDGE, MENU_EDGE))
        super().showEvent(event)

    # --- drawing --------------------------------------------------------------------------------

    def _key_font(self) -> QFont:
        return caption(self.font())

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        colours = self._colours
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inset = MENU_EDGE + 0.5
        panel = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        painter.setPen(QPen(QColor(colours.line), 1))
        painter.setBrush(QColor(colours.panel))
        painter.drawRoundedRect(panel, colours.corner, colours.corner)
        for action in self.actions():
            if not action.isVisible() or isinstance(action, QWidgetAction):
                continue
            rect = self.actionGeometry(action)
            if rect.isEmpty() or not rect.intersects(event.rect()):
                continue
            if action.isSeparator():
                painter.setPen(QPen(QColor(colours.line), 1))
                y = rect.center().y() + 0.5
                painter.drawLine(QPointF(rect.left() + PAD, y), QPointF(rect.right() - PAD, y))
                continue
            self._paint_row(painter, action, rect)

    def _paint_row(self, painter: QPainter, action: QAction, rect: QRect) -> None:
        colours = self._colours
        enabled = action.isEnabled()
        danger = bool(action.property(DANGER))
        if action is self.activeAction() and enabled:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colours.hover))
            corner = min(RADIUS_CONTROL, colours.corner)
            painter.drawRoundedRect(QRectF(rect).adjusted(0, 1, 0, -1), corner, corner)
        ink = colours.danger if danger else (colours.text if enabled else colours.muted)
        mark_ink = colours.danger if danger else colours.muted
        ratio = self.devicePixelRatioF()
        middle = rect.center().y() - ICON_PX // 2 + 1
        left = rect.left() + PAD
        name = action.property(ICON)
        if name:
            painter.drawPixmap(left, middle, icons.pixmap(str(name), mark_ink, ICON_PX, ratio))
        elif not action.icon().isNull():
            action.icon().paint(painter, QRect(left, middle, ICON_PX, ICON_PX))
        left += ICON_PX + GAP
        right = rect.right() - PAD
        end = None
        if action.menu() is not None:
            end = icons.pixmap("chevron-right", colours.muted, ICON_PX, ratio)
        elif action.isCheckable() and action.isChecked():
            end = icons.pixmap("check", colours.accent, ICON_PX, ratio)
        if end is not None:
            painter.drawPixmap(right - ICON_PX + 1, middle, end)
            right -= ICON_PX + GAP
        words, keys = words_and_keys(action)
        band = QRect(left, rect.top(), max(0, right - left + 1), rect.height())
        if keys:
            painter.setFont(self._key_font())
            painter.setPen(QColor(colours.danger if danger else colours.muted))
            painter.drawText(band, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, keys)
        painter.setFont(self.font())
        painter.setPen(QColor(ink))
        painter.drawText(band, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, words)


def mark(action: QAction, icon: str = "", *, danger: bool = False) -> QAction:
    """Give a row its icon and, for one that deletes, its red. The QIcon only reserves the room; the
    row's icon is painted in the look's colours."""
    if icon:
        action.setProperty(ICON, icon)
        action.setIcon(icons.icon(icon, "#000000"))
    if danger:
        action.setProperty(DANGER, True)
    return action
