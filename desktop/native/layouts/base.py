"""What every layout shares: the signals it may raise, and one way of being told about the week.

A layout is presentation only. It is handed a Scene and draws it; when the student wants something
done it says so with a signal, and the window answers with the behaviour it already has. No layout
adds homework, plans, or finishes anything by itself, so there is one planner, not eight.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLayout, QPushButton, QScrollArea, QWidget
from shiboken6 import isValid

from desktop.native.calendar import CATEGORIES
from desktop.native.hours.hand import Hand, is_date_surface, is_surface
from desktop.native.hours.hand import Verdict as HandVerdict
from desktop.native.hours.zoom import HoursScroll
from desktop.native.icons import tint
from desktop.native.look import category_paint, luminance
from desktop.native.weekmodel import Occurrence, WeekModel


@dataclass(frozen=True)
class Scene:
    """Everything a layout needs to draw. `today` is None when the week on screen is not this week."""

    week: WeekModel
    today: int | None
    minute: int
    options: dict[str, str] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    scale: float = 1.0
    surface: str = "week"
    month: dict | None = None
    iso_day: str = ""
    dirty: bool = False
    # Weeks other than this one that the student changed and left unsaved, by their Monday.
    unsaved_weeks: Mapping[str, WeekModel] = field(default_factory=dict)
    # The focus timer: "" when none runs, else "focusing", "paused" or "break".
    focus: str = ""
    today_iso: str = ""

    def px(self, size: float) -> int:
        """A size in pixels that follows the student's Text size knob."""
        return max(1, round(size * self.scale))


def empty(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget, inner = item.widget(), item.layout()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif inner is not None:
            empty(inner)


def base_sheet(name: str, tokens: dict[str, str]) -> str:
    """Undo what the app's stylesheet gives every frame, label and button, so a design starts clean.

    QLabel is a QFrame, so the label rule has to come after the frame rule.
    """
    return (
        f"#{name} {{ background: {tokens['bg']}; color: {tokens['bg_ink']}; }}"
        f"#{name} QFrame {{ background: transparent; color: {tokens['text']}; border: none;"
        " padding: 0; border-radius: 0; }"
        f"#{name} QLabel {{ background: transparent; color: {tokens['bg_ink']}; border: none; padding: 0; }}"
    )


def rules(name: str, entries: dict[str, str]) -> str:
    """Design rules, each prefixed with the view's own id.

    Without the prefix `#oneLabel` loses to the reset's `#layoutOne QLabel`, which is an id and a type,
    and the accent colour silently turned white. Every selector in a comma list gets the prefix: with
    only the first one prefixed, the second label of a shared rule went back to the reset's colour.
    """
    return "".join(
        ", ".join(f"#{name} {part.strip()}" for part in selector.split(",")) + f" {{ {body} }}"
        for selector, body in entries.items()
    )


def css(**properties: object) -> str:
    """`css(font_size="13px", color=ink)` is `font-size: 13px; color: ...;`. It keeps a design's rules
    one property to a line instead of one long string."""
    return " ".join(f"{name.replace('_', '-')}: {value};" for name, value in properties.items())


def label(text: str, name: str, *, wrap: bool = False) -> QLabel:
    made = QLabel(text)
    made.setObjectName(name)
    made.setWordWrap(wrap)
    made.setTextFormat(Qt.TextFormat.PlainText)
    return made


def button(text: str, name: str, kind: str = "") -> QPushButton:
    made = QPushButton(text)
    made.setObjectName(name)
    made.setCursor(Qt.CursorShape.PointingHandCursor)
    if kind:
        made.setProperty("kind", kind)
    return made


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def mark_of(category: str) -> str:
    """A category's strong colour, the one the web client paints with."""
    return (CATEGORIES.get(category) or {}).get("mark") or "#94a3b8"


def family(tokens: dict[str, str]) -> str:
    """Light or dark, read from the page, since a colourway names no family of its own."""
    return "dark" if luminance(tokens["bg"]) < 0.2 else "light"


def family_fill(category: str, tokens: dict[str, str]) -> str:
    """A category's fill in the one family (decision 9 of 0.17) on a design's cards: pale on light
    ones, its tone sunk into dark ones. Lightening or darkening the mark, as designs did, turned the
    darker homework mark into a neon red and a dark look's blocks into ink under dark words."""
    family = "dark" if luminance(tokens["surface"]) < 0.2 else "light"
    return category_paint(category, {"family": family, "panel": tokens["surface"]})[0] or tokens["surface"]


def short_length(minutes: int) -> str:
    """A length where room is short: "1h 30m", "45 min", "2h". Spaces around h made "2 h 15" look
    like a time of day."""
    hours, rest = divmod(max(minutes, 0), 60)
    if not hours:
        return f"{rest} min"
    return f"{hours}h {rest}m" if rest else f"{hours}h"


def free_stretches(items: Sequence[Occurrence], start: int, end: int) -> list[tuple[int, int]]:
    """The stretches from `start` to `end` that nothing still to do takes."""
    free, at = [], start
    for item in sorted(items, key=lambda entry: entry.start):
        if not item.live or item.end <= at or item.start >= end:
            continue
        if item.start > at:
            free.append((at, item.start))
        at = max(at, item.end)
    if at < end:
        free.append((at, end))
    return free


def work_left(scene: Scene) -> int:
    """Placed homework minutes still ahead today. Running late is only offered while there are some."""
    if scene.today is None:
        return 0
    total = 0
    for item in scene.week.on_day(scene.today):
        if item.work and item.live and item.end > scene.minute:
            total += item.end - max(item.start, scene.minute)
    return total


# Mission control wanted 1220 pixels, Clay deck 1148 and Bento 1130. Below this a design gives up a
# column rather than making the student scroll sideways to reach Run plan.
NARROW_WIDTH = 1150


def _refuse_all(block_id: str, from_day: int, span: object) -> HandVerdict:
    return HandVerdict(False, "")


class LayoutView(QWidget):
    add_requested = Signal(str)
    plan_requested = Signal()
    block_activated = Signal(str)
    # The whole homework, not one session: that is the only kind of finishing the product has.
    finished_requested = Signal(str)
    focus_requested = Signal(str, int)
    late_requested = Signal()
    my_day_requested = Signal()
    back_requested = Signal()
    day_activated = Signal(str)
    watched_day_changed = Signal(str)
    # The app's own menu, opening up from this point on the screen, as Retro desktop's Start asks.
    menu_requested = Signal(QPoint)
    # A level the student chose on hours this design made, to remember: the scale's key and pixels an hour.
    zoomed = Signal(str, int)

    layout_id = ""

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("layout" + self.layout_id.title())
        # The window's one pointer. Hours a design draws take it, and bring tracks and paint only: no
        # thresholds, snapping, judging or saving of their own. A picture of a design, drawn with no
        # window, gets one that refuses everything and belongs to the view, so nothing outlives it.
        self.hand = hand if hand is not None else Hand(_refuse_all, self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._scene: Scene | None = None
        self._was_cramped: bool | None = None
        self._dragging = False
        self._held: Scene | None = None
        # The levels this device chose, by scale. The window hands over its own and keeps it current, so
        # hours made on a later render open where the student left them. A picture has none.
        self.remembered_zoom: Mapping[str, int] = {}
        # The hours made last for each scale. Timeline and Bento make theirs again for a new text size,
        # and the new ones take over where the student left each week and day.
        self._made_hours: dict[str, HoursScroll] = {}

    @property
    def scene(self) -> Scene | None:
        return self._scene

    def show_week(self, scene: Scene) -> None:
        if self._dragging:
            # A re-render now would delete what the drag started on, mid-drag. It waits for the drop.
            self._held = scene
            return
        if scene == self._scene:
            return
        week_changed = self._scene is None or scene.week != self._scene.week
        self._scene = scene
        held = QApplication.focusWidget()
        name = held.objectName() if held is not None and held is not self and self.isAncestorOf(held) else ""
        self._was_cramped = self.cramped
        if scene.surface == "month":
            host = self._week_host()
            if host is not None:
                host.hide()
            self.render_month(scene, week_changed)
        else:
            board = getattr(self, "_month_board", None)
            if board is not None:
                board.hide()
            host = self._week_host()
            if host is not None:
                host.show()
            self.render(scene, week_changed)
        again = self.findChild(QWidget, name) if name else None
        if again is not None:
            again.setFocus()

    def keep_zoom(self, scroll: HoursScroll) -> HoursScroll:
        """Hours that open at the level this device last chose for them, and report a new one. A
        design passes every `HoursScroll` it makes through this, where it makes it."""
        scroll.restore(self.remembered_zoom)
        scroll.zoomed.connect(self.zoomed)
        before = self._made_hours.get(scroll.scale.key)
        if before is not None and before is not scroll and isValid(before):
            scroll.take_places(before)
        self._made_hours[scroll.scale.key] = scroll
        return scroll

    def hours_surfaces(self) -> list[QWidget]:
        """Every surface of hours this design shows now, in reading order. The rig and the tests find
        days and times through these; a design with a different order says so here."""
        return [widget for widget in self.findChildren(QWidget) if is_surface(widget) and widget.isVisible()]

    def month_surfaces(self) -> list[QWidget]:
        """Every month this design shows now: what the rig carries chips across."""
        found = self.findChildren(QWidget)
        return [widget for widget in found if is_date_surface(widget) and widget.isVisible()]

    def hold(self, holding: bool) -> None:
        """While the pointer holds something, a new scene waits: a re-render would delete what the
        press started on. Letting go shows the last scene that arrived."""
        self._dragging = holding
        if not holding:
            held, self._held = self._held, None
            if held is not None:
                self.show_week(held)

    def bottom_inset(self) -> int:
        """Pixels of this design's own bottom edge taken by chrome, such as Retro's taskbar. A notice
        placed over the design keeps clear of them."""
        return 0

    @property
    def cramped(self) -> bool:
        """Too narrow for this design's full arrangement. Measured on the view, not the window."""
        return 0 < self.width() < NARROW_WIDTH

    def _week_host(self) -> QWidget | None:
        """The week surface to put away when Month is on, so it cannot show through the calendar.

        The first widget in the view's own layout is that surface. A layout that keeps a taskbar or
        extra chrome wraps both in one child so Month hides the week, not one panel named `_board`.
        """
        manager = self.layout()
        if manager is None:
            return None
        for index in range(manager.count()):
            widget = manager.itemAt(index).widget()
            if widget is not None:
                return widget
        return None

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        board = getattr(self, "_month_board", None)
        if board is not None and board.isVisible():
            board.setGeometry(self.rect())
        # Only when the answer changes, so an ordinary resize does not rebuild the whole view.
        if self._scene is not None and self.cramped != self._was_cramped:
            self._was_cramped = self.cramped
            if self._scene.surface == "month":
                self.render_month(self._scene, False)
            else:
                self.render(self._scene, False)

    def render(self, scene: Scene, week_changed: bool) -> None:
        raise NotImplementedError

    def watched_date(self) -> str | None:
        scene = self._scene
        if scene is None or scene.today is None:
            return None
        return scene.week.date_of(scene.today).isoformat()

    def render_month(self, scene: Scene, week_changed: bool) -> None:
        """A chip calendar in this design's colours. Retro and Mission keep this; they only paint."""
        from desktop.native.hours.month import MonthGrid

        board = getattr(self, "_month_board", None)
        if board is None:
            board = MonthGrid(self, hand=self.hand)
            board.setObjectName("layoutMonthBoard")
            board.day_activated.connect(self.day_activated.emit)
            self._month_board = board
        board.set_tokens(scene.tokens)
        board.set_unsaved(scene.unsaved_weeks)
        board.set_week(scene.week)
        board.set_month(scene.month, scene.dirty, scene.today_iso or None)
        opened = ((scene.month or {}).get("month"), scene.iso_day)
        if scene.month and scene.iso_day and opened != getattr(self, "_month_revealed", None):
            # Once per month opened, and after the board has its size: after that it stays wherever
            # the student scrolled it, through saves and refreshes.
            self._month_revealed = opened
            QTimer.singleShot(0, lambda: board.reveal(scene.iso_day))
        board.setGeometry(self.rect())
        board.show()
        board.raise_()


DAY_ICONS = {"Finished": "check", "Focus": "timer", "Late": "clock", "Back": "chevron-left"}


def day_buttons(view: LayoutView, scene: Scene, item: Occurrence | None, prefix: str) -> list[QPushButton]:
    """What a student does while living the day, written once for every day screen: finish the
    homework, start focus, say they are running late, go back to planning. One is filled, the step
    this minute is for: Homework finished, or else Running late."""
    made = []
    if scene.options.get("actions") != "hide":
        if item is not None and item.work and item.assignment_id:
            finished = button("Homework finished", f"{prefix}Finished", "main")
            finished.clicked.connect(
                lambda _=False, key=item.assignment_id: view.finished_requested.emit(key)
            )
            focus = button("Start focus", f"{prefix}Focus")
            focus.clicked.connect(
                lambda _=False, entry=item: view.focus_requested.emit(entry.block_id, entry.day)
            )
            made += [finished, focus]
        if work_left(scene):
            late = button("Running late", f"{prefix}Late", "" if made else "main")
            late.clicked.connect(view.late_requested.emit)
            made.append(late)
    back = button("Back to planning", f"{prefix}Back")
    back.clicked.connect(view.back_requested.emit)
    made.append(back)
    for entry in made:
        tint(entry, DAY_ICONS[entry.objectName().removeprefix(prefix)], gap=scene.px(4))
    return made


def plan_buttons(view: LayoutView, prefix: str, add_words: str) -> list[QPushButton]:
    """Add homework, drawn as a design's second button: the top bar's Add is the one filled action
    in every layout since 0.16, and Plan my homework and My day live there too."""
    add = button(add_words, f"{prefix}Add")
    add.clicked.connect(lambda _=False: view.add_requested.emit(""))
    return [add]


def scrolling(content: QWidget, name: str) -> QScrollArea:
    """A main view shares the window with the planning controls and gets about half its height, so
    whatever does not fit scrolls instead of being cut off."""
    area = QScrollArea()
    area.setObjectName(name)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(content)
    return area
