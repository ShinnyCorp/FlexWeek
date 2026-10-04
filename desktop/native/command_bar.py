"""Ctrl+K: one box to add something or go somewhere by typing, instead of hunting through menus.

The bar only lists what can be done and says which one was chosen; the window does it, the same way
its buttons do. It is drawn as decision 21 of 0.17 has it: the window dimmed 40 % behind it, the box a
sheet with the large shadow, and its rows grouped under muted labels (Add, Go to, Settings, Homework), each
with an icon and, where it has one, its key on the right.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from desktop.native import icons
from desktop.native.elevation import lift
from desktop.native.fonts import caption, weighted
from desktop.native.look import mix
from desktop.native.motion import EASE_MS, RISE_PX, appear, distance, glide, settle
from desktop.native.tokens import WEIGHT_STRONG, Shadow
from desktop.native.widgets import overlay_scroll_bars

BAR_WIDTH = 560
BAR_RISE_PX, BAR_RISE_MS = 2 * RISE_PX, EASE_MS + 80
# Room kept under the box when a long list reaches the bottom of the window.
BOTTOM_GAP = 24
ROW_PX = 36
LABEL_PX = 28
PLACEHOLDER = "Type a command or the name of your homework"
NOTHING_MATCHES = "Nothing matches. Try fewer letters."
GROUPS = ("Add", "Go to", "Settings", "Homework")
KEY_ROLE = Qt.ItemDataRole.UserRole
KEYS_ROLE = Qt.ItemDataRole.UserRole + 1


@dataclass(frozen=True)
class Command:
    key: str
    words: str
    tip: str = ""
    group: str = "Go to"
    icon: str = ""
    keys: str = ""


def _rank_in_text(query: str, text: str) -> int | None:
    wanted = " ".join(query.casefold().split())
    if not wanted:
        return 0
    lowered = text.casefold()
    parts = lowered.split()
    if lowered.startswith(wanted):
        return 0
    if any(part.startswith(wanted) for part in parts):
        return 1
    if wanted in lowered:
        return 2
    if "".join(part[0] for part in parts).startswith(wanted.replace(" ", "")):
        return 3
    return None


def match_rank(query: str, words: str, tip: str = "") -> int | None:
    """How well `words` answers what was typed, best first, or None when it does not.

    The whole name starting with it, then a word starting with it, then anywhere in it, then the
    first letters of its words, so "pmh" finds Plan my homework. The tip is checked too, so "look"
    still finds Customise… from its description.
    """
    wanted = " ".join(query.casefold().split())
    if not wanted:
        return 0
    word_rank = _rank_in_text(query, words)
    if word_rank is not None:
        return word_rank
    if tip and len(wanted) >= 3 and wanted in tip.casefold():
        return 2
    return None


def _word_starts(text: str) -> list[int]:
    starts: list[int] = []
    looking = True
    for index, char in enumerate(text):
        if char.isspace():
            looking = True
        elif looking:
            starts.append(index)
            looking = False
    return starts


def match_span(query: str, words: str) -> list[tuple[int, int]]:
    """Where in `words` the typed letters show up, for highlighting in the list.

    Word starts, then a run of letters, then the initials themselves — each initial its own
    span, never one run across words.
    """
    wanted = " ".join(query.casefold().split())
    if not wanted:
        return []
    text = words.casefold()
    if text.startswith(wanted):
        return [(0, len(wanted))]
    starts = _word_starts(text)
    for start in starts:
        part = text[start:].split(None, 1)[0]
        if part.startswith(wanted):
            return [(start, start + len(wanted))]
    if wanted in text:
        start = text.index(wanted)
        return [(start, start + len(wanted))]
    letters = wanted.replace(" ", "")
    initials = "".join(text[start] for start in starts)
    if letters and initials.startswith(letters):
        return [(start, start + 1) for start in starts[: len(letters)]]
    return []


def ranked(query: str, commands: list[Command]) -> list[Command]:
    scored = [
        (rank, index)
        for index, command in enumerate(commands)
        if (rank := match_rank(query, command.words, command.tip)) is not None
    ]
    return [commands[index] for _, index in sorted(scored)]


def grouped(query: str, commands: list[Command]) -> list[tuple[str, list[Command]]]:
    """What matches, under its group. The group holding the best match comes first, so the first row,
    the one Enter runs, is always the best answer; with nothing typed they come in GROUPS order."""
    best: dict[str, int] = {}
    rows: dict[str, list[Command]] = {}
    for command in ranked(query, commands):
        rank = match_rank(query, command.words, command.tip) or 0
        best.setdefault(command.group, rank)
        rows.setdefault(command.group, []).append(command)
    def place(group: str) -> tuple[int, int]:
        return best[group], GROUPS.index(group) if group in GROUPS else len(GROUPS)

    order = sorted(rows, key=place)
    return [(group, rows[group]) for group in order]


# A key hint's cap: its padding beside the letters and above them, and its corners.
CAP_PAD, CAP_RISE, CAP_CORNER = 6, 2, 4


class CommandRow(QStyledItemDelegate):
    """A command drawn as the style draws a row, with its keys on the right as keycaps, as Help draws
    them; a group label drawn small and muted."""

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.muted = "#5b6474"
        self.edge = "#d0d5dd"
        self.text = "#1a1a1a"
        self.accent = "#3d6fc4"
        self.panel = "#ffffff"
        self.query = ""

    def sizeHint(  # noqa: N802
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), ROW_PX if index.data(KEY_ROLE) else LABEL_PX)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        if not index.data(KEY_ROLE):
            painter.save()
            font = weighted(caption(option.font), WEIGHT_STRONG)
            painter.setFont(font)
            painter.setPen(QColor(self.muted))
            words = option.rect.adjusted(8, 4, -8, 0)
            painter.drawText(words, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, index.data())
            painter.restore()
            return
        state = option.state
        row = option.rect
        if state & QStyle.StateFlag.State_Selected:
            painter.fillRect(row, QColor(mix(self.accent, self.panel, 0.14)))
        elif state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(row, QColor(mix(self.accent, self.panel, 0.06)))
        painter.save()
        font = caption(option.font)
        painter.setFont(font)
        label = index.data(Qt.ItemDataRole.DisplayRole) or ""
        spans = match_span(self.query, str(label))
        left = row.left() + 8
        item = None
        parent = self.parent()
        if isinstance(parent, QListWidget):
            item = parent.itemFromIndex(index)
        if item is not None and not item.icon().isNull():
            item.icon().paint(painter, QRect(left, row.center().y() - 8, 16, 16))
            left += 22
        metrics = QFontMetrics(font)
        # Same 56 px the unmatched path keeps clear of the key caps.
        limit = row.right() - 56
        if not spans:
            painter.setPen(QColor(self.text))
            painter.drawText(
                QRect(left, row.top(), max(0, limit - left), row.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
        else:
            pieces: list[tuple[str, str]] = []
            cursor = 0
            for start, end in spans:
                if start > cursor:
                    pieces.append((label[cursor:start], self.text))
                pieces.append((label[start:end], self.accent))
                cursor = end
            if cursor < len(label):
                pieces.append((label[cursor:], self.text))
            x = left
            for piece, colour in pieces:
                if not piece:
                    continue
                painter.setPen(QColor(colour))
                painter.drawText(
                    QRect(x, row.top(), max(0, limit - x), row.height()),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    piece,
                )
                x += metrics.horizontalAdvance(piece)
        painter.restore()
        keys = index.data(KEYS_ROLE)
        if keys:
            self._paint_keys(painter, option.rect, caption(option.font), keys)

    def _paint_keys(self, painter: QPainter, row: QRect, font: QFont, keys: str) -> None:
        """Each key a cap with an edge, right to left from the row's end, "+" plain between them
        (T22 of the 0.17.0 audit: they were plain letters)."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        height = metrics.height() + 2 * CAP_RISE
        top = row.center().y() - height // 2
        right = row.right() - 12
        for position, key in enumerate(reversed(keys.split("+"))):
            if position:
                join = metrics.horizontalAdvance("+") + 6
                painter.setPen(QColor(self.muted))
                painter.drawText(QRect(right - join, top, join, height), Qt.AlignmentFlag.AlignCenter, "+")
                right -= join
            width = max(metrics.horizontalAdvance(key) + 2 * CAP_PAD, height)
            cap = QRectF(right - width + 0.5, top + 0.5, width - 1, height - 1)
            painter.setPen(QPen(QColor(self.edge), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(cap, CAP_CORNER, CAP_CORNER)
            painter.setPen(QColor(self.muted))
            painter.drawText(cap, Qt.AlignmentFlag.AlignCenter, key)
            right -= width
        painter.restore()


class CommandBar(QWidget):
    """Laid over the whole window, dimming it; the box sits in the top third. A click outside the box
    or Esc closes it."""

    chosen = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("commandBar")
        # Over the whole window: a notice said while it is open goes under it (widgets.Toast).
        self.setProperty("covers", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._commands: list[Command] = []
        self._icon_colour = "#5b6474"
        # The window's Animations level: the dimmed window fades in, and the box rises on it.
        self.motion = "normal"
        self.box = QFrame(self)
        self.box.setObjectName("commandBox")
        self.box.setFixedWidth(BAR_WIDTH)
        column = QVBoxLayout(self.box)
        # The box's own padding is the margin; the layout's would double it.
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        self.input = QLineEdit()
        self.input.setObjectName("commandInput")
        self.input.setPlaceholderText(PLACEHOLDER)
        self.input.setAccessibleName("Command bar")
        self.input.textChanged.connect(self._fill)
        self.input.returnPressed.connect(self._run_current)
        self.input.installEventFilter(self)
        self._search = self.input.addAction(
            icons.icon("search", self._icon_colour), QLineEdit.ActionPosition.LeadingPosition
        )
        rule = QFrame()
        rule.setObjectName("commandRule")
        rule.setFixedHeight(1)
        self.list = QListWidget()
        self.list.setObjectName("commandList")
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setIconSize(QSize(16, 16))
        overlay_scroll_bars(self.list)
        self.rows = CommandRow(self.list)
        self.list.setItemDelegate(self.rows)
        self.list.setMouseTracking(True)
        self.list.viewport().setMouseTracking(True)
        self.list.itemClicked.connect(self._run_item)
        self.nothing = QLabel(NOTHING_MATCHES)
        self.nothing.setObjectName("commandNothing")
        for widget in (self.input, rule, self.list, self.nothing):
            column.addWidget(widget)
        parent.installEventFilter(self)
        self.hide()

    def set_look(self, palette: dict, shadow: Shadow | None, dark: bool = False) -> None:
        """The icons and labels in the look's muted colour, and the box's shadow, or none."""
        self._icon_colour = palette["muted"]
        self.rows.muted = palette["muted"]
        self.rows.edge = palette["hairline_strong"]
        self.rows.text = palette["text"]
        self.rows.accent = palette["accent"]
        self.rows.panel = palette["panel"]
        self.list.setStyleSheet(
            "QListWidget::item { background: transparent; border: none; }"
            "QListWidget::item:selected { background: transparent; }"
            "QListWidget::item:hover { background: transparent; }"
        )
        self._search.setIcon(icons.icon("search", self._icon_colour))
        if shadow is None:
            self.box.setGraphicsEffect(None)
        else:
            lift(self.box, shadow, dark)
        if self.isVisible():
            self._fill(self.input.text())

    def open(self, commands: list[Command]) -> None:
        self._commands = commands
        self.input.clear()
        self._fill("")
        self._place()
        self.show()
        self.raise_()
        self.input.setFocus()
        appear(self, self.motion)
        # The box's own effect is its shadow, so it rises by moving (decision 31 of 0.17). At a
        # notice's 8 pixels, over the same time the window dims, the rise was done before it was seen.
        home = self.box.geometry()
        self.box.move(home.topLeft() + QPoint(0, distance(BAR_RISE_PX, self.motion)))
        glide(self.box, home, self.motion, ms=BAR_RISE_MS)

    def close_bar(self) -> None:
        self.hide()
        host = self.parentWidget()
        if host is not None:
            host.setFocus()

    def shown_words(self) -> list[str]:
        """The commands listed, without the group labels."""
        return [item.text() for item in self._items() if item.data(KEY_ROLE)]

    def shown_groups(self) -> list[str]:
        return [item.text() for item in self._items() if not item.data(KEY_ROLE)]

    def _items(self) -> list[QListWidgetItem]:
        return [self.list.item(row) for row in range(self.list.count())]

    def _fill(self, query: str) -> None:
        # Typing lands the box where it belongs, since the list's height sizes it from here on.
        settle(self.box)
        self.rows.query = query
        self.list.clear()
        for group, commands in grouped(query, self._commands):
            label = QListWidgetItem(group)
            label.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(label)
            for command in commands:
                item = QListWidgetItem(command.words)
                item.setData(KEY_ROLE, command.key)
                item.setData(KEYS_ROLE, command.keys)
                if command.icon:
                    item.setIcon(icons.icon(command.icon, self._icon_colour))
                if command.tip:
                    item.setToolTip(command.tip)
                self.list.addItem(item)
        found = len(self.shown_words())
        self.list.setVisible(found > 0)
        self.nothing.setVisible(found == 0)
        if found:
            self._step_to(0, 1)
        self._refit()

    def _refit(self) -> None:
        """Size the list to the current rows and the window, without rebuilding it."""
        if self.shown_words():
            # Every row while the window has room for them, so a list that fits never scrolls; past
            # that, the list scrolls under the thin bar the rest of the app uses.
            height = sum(ROW_PX if item.data(KEY_ROLE) else LABEL_PX for item in self._items())
            self.list.setFixedHeight(min(height, self._room()) + 2 * self.list.frameWidth())
        self.box.adjustSize()
        self._fit_box()

    def _room(self) -> int:
        """How tall the list may be: the window below the box's top, less the field and a gap."""
        host = self.parentWidget()
        if host is None:
            return 10 * ROW_PX
        above = self.input.sizeHint().height() + 2 * self.box.layout().spacing() + 2 * 8 + 1
        return max(4 * ROW_PX, host.height() - self._top() - above - BOTTOM_GAP)

    def _fit_box(self) -> None:
        """Keep the whole box on screen; shrink the list if the window is short."""
        host = self.parentWidget()
        if host is None:
            return
        top = self._top()
        max_bottom = host.height() - BOTTOM_GAP
        box = self.box.geometry()
        if box.bottom() <= max_bottom and box.top() >= 0:
            return
        while box.bottom() > max_bottom and self.list.height() > 4 * ROW_PX:
            self.list.setFixedHeight(self.list.height() - ROW_PX)
            self.box.adjustSize()
            box = self.box.geometry()
        if box.bottom() > max_bottom:
            top = max(0, max_bottom - box.height())
        self.box.move(box.x(), top)

    def _top(self) -> int:
        host = self.parentWidget()
        return max(24, round(host.height() / 6)) if host is not None else 24

    def _place(self) -> None:
        settle(self.box)
        host = self.parentWidget()
        if host is None:
            return
        self.setGeometry(host.rect())
        width = min(BAR_WIDTH, max(host.width() - 48, 240))
        self.box.setFixedWidth(width)
        self.box.adjustSize()
        # A fixed top, so the box grows and shrinks downwards as typing filters the list.
        self.box.move((host.width() - width) // 2, self._top())
        self._refit()

    def _run_item(self, item: QListWidgetItem) -> None:
        key = item.data(KEY_ROLE)
        if not key:
            return
        # Closed first, so a dialog the command opens is not under the dimmed window.
        self.close_bar()
        self.chosen.emit(key)

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item is not None and self.list.isVisible():
            self._run_item(item)

    def _step_to(self, row: int, by: int) -> None:
        """The first command from `row` in the direction `by`, round the list, past the labels."""
        count = self.list.count()
        for _ in range(count):
            row %= count
            if self.list.item(row).data(KEY_ROLE):
                self.list.setCurrentRow(row)
                return
            row += by

    def _step(self, by: int) -> None:
        if self.list.count():
            self._step_to(self.list.currentRow() + by, by)

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
