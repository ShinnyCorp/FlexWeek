"""Month, as Daily Scheduler draws it, and one thing more: a block can be carried to another date.

Daily Scheduler's month is one painted grid. Each date shows its day number and its events as chips
that start with their time ("09:00 History essay"); what does not fit becomes "+N more"; a click
anywhere on a date opens that day. FlexWeek draws the same, in weeks that start on Monday, with the
homework due that day as "Due" chips first.

A chip with a time can also be carried: it is picked up by the one `Hand` as a date move, the hand
asks the window whether the block can go on the date under the pointer, and the date shows the
answer while the chip is held. Letting go reports a `MoveDate`; the window saves it. A deadline chip
is not carried: moving a deadline is editing the homework.

Today's app and every design show this grid through `MonthGrid`; a design dresses it with its
colour tokens.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from backend.models import due_is_timed
from desktop.native.calendar import CATEGORIES, DAYS
from desktop.native.hours.geometry import Span
from desktop.native.hours.hand import Gesture, Hand, Held, Verdict
from desktop.native.look import resolved_palette
from desktop.native.weekmodel import WeekModel, clock_label, hhmm_text

# The row of day names, kept above the dates while they scroll.
HEADER = 26
# The fewest chips a date always has room for; past them the month scrolls rather than squeezing.
LEAST_CHIPS = 2
FALLBACK_MARK = "#94a3b8"


@dataclass(frozen=True)
class MonthChip:
    """One line in a date: a block at its time, or homework due that day."""

    key: str
    title: str
    category: str
    block_id: str | None = None
    start: int | None = None
    minutes: int = 0
    due: bool = False
    due_time: str | None = None
    done: bool = False

    @property
    def carried(self) -> bool:
        """A block with a time can be carried to another date. A deadline cannot."""
        return self.block_id is not None and self.start is not None and not self.due

    @property
    def words(self) -> str:
        if self.due:
            return f"Due {hhmm_text(self.due_time)} {self.title}" if self.due_time else f"Due {self.title}"
        return f"{clock_label(self.start or 0)} {self.title}"


@dataclass(frozen=True)
class MonthCell:
    iso: str
    in_month: bool
    today: bool
    chips: tuple[MonthChip, ...]

    @property
    def day_number(self) -> int:
        return int(self.iso[8:])


def month_cells(snapshot: dict | None, weeks: Mapping[str, WeekModel], today_iso: str) -> list[MonthCell]:
    """The dates of a month reply, each with its chips. `weeks` are the weeks the student has now,
    saved or not, by their Monday: a date in one of them is read from it; any other date from what
    the reply says is on it."""
    if not snapshot:
        return []
    deadlines: dict[str, dict] = {}
    for item in list(snapshot.get("deadlines") or []) + list(snapshot.get("overdue") or []):
        if item.get("id"):
            deadlines[str(item["id"])] = item
    open_days: dict[str, tuple] = {}
    for week_start, week in weeks.items():
        monday = date.fromisoformat(week_start)
        for offset in range(7):
            day_iso = (monday + timedelta(days=offset)).isoformat()
            open_days[day_iso] = tuple(item for item in week.occurrences if item.day == offset)
    cells = []
    for day in snapshot.get("days") or []:
        iso = str(day["date"])
        chips: list[MonthChip] = []
        for aid in day.get("due_ids") or []:
            item = deadlines.get(str(aid), {"id": aid, "title": aid})
            due = str(item.get("due") or "")
            chips.append(
                MonthChip(
                    f"due:{aid}",
                    str(item.get("title") or aid),
                    str(item.get("category") or "assignments"),
                    due=True,
                    due_time=due[11:16] if due and due_is_timed(due) else None,
                    done=bool(item.get("completed")),
                )
            )
        blocks: list[MonthChip] = []
        if iso in open_days:
            for item in open_days[iso]:
                blocks.append(
                    MonthChip(
                        f"block:{item.block_id}",
                        item.title,
                        item.category,
                        block_id=item.block_id,
                        start=item.start,
                        minutes=item.end - item.start,
                        done=item.done,
                    )
                )
        else:
            for item in day.get("blocks") or []:
                start = str(item.get("start") or "")
                if len(start) != 5:
                    continue
                blocks.append(
                    MonthChip(
                        f"block:{item['id']}",
                        str(item.get("title") or "Untitled"),
                        str(item.get("category") or ""),
                        block_id=str(item["id"]),
                        start=int(start[:2]) * 60 + int(start[3:]),
                        minutes=int(item.get("duration_min") or 0),
                        done=bool(item.get("completed")),
                    )
                )
        blocks.sort(key=lambda chip: (chip.start or 0, chip.title))
        cells.append(MonthCell(iso, bool(day.get("in_month")), iso == today_iso, tuple(chips + blocks)))
    return cells


class MonthPainter:
    """How the month looks. A design gives its own colours; the shapes are Daily Scheduler's."""

    def __init__(self, colours: dict[str, str]) -> None:
        self.colours = {
            "window": "#ffffff",
            "text": "#0f172a",
            "muted": "#64748b",
            "panel": "#ffffff",
            "hairline": "#e2e8f0",
            "accent": "#2563eb",
            "accent_ink": "#ffffff",
            "error": "#dc2626",
            **{key: value for key, value in colours.items() if isinstance(value, str)},
        }

    def c(self, name: str) -> QColor:
        return QColor(self.colours[name])

    def cell(self, painter: QPainter, box: QRectF, cell: MonthCell) -> None:
        painter.fillRect(box, self.c("panel") if cell.in_month else self.c("window"))
        painter.setPen(QPen(self.c("hairline"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)

    def day_number(self, painter: QPainter, box: QRectF, cell: MonthCell) -> None:
        side = max(22.0, QFontMetrics(painter.font()).height() + 4)
        spot = QRectF(box.left() + 5, box.top() + 3, side, side)
        if cell.today:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.c("accent"))
            painter.drawEllipse(spot)
            painter.setPen(self.c("accent_ink"))
        else:
            painter.setPen(self.c("text") if cell.in_month else self.c("muted"))
        painter.drawText(spot, Qt.AlignmentFlag.AlignCenter, str(cell.day_number))

    def chip(self, painter: QPainter, box: QRectF, chip: MonthChip, faded: bool, held: bool) -> None:
        mark = QColor((CATEGORIES.get(chip.category) or {}).get("mark") or FALLBACK_MARK)
        fill = QColor(mark)
        fill.setAlpha(24 if chip.due else 60)
        ink = self.c("text")
        if faded or chip.done or held:
            fill.setAlpha(fill.alpha() // 2)
            ink.setAlpha(120)
        painter.setPen(QPen(mark, 1) if chip.due else Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(box, 4, 4)
        painter.setPen(ink)
        room = box.adjusted(5, 0, -3, 0)
        words = QFontMetrics(painter.font()).elidedText(
            chip.words, Qt.TextElideMode.ElideRight, int(room.width())
        )
        painter.drawText(room, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, words)

    def more(self, painter: QPainter, box: QRectF, count: int) -> None:
        painter.setPen(self.c("muted"))
        painter.drawText(box.adjusted(8, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, f"+{count} more")

    def target(self, painter: QPainter, box: QRectF, verdict: Verdict | None) -> None:
        refused = verdict is not None and not verdict.ok
        painter.setPen(QPen(self.c("error" if refused else "accent"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box.adjusted(1, 1, -1, -1))

    def header(self, painter: QPainter, box: QRectF, words: str) -> None:
        painter.setPen(self.c("muted"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, words)


class MonthCanvas(QWidget):
    """The month's dates, painted. A surface the hand carries dates onto (see hand.py)."""

    takes_dates = True
    date_opened = Signal(str)

    def __init__(self, hand: Hand, painter: MonthPainter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monthCanvas")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Month")
        self.hand, self.painter = hand, painter
        self.cells: list[MonthCell] = []
        # The Monday of the week the window has open: only its blocks have a menu, since the same id
        # can stand for a block on another week, such as School.
        self.open_week: str | None = None
        self._pressed: str | None = None
        hand.preview_changed.connect(self.update)

    def set_cells(self, cells: list[MonthCell]) -> None:
        self.cells = cells
        self.setMinimumHeight(self.rows() * self.least_row())
        self.setAccessibleDescription(
            "Click a date to open it. Drag a block with a time to another date to move it there."
        )
        self.update()

    def set_painter(self, painter: MonthPainter) -> None:
        self.painter = painter
        self.update()

    # Where things are

    def rows(self) -> int:
        return max(1, (len(self.cells) + 6) // 7)

    def _small(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(max(font.pointSizeF() * 0.86, 7))
        return font

    def chip_height(self) -> float:
        return QFontMetrics(self._small()).height() + 2

    def pitch(self) -> float:
        return self.chip_height() + 3

    def number_height(self) -> float:
        return max(27.0, QFontMetrics(self.font()).height() + 11)

    def least_row(self) -> int:
        return round(self.number_height() + LEAST_CHIPS * self.pitch() + self.pitch() + 4)

    def cell_rect(self, index: int) -> QRectF:
        row, column = divmod(index, 7)
        wide = self.width() / 7
        tall = self.height() / self.rows()
        return QRectF(column * wide, row * tall, wide, tall)

    def index_of(self, iso: str) -> int | None:
        return next((at for at, cell in enumerate(self.cells) if cell.iso == iso), None)

    def date_at(self, point: QPointF) -> str | None:
        if not self.cells:
            return None
        for at, cell in enumerate(self.cells):
            if self.cell_rect(at).contains(point):
                return cell.iso
        return None

    def chip_boxes(self, index: int) -> tuple[list[tuple[MonthChip, QRectF]], int]:
        """The chips a date shows, each with its box, and how many more did not fit."""
        box = self.cell_rect(index)
        chips = self.cells[index].chips
        room = box.height() - self.number_height() - 2
        fits = max(0, int(room // self.pitch()))
        if len(chips) > fits:
            fits = max(0, fits - 1)
        shown = [
            (
                chip,
                QRectF(
                    box.left() + 4,
                    box.top() + self.number_height() + at * self.pitch(),
                    box.width() - 8,
                    self.chip_height(),
                ),
            )
            for at, chip in enumerate(chips[:fits])
        ]
        return shown, len(chips) - len(shown)

    def _chip_at(self, point: QPointF) -> tuple[MonthCell, MonthChip, QRectF] | None:
        for at, cell in enumerate(self.cells):
            if not self.cell_rect(at).contains(point):
                continue
            for chip, box in self.chip_boxes(at)[0]:
                if box.contains(point):
                    return cell, chip, box
            return None
        return None

    # Painting

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.painter.c("window"))
        held = self.hand.preview_held()
        target = self.hand.month_target if held is not None else None
        for at, cell in enumerate(self.cells):
            box = self.cell_rect(at)
            self.painter.cell(painter, box, cell)
            painter.setFont(self.font())
            self.painter.day_number(painter, box, cell)
            painter.setFont(self._small())
            shown, more = self.chip_boxes(at)
            for chip, chip_box in shown:
                lifted = held is not None and chip.block_id == held.block_id and cell.iso == held.from_iso
                self.painter.chip(painter, chip_box, chip, not cell.in_month, lifted)
            if more:
                last = box.top() + self.number_height() + len(shown) * self.pitch()
                self.painter.more(painter, QRectF(box.left(), last, box.width(), self.chip_height()), more)
            if target == cell.iso:
                self.painter.target(painter, box, self.hand.month_verdict)
        painter.end()

    # Pointer

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        point = event.position()
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        found = self._chip_at(point)
        if found is not None and found[1].carried:
            cell, chip, _box = found
            weekday = date.fromisoformat(cell.iso).weekday()
            start = chip.start or 0
            held = Held(
                Gesture.MOVE_DATE,
                chip.title,
                chip.minutes,
                chip.block_id,
                weekday,
                Span(weekday, start, start + chip.minutes),
                0,
                cell.iso,
            )
            # A chip that is only clicked opens its date, as a click anywhere on a date does.
            self.hand.press(
                self, held, event.globalPosition().toPoint(), tap=lambda: self.date_opened.emit(cell.iso)
            )
            return
        self._pressed = self.date_at(point)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        """A right-click on a block of the open week asks for its menu. A deadline has none."""
        found = self._chip_at(QPointF(event.pos()))
        if found is None or found[1].block_id is None or found[1].due or self.hand.busy:
            event.ignore()
            return
        cell, chip, _box = found
        day = date.fromisoformat(cell.iso)
        if (day - timedelta(days=day.weekday())).isoformat() != self.open_week:
            event.ignore()
            return
        event.accept()
        self.hand.ask_menu(chip.block_id, day.weekday(), event.globalPos())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pressed, self._pressed = self._pressed, None
        if (
            event.button() == Qt.MouseButton.LeftButton
            and pressed
            and pressed == self.date_at(event.position())
        ):
            self.date_opened.emit(pressed)
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.hand.busy:
            return
        found = self._chip_at(event.position())
        carried = found is not None and found[1].carried
        self.setCursor(Qt.CursorShape.OpenHandCursor if carried else Qt.CursorShape.PointingHandCursor)

    # For the rig and the tests, in global coordinates

    def chip_words(self, block_id: str, iso: str) -> str:
        at = self.index_of(iso)
        chip = (
            next((chip for chip in self.cells[at].chips if chip.block_id == block_id), None)
            if at is not None
            else None
        )
        if chip is None:
            raise LookupError(f"no chip for {block_id} on {iso}")
        return chip.words

    def chip_point(self, block_id: str, iso: str) -> QPoint:
        at = self.index_of(iso)
        if at is not None:
            for chip, box in self.chip_boxes(at)[0]:
                if chip.block_id == block_id:
                    return self.mapToGlobal(box.center().toPoint())
        raise LookupError(f"{block_id} is not drawn on {iso}")

    def cell_point(self, iso: str) -> QPoint:
        """A point on the date that is on none of its chips: the middle of the room under them."""
        at = self.index_of(iso)
        if at is None:
            raise LookupError(f"{iso} is not in this month")
        box = self.cell_rect(at)
        shown, more = self.chip_boxes(at)
        used = self.number_height() + (len(shown) + (1 if more else 0)) * self.pitch()
        free = (used + box.height()) / 2 if used < box.height() - 6 else box.height() - 3
        return self.mapToGlobal(QPointF(box.center().x(), box.top() + free).toPoint())

    def reveal(self, iso: str) -> None:
        """Scroll the nearest scroll area so this date is wholly on screen, clear of its edges."""
        at = self.index_of(iso)
        area = self.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if at is None or area is None:
            return
        box = self.cell_rect(at)
        area.ensureVisible(round(box.center().x()), round(box.center().y()), 0, round(box.height() / 2) + 40)


class MonthNames(QWidget):
    """Monday to Sunday over the dates, in the canvas's own colours, kept in place as they scroll."""

    def __init__(self, canvas: MonthCanvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monthNames")
        self.canvas = canvas

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.canvas.painter.c("window"))
        font = QFont(self.canvas._small())
        font.setBold(True)
        painter.setFont(font)
        wide = self.width() / 7
        for column in range(7):
            self.canvas.painter.header(
                painter, QRectF(column * wide, 0, wide, self.height()), DAYS[column].upper()
            )
        painter.end()


class MonthScroll(QScrollArea):
    """The dates scroll; the names above them do not, and are always exactly as wide as the dates."""

    def __init__(self, canvas: MonthCanvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monthScroll")
        self.names = MonthNames(canvas, self)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidget(canvas)
        self.setViewportMargins(0, HEADER, 0, 0)

    def _place(self) -> None:
        port = self.viewport().geometry()
        self.names.setGeometry(port.left(), port.top() - HEADER, port.width(), HEADER)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place()

    def viewportEvent(self, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            self._place()
        return super().viewportEvent(event)


class MonthGrid(QWidget):
    """A month: a note while changes are still saving, the dates, and what is overdue. The window's
    heading already names the month, so the grid does not say it again."""

    day_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monthPageInner")
        layout = QVBoxLayout(self)
        self.warning = QLabel()
        self.warning.setObjectName("monthSavedWarning")
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)
        # A month drawn with no window takes nothing and moves nothing; its hand belongs to it.
        self.hand = (
            hand if hand is not None else Hand(lambda block_id, from_day, span: Verdict(False, ""), self)
        )
        self._palette = resolved_palette("system", False, None)
        self.canvas = MonthCanvas(self.hand, MonthPainter(self._palette))
        self.canvas.date_opened.connect(self.day_activated.emit)
        self.scroll = MonthScroll(self.canvas)
        layout.addWidget(self.scroll, 1)
        self.overdue = QLabel()
        self.overdue.setObjectName("monthOverdue")
        self.overdue.setWordWrap(True)
        layout.addWidget(self.overdue)
        self._week: WeekModel | None = None
        self._unsaved: Mapping[str, WeekModel] = {}
        self._shown: tuple[dict | None, bool] | None = None

    def set_palette(self, palette: dict) -> None:
        self._palette = palette
        self.canvas.set_painter(MonthPainter(palette))
        self.scroll.names.update()

    def set_tokens(self, tokens: dict[str, str]) -> None:
        """A layout's own colours, so Month is not the pack's calendar sitting inside Bento."""
        self.setStyleSheet(
            f"#monthPageInner, #monthScroll {{ background: {tokens['bg']}; color: {tokens['bg_ink']}; }}"
            f"#monthOverdue, #monthSavedWarning {{ color: {tokens['bg_muted']}; }}"
        )
        self.canvas.set_painter(
            MonthPainter(
                {
                    "window": tokens["bg"],
                    "text": tokens["bg_ink"],
                    "muted": tokens["bg_muted"],
                    "panel": tokens["surface"],
                    "hairline": tokens["line"],
                    "accent": tokens["accent"],
                    "accent_ink": tokens.get("accent_ink", "#ffffff"),
                }
            )
        )
        self.scroll.names.update()

    def set_week(self, week: WeekModel | None) -> None:
        """The open week as the student has it now, saved or not."""
        self._week = week
        if self._shown is not None:
            self.set_month(*self._shown)

    def set_unsaved(self, weeks: Mapping[str, WeekModel]) -> None:
        """Weeks the student changed and left without saving, by their Monday, as they have them."""
        self._unsaved = weeks
        if self._shown is not None:
            self.set_month(*self._shown)

    def set_month(self, snapshot: dict | None, dirty: bool) -> None:
        self._shown = (snapshot, dirty)
        if snapshot is None:
            self.canvas.set_cells([])
            self._say(self.warning, "Loading month…")
            self._say(self.overdue, "")
            return
        # Every week is drawn as the student has it, saved or not, so there is no "saved only" to say.
        self._say(self.warning, "")
        weeks = dict(self._unsaved)
        if self._week is not None and self._week.week_start:
            weeks[self._week.week_start] = self._week
        self.canvas.open_week = self._week.week_start if self._week is not None else None
        self.canvas.set_cells(month_cells(snapshot, weeks, date.today().isoformat()))
        overdue = snapshot.get("overdue") or []
        titles = ", ".join(str(item.get("title") or item.get("id", "")) for item in overdue[:8])
        self._say(self.overdue, "Overdue: " + titles if overdue else "")

    @staticmethod
    def _say(label: QLabel, words: str) -> None:
        # An empty line takes no room: the dates have it.
        label.setText(words)
        label.setVisible(bool(words))

    def reveal(self, iso_day: str) -> None:
        """Open the month on the week the student is in, not on its first row."""
        self.canvas.reveal(iso_day)

    def month_surfaces(self) -> list[MonthCanvas]:
        return [self.canvas] if self.canvas.isVisible() else []
