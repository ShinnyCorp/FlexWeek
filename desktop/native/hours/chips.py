"""Things outside the hours that can be dragged onto them."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QPushButton, QWidget

from desktop.native.hours.hand import Gesture, Hand, Held
from desktop.native.weekmodel import Waiting, length_label


class TrayChip(QPushButton):
    """Homework with no time yet. Drag it onto any hours to give it that time; a click opens it and a
    right-click shows its menu.

    Its words shorten to the room it has, with the whole title in its tooltip, rather than running
    off the edge of a narrow tray or large text. The title shortens first: the length is the number
    the chip is for."""

    def __init__(self, hand: Hand, waiting: Waiting, parent: QWidget | None = None) -> None:
        self._title = waiting.title
        self._length = f" · {length_label(waiting.minutes)}"
        self._words = f"{waiting.title}{self._length}"
        super().__init__(self._words, parent)
        self.hand = hand
        self.block_id = waiting.block_id
        self.held = Held(Gesture.PLACE, waiting.title, waiting.minutes, waiting.block_id)
        self.setProperty("block_id", waiting.block_id)
        self.setProperty("tray", True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAccessibleName(self._words)
        self.setToolTip(f"{self._words}. Drag onto the hours to give it a time, or click to open it.")

    def sizeHint(self) -> QSize:  # noqa: N802
        # As wide as the whole words, whatever is shown now, so a wider tray shows them again.
        shown = self.text()
        hint = super().sizeHint()
        fonts = self.fontMetrics()
        # Two pixels over: text is measured in whole pixels but laid out in fractions of one.
        return QSize(
            hint.width() - fonts.horizontalAdvance(shown) + fonts.horizontalAdvance(self._words) + 2,
            hint.height(),
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        fonts = self.fontMetrics()
        chrome = super().sizeHint().width() - fonts.horizontalAdvance(self.text())
        room = max(self.width() - chrome, 0)
        fitted = fonts.elidedText(self._words, Qt.TextElideMode.ElideRight, room)
        if fitted != self._words:
            title = fonts.elidedText(
                self._title, Qt.TextElideMode.ElideRight, room - fonts.horizontalAdvance(self._length)
            )
            if title.strip("…"):
                fitted = title + self._length
        if fitted != self.text():
            self.setText(fitted)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        # Not passed on: a press may be the start of a drag, so the click waits for the release.
        self.hand.press(self, self.held, event.globalPosition().toPoint(), tap=self.click)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        event.accept()
        # It has no day until it is given a time.
        self.hand.ask_menu(self.block_id, -1, event.globalPos())
