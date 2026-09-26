"""Ctrl+K: one box to add something or go somewhere by typing, instead of hunting through menus.

The bar only lists what can be done and says which one was chosen; the window does it, the same way
its buttons do.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

BAR_WIDTH = 560
VISIBLE_ROWS = 8
PLACEHOLDER = "Type a command or the name of your homework"
NOTHING_MATCHES = "Nothing matches. Try fewer letters."


@dataclass(frozen=True)
class Command:
    key: str
    words: str
    tip: str = ""


def match_rank(query: str, words: str) -> int | None:
    """How well `words` answers what was typed, best first, or None when it does not.

    The whole name starting with it, then a word starting with it, then anywhere in it, then the
    first letters of its words, so "pmh" finds Plan my homework.
    """
    wanted = " ".join(query.casefold().split())
    if not wanted:
        return 0
    text = words.casefold()
    parts = text.split()
    if text.startswith(wanted):
        return 0
    if any(part.startswith(wanted) for part in parts):
        return 1
    if wanted in text:
        return 2
    if "".join(part[0] for part in parts).startswith(wanted.replace(" ", "")):
        return 3
    return None


def ranked(query: str, commands: list[Command]) -> list[Command]:
    scored = [(rank, index) for index, command in enumerate(commands)
              if (rank := match_rank(query, command.words)) is not None]
    return [commands[index] for _, index in sorted(scored)]


class CommandBar(QWidget):
    """Laid over the whole window, dimming it; the box sits in the top third. A click outside the box
    or Esc closes it."""

    chosen = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("commandBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._commands: list[Command] = []
        self.box = QFrame(self)
        self.box.setObjectName("commandBox")
        self.box.setFixedWidth(BAR_WIDTH)
        column = QVBoxLayout(self.box)
        # The box's own padding is the margin; the layout's would double it.
        column.setContentsMargins(0, 0, 0, 0)
        self.input = QLineEdit()
        self.input.setObjectName("commandInput")
        self.input.setPlaceholderText(PLACEHOLDER)
        self.input.setAccessibleName("Command bar")
        self.input.textChanged.connect(self._fill)
        self.input.returnPressed.connect(self._run_current)
        self.input.installEventFilter(self)
        self.list = QListWidget()
        self.list.setObjectName("commandList")
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(self._run_item)
        self.nothing = QLabel(NOTHING_MATCHES)
        self.nothing.setObjectName("commandNothing")
        for widget in (self.input, self.list, self.nothing):
            column.addWidget(widget)
        parent.installEventFilter(self)
        self.hide()

    def open(self, commands: list[Command]) -> None:
        self._commands = commands
        self.input.clear()
        self._fill("")
        self._place()
        self.show()
        self.raise_()
        self.input.setFocus()

    def close_bar(self) -> None:
        self.hide()
        host = self.parentWidget()
        if host is not None:
            host.setFocus()

    def shown_words(self) -> list[str]:
        return [self.list.item(row).text() for row in range(self.list.count())]

    def _fill(self, query: str) -> None:
        self.list.clear()
        for command in ranked(query, self._commands):
            item = QListWidgetItem(command.words)
            item.setData(Qt.ItemDataRole.UserRole, command.key)
            if command.tip:
                item.setToolTip(command.tip)
            self.list.addItem(item)
        found = self.list.count()
        self.list.setVisible(found > 0)
        self.nothing.setVisible(found == 0)
        if found:
            self.list.setCurrentRow(0)
            rows = min(found, VISIBLE_ROWS)
            self.list.setFixedHeight(rows * self.list.sizeHintForRow(0) + 2 * self.list.frameWidth())
        self.box.adjustSize()

    def _place(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        self.setGeometry(host.rect())
        width = min(BAR_WIDTH, max(host.width() - 48, 240))
        self.box.setFixedWidth(width)
        self.box.adjustSize()
        # A fixed top, so the box grows and shrinks downwards as typing filters the list.
        self.box.move((host.width() - width) // 2, max(24, round(host.height() / 6)))

    def _run_item(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        # Closed first, so a dialog the command opens is not under the dimmed window.
        self.close_bar()
        self.chosen.emit(key)

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item is not None and self.list.isVisible():
            self._run_item(item)

    def _step(self, by: int) -> None:
        count = self.list.count()
        if count:
            self.list.setCurrentRow((self.list.currentRow() + by) % count)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize and watched is self.parentWidget() and self.isVisible():
            self._place()
        if watched is self.input and event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.close_bar()
                return True
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._step(1 if key == Qt.Key.Key_Down else -1)
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.box.geometry().contains(event.position().toPoint()):
            self.close_bar()
            return
        super().mousePressEvent(event)
