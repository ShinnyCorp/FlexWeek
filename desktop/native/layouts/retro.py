"""Retro desktop: Windows 98 as it was drawn (0.17's Windows 98, faithful).

A desktop in the colourway's teal, or the look's accent under Match my look, with icons down its left
and three windows on it: Week.exe holds the hours, deadlines.txt is Notepad with the homework still to
do, and Up next is a dialog. A taskbar runs along the foot with Start, a button per window and the
clock. Every window, button and field has Windows 98's two-pixel bevel lit from the top left, and the
title bars run navy to blue with the window's icon and its buttons drawn a pixel at a time. Words are
in Pixelify Sans with VT323's figures, Notepad in VT323. High contrast is Windows 98's own High
Contrast Black, in the look's colours.

The hours are the shared ones, on the window's hand. Homework not placed yet is a line of Notepad,
picked up and dropped on Week.exe; with Notepad closed it waits under the hours instead.

What the desktop draws does what it says, or nothing: a window's buttons minimise, maximise and close
it; a taskbar button brings its window forward, or puts away the one in front; the Week.exe and
deadlines.txt icons open theirs; Start opens the app's own menu. The menu bars, the other icons, the
tray's bell and the dialog's question mark are pictures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import (
    QAbstractAnimation,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from backend.models import due_is_timed, due_sort_key
from desktop.native import icons
from desktop.native.calendar import CATEGORIES, DAY_FULL, DAYS, category_title
from desktop.native.fonts import at_scale, load_fonts, time_font, weighted
from desktop.native.hours.canvas import (
    EDGE_WIDTH,
    TEXT_TOP,
    BlockPainter,
    Drawn,
    HoursCanvas,
    Started,
    fit_lines,
)
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.classic import open_hours
from desktop.native.hours.geometry import FIRST, LAST, Axis, LinearTrack
from desktop.native.hours.hand import Hand
from desktop.native.hours.zoom import HoursScroll, Scale
from desktop.native.layouts.base import (
    LayoutView,
    Scene,
    base_sheet,
    css,
    empty,
    family,
    free_stretches,
    label,
    rules,
    scrolling,
    short_length,
)
from desktop.native.layouts.colourways import RETRO
from desktop.native.look import AA_TEXT, category_paint, look_measures, type_sizes
from desktop.native.motion import app_level, appear, between, duration, moves
from desktop.native.reuse import MONTHS, planner_title
from desktop.native.tokens import (
    WEIGHT_REGULAR,
    WEIGHT_STRONG,
    contrast,
    fit_lightness,
    luminance,
    mix,
    mix_oklab,
)
from desktop.native.weekmodel import (
    HOMEWORK,
    Occurrence,
    Waiting,
    WeekModel,
    clock_label,
    hhmm_text,
    length_label,
)

# The mock-up's 08:00 to 22:00 fills Week.exe at 40 pixels an hour, on the week and on Day.
WEEK_SCALE = Scale("retro.week", (32, 40, 56, 72, 96), 40)
DAY_SCALE = Scale("retro.day", (32, 40, 56, 72, 96, 128), 40)
GUTTER = 48
PAD = 10
# The desktop as the mock-up lays it out on its 1280-pixel stage: windows 12 in from its edges and 16
# apart, Week.exe right of the icons, Notepad and the dialog SIDE wide on the right.
STAGE = 1280
MARGIN, GAP = 12, 16
ICONS_WIDE = 100
SIDE, SIDE_LEAST = 380, 280
NOTES_TALL, NOTES_LEAST = 332, 140
NEXT_TALL = 212
WEEK_LEAST = 440
# The icons give way before Week.exe gets narrower than this at normal text, about where a column
# stops having room for "Robotics" whole: they are pictures, and the hours are the week.
WEEK_ROOMY = 640
# A Day narrower than this draws its blocks as the week's, its name over its times.
DAY_WIDE_LEAST = 220
WEBVIEW = 216
ICON_PX = 32
# A scroll bar's width and its buttons' length, and a caption button's size.
BAR = 17
CAP = QSize(20, 18)
# How long Windows 98's zoom rectangle takes to fly a window's title bar out (decision 35 of 0.17).
ZOOM_MS = 200
# Free time shorter than this is not worth listing; the list runs to the end of the mock-up's hours.
FREE_LEAST = 20
FREE_FROM, FREE_UNTIL = 8 * 60, 22 * 60
NOT_PLACED = "not placed yet"
PIXEL_FACE, NOTE_FACE = '"Pixelify Sans"', '"VT323"'


@dataclass(frozen=True)
class Win:
    """A window: its key, its name on the taskbar, its icon and, if other than its name, its title."""

    key: str
    name: str
    icon: str
    title: str = ""


WINDOWS = (
    Win("week", "Week.exe", "calendar-days"),
    Win("notes", "deadlines.txt", "file-text", "deadlines.txt - Notepad"),
    Win("next", "Up next", "bell"),
)
# The desktop's icons: their name, picture and the Scheme colour inside it, and the window each opens.
ICONS = (
    ("Week.exe", "calendar-days", "field", "week"),
    ("deadlines.txt", "file-text", "field", "notes"),
    ("Homework", "folder", "folder", None),
    ("Focus timer", "timer", "field", None),
    ("Recycle Bin", "trash", "face", None),
)
MENUS = {"week": ("File", "Edit", "View", "Homework", "Help"), "notes": ("File", "Edit", "Search", "Help")}


@dataclass(frozen=True)
class Scheme:
    """Windows 98's colours for one scene: its standard greys and white, and the desktop and title
    bars from the colourway or, under Match my look, the look's accent. In High contrast all of it
    comes from the look, as Windows 98's High Contrast Black did."""

    face: str
    light: str
    hi: str
    shadow: str
    dark: str
    field: str
    ink: str
    tip: str
    folder: str
    rule: str
    desk: str
    desk_ink: str
    title: str
    title_end: str
    title_ink: str
    accent: str
    danger: str
    # Which of the category family the blocks are: the light one inside the period white and silver
    # windows, whatever the look, or High contrast's own.
    family: str = "light"

    @property
    def contrast(self) -> bool:
        return self.family == "contrast"


STANDARD = {
    "face": "#c0c0c0",
    "light": "#dfdfdf",
    "hi": "#ffffff",
    "shadow": "#808080",
    "dark": "#0a0a0a",
    "field": "#ffffff",
    "ink": "#000000",
    "tip": "#ffffe1",
    "folder": "#f3d36b",
    "rule": "#e3e3e3",
}


def ink_on(*grounds: str) -> str:
    """Black or white, whichever reads better on the weakest of `grounds`: a title runs over a gradient."""
    return max(("#000000", "#ffffff"), key=lambda ink: min(contrast(ink, ground) for ground in grounds))


def high_contrast(tokens: dict[str, str]) -> bool:
    """White on black is High contrast: no other look writes pure white on a pure black page."""
    return luminance(tokens["bg"]) == 0.0 and luminance(tokens["text"]) == 1.0


def scheme(tokens: dict[str, str]) -> Scheme:
    accent = tokens["accent"]
    if "title" in tokens:
        greys, contrasted = STANDARD, False
        desk, desk_ink = tokens["bg"], tokens["bg_ink"]
        title, title_end, title_ink = tokens["title"], tokens["title_end"], tokens["title_ink"]
    elif high_contrast(tokens):
        contrasted = True
        page, text = tokens["bg"], tokens["text"]
        greys = {
            "face": tokens["surface"],
            "light": mix_oklab(text, tokens["surface"], 0.05),
            "hi": text,
            "shadow": tokens["muted"],
            "dark": text,
            "field": page,
            "ink": text,
            "tip": page,
            "folder": page,
            "rule": mix(text, page, 0.4),
        }
        desk, desk_ink = page, text
        title = title_end = accent
        title_ink = tokens["accent_ink"]
    else:
        greys, contrasted = STANDARD, False
        dark = family(tokens) == "dark"
        desk = mix_oklab(accent, tokens["bg"], 0.42) if dark else accent
        title = mix_oklab(accent, "#000000", 0.82 if dark else 0.72)
        title_end = mix_oklab(accent, "#ffffff", 0.72) if dark else accent
        desk_ink, title_ink = ink_on(desk), ink_on(title, title_end)
    return Scheme(
        **greys,
        desk=desk,
        desk_ink=desk_ink,
        title=title,
        title_end=title_end,
        title_ink=title_ink,
        accent=accent,
        danger=fit_lightness(tokens["danger"], (greys["face"],), AA_TEXT),
        family="contrast" if contrasted else "light",
    )


# Windows 98's bevels, lit from the top left: the Scheme colours of the outer ring's top and left, its
# bottom and right, then the inner ring's, as the mock-up's inset shadows draw them.
BEVELS = {
    "raised": ("hi", "dark", "light", "shadow"),
    "window": ("light", "dark", "hi", "shadow"),
    "sunken": ("shadow", "hi", "dark", "light"),
    "pressed": ("dark", "hi", "shadow", "light"),
    "status": ("shadow", "hi"),
    "block": ("hi", "shadow"),
}
# Glyphs a pixel at a time: where "#" is ink. The caption buttons' are the mock-up's; restore is
# Windows 98's.
GLYPHS = {
    "min": ("######", "######"),
    "max": ("#########", "#########", *("#.......#",) * 6, "#########"),
    "restore": (
        "..######",
        "..######",
        "..#....#",
        "######.#",
        "######.#",
        "#....###",
        "#....#",
        "#....#",
        "######",
    ),
    "close": ("##....##", ".##..##.", "..####..", "...##...", "..####..", ".##..##.", "##....##"),
    "help": (".####.", "##..##", "....##", "...##.", "..##..", "..##..", "......", "..##.."),
    "up": ("...#...", "..###..", ".#####.", "#######"),
    "down": ("#######", ".#####.", "..###..", "...#..."),
}


def frame_in(painter: QPainter, rect: QRect, top_left: QColor, bottom_right: QColor) -> None:
    """A one-pixel ring: its top and left in one colour, its bottom and right over them in another."""
    painter.fillRect(QRect(rect.left(), rect.top(), rect.width(), 1), top_left)
    painter.fillRect(QRect(rect.left(), rect.top(), 1, rect.height()), top_left)
    painter.fillRect(QRect(rect.left(), rect.bottom(), rect.width(), 1), bottom_right)
    painter.fillRect(QRect(rect.right(), rect.top(), 1, rect.height()), bottom_right)


def bevel(painter: QPainter, rect: QRect, colours: Scheme, kind: str) -> None:
    names = BEVELS[kind]
    for ring in range(len(names) // 2):
        light, dark = (QColor(getattr(colours, name)) for name in names[2 * ring : 2 * ring + 2])
        frame_in(painter, rect.adjusted(ring, ring, -ring, -ring), light, dark)


def glyph(painter: QPainter, rect: QRect, rows: tuple[str, ...], ink: QColor) -> None:
    """`rows` in the middle of `rect`, a pixel at a time."""
    left = rect.left() + (rect.width() - max(len(row) for row in rows)) // 2
    top = rect.top() + (rect.height() - len(rows)) // 2
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell == "#":
                painter.fillRect(QRect(left + x, top + y, 1, 1), ink)


def dither(painter: QPainter, rect: QRect, colours: Scheme) -> None:
    """Windows 98's dithered grey: the face and white a pixel apart, as its scroll bar tracks are."""
    painter.fillRect(rect, QColor(colours.face))
    if not colours.contrast:
        painter.fillRect(rect, QBrush(QColor(colours.hi), Qt.BrushStyle.Dense4Pattern))


def _height(px: int) -> int:
    return round((LAST - FIRST) / 60 * px) + 2 * PAD


def _columns(area: QRectF) -> list[LinearTrack]:
    width = area.width() / 7
    return [
        LinearTrack(day, QRectF(area.left() + day * width, area.top() + PAD, width, area.height() - 2 * PAD))
        for day in range(7)
    ]


def arrange(size: QSize, next_tall: int, scale: float) -> tuple[dict[str, QRect], bool]:
    """Where each window sits on a desktop of `size`, as the mock-up lays them out at 1280: Week.exe
    right of the icons, as tall as the desktop, and Notepad over the dialog on the right; and whether
    the icons have room."""
    width, height = size.width(), size.height()
    side = min(SIDE, max(SIDE_LEAST, round(width * SIDE / STAGE)))
    icons_shown = width - ICONS_WIDE - side - 2 * MARGIN >= round(WEEK_ROOMY * scale)
    left = ICONS_WIDE if icons_shown else MARGIN
    week = QRect(left, MARGIN, max(width - left - side - 2 * MARGIN, WEEK_LEAST), height - 2 * MARGIN)
    room = height - 2 * MARGIN - GAP - next_tall
    notes = QRect(
        week.right() + 1 + MARGIN, MARGIN, side, max(min(round(NOTES_TALL * scale), room), NOTES_LEAST)
    )
    below = QRect(notes.left(), notes.bottom() + 1 + GAP, side, next_tall)
    return {"week": week, "notes": notes, "next": below}, icons_shown


@dataclass(frozen=True)
class Deadline:
    """A line of deadlines.txt: homework still to do, how long it takes, and when it is placed."""

    title: str
    length: str
    when: str
    block_id: str
    waiting: Waiting | None = None


@dataclass(frozen=True)
class DueGroup:
    heading: str
    lines: tuple[Deadline, ...]


def unbroken(words: str) -> str:
    """A length that stays on one line where words wrap: never "in 20" at a line's end and "min" after."""
    return words.replace(" ", "\u00a0")


def due_heading(due: str | None, week: WeekModel, today: int | None) -> str:
    """ "Due Sunday 27 September, in 3 days.", as Notepad's first line says it."""
    if not due:
        return "No due date."
    day = date.fromisoformat(due[:10])
    words = f"Due {DAY_FULL[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"
    if due_is_timed(due):
        words += f" at {hhmm_text(due[11:16])}"
    if today is not None:
        gap = (day - week.date_of(today)).days
        words += {0: ", today", 1: ", tomorrow"}.get(
            gap, f", {unbroken(f'in {gap} days')}" if gap > 1 else ", past due"
        )
    return words + "."


def deadlines(week: WeekModel, today: int | None) -> list[DueGroup]:
    """Every homework still to do, placed or not, under its deadline, the soonest first. Placed work
    says when it is placed, in those words, so the time is not read as its deadline; the rest says it
    is not placed yet."""
    groups: dict[str, list[tuple[tuple, Deadline]]] = {}
    for item in week.open_work():
        when = f"placed {DAYS[item.day]} {clock_label(item.start)}"
        line = Deadline(item.title, short_length(item.minutes), when, item.block_id)
        groups.setdefault(item.due or "", []).append(((0, item.day, item.start), line))
    for index, waiting in enumerate(week.waiting):
        line = Deadline(waiting.title, short_length(waiting.minutes), NOT_PLACED, waiting.block_id, waiting)
        groups.setdefault(waiting.due or "", []).append(((1, index, 0), line))
    return [
        DueGroup(
            due_heading(due, week, today), tuple(line for _, line in sorted(lines, key=lambda pair: pair[0]))
        )
        for due, lines in sorted(groups.items(), key=lambda pair: due_sort_key(pair[0] or None))
    ]


def shorten(text: str, chars: int) -> str:
    """`text` in `chars` letters of a monospaced face, given way at a space: "Science fair…"."""
    if len(text) <= chars:
        return text
    kept = ""
    for word in text.split():
        if len(f"{kept} {word}".strip()) + 1 > chars:
            break
        kept = f"{kept} {word}".strip()
    return f"{kept}…" if kept else text[: max(chars - 1, 0)] + "…"


def note_widths(lines: list[Deadline], chars: int) -> tuple[int, int]:
    """Notepad's title and length columns for `chars` letters a line: the titles as wide as the
    widest that leaves room for the rest, so the lengths and times line up."""
    length = max((len(line.length) for line in lines), default=0)
    when = max((len(line.when) for line in lines), default=0)
    title = max((len(line.title) for line in lines), default=0)
    return max(min(title, chars - length - when - 4), 0), length


def note_lines(line: Deadline, widths: tuple[int, int], chars: int) -> list[str]:
    """A homework's line of Notepad; short of room, its length and time go on a line under its title,
    in their columns, and the title shortens at a word only if it must."""
    title, length = widths
    rest = f"{line.length:<{length}}  {line.when}"
    if len(line.title) <= title and title + 2 + len(rest) <= chars:
        return [f"{line.title:<{title}}  {rest}"]
    indent = title + 2 if title + 2 + len(rest) <= chars else 3
    return [shorten(line.title, chars), " " * indent + rest]


@dataclass(frozen=True)
class UpNext:
    """What the Up next dialog says: the name in bold, then when, then what follows."""

    title: str
    line: str
    then: str = ""


def up_next(scene: Scene) -> UpNext:
    if scene.today is None:
        return UpNext("", "This is another week, so nothing is next.")
    ahead = [
        item for item in scene.week.day_queue(scene.today, scene.minute).queue if item.start > scene.minute
    ]
    if not ahead:
        heading, title, line = scene.week.leftover_parts(scene.today)
        if title == heading:
            return UpNext(heading, "")
        return UpNext(title, f"{heading}. {line}.")
    first = ahead[0]
    wait = unbroken(f"in {length_label(first.start - scene.minute)}")
    when = f"starts at {clock_label(first.start)}, {wait}."
    then = f"Then {ahead[1].title} at {clock_label(ahead[1].start)}." if len(ahead) > 1 else ""
    return UpNext(first.title, when, then)


def planned_words(items: tuple[Occurrence, ...], ahead: int | None) -> str:
    """ "9 h 45 min planned, 3 still to come.", or without what is to come on a day that is not today."""
    minutes = sum(item.minutes for item in items if item.work)
    if not minutes:
        return "Nothing planned."
    words = f"{unbroken(length_label(minutes))} planned"
    return f"{words}, {ahead} still to come." if ahead is not None else f"{words}."


def category_minutes(items: tuple[Occurrence, ...]) -> list[tuple[str, int]]:
    """Each category's minutes on a day, in the app's order of categories."""
    totals: dict[str, int] = {}
    for item in items:
        totals[item.category or HOMEWORK] = totals.get(item.category or HOMEWORK, 0) + item.minutes
    known = [key for key in CATEGORIES if key in totals]
    return [(key, totals[key]) for key in known + sorted(set(totals) - set(known))]


def free_from(items: tuple[Occurrence, ...], start: int) -> list[tuple[int, int]]:
    return [(a, b) for a, b in free_stretches(items, start, FREE_UNTIL) if b - a >= FREE_LEAST]


class RetroPainter(BlockPainter):
    """Week.exe's hours: the white field with grey rules, blocks in the category family with a
    three-pixel edge and a one-pixel bevel, and now as a line in the title bar's colour, dotted across
    the other days, with its time on a Windows 98 tooltip in the gutter."""

    now_in_gutter = True
    trims_narrow = True

    def __init__(self, colours: Scheme, *, wide: bool = False) -> None:
        super().__init__(
            {
                "window": colours.field,
                "grid": colours.rule,
                "hairline": colours.rule,
                "rule": colours.rule,
                "accent": colours.accent,
                "accent_ink": ink_on(colours.accent),
                "error": colours.danger,
                "text": colours.ink,
                "muted": colours.ink,
            },
            wide=wide,
        )
        self.scheme = colours
        self.day = wide

    @property
    def measures(self) -> dict:
        # The week's narrow columns say a block's name and start; Day says its length too.
        return {**look_measures(None), "show_lengths": self.wide}

    def background(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(self.scheme.field))

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        colours, area = self.scheme, track.area
        if today:
            painter.fillRect(area, QColor(mix_oklab(colours.shadow, colours.field, 0.09)))
        rule = QColor(colours.rule)
        for minute in range(-(-track.first // 60) * 60, track.last + 1, 60):
            painter.fillRect(
                QRectF(area.left(), round(area.top() + track.offset(minute)), area.width(), 1), rule
            )
        painter.fillRect(QRectF(round(area.left()), area.top(), 1, area.height()), rule)
        if self.now_minute is not None and not self.wide:
            at = round(area.top() + track.offset(self.now_minute))
            pen = QPen(QColor(colours.title), 1)
            pen.setDashPattern([1, 1])
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(pen)
            painter.drawLine(QPointF(area.left(), at), QPointF(area.right(), at))

    def now(self, painter: QPainter, track: LinearTrack, minute: int) -> None:
        area = track.area
        at = round(area.top() + track.offset(minute))
        painter.fillRect(QRectF(area.left(), at - 1, area.width(), 2), QColor(self.scheme.title))

    def hour_labels(
        self,
        painter: QPainter,
        track: LinearTrack,
        room: float,
        every: int = 60,
        visible: QRectF | None = None,
    ) -> None:
        super().hour_labels(painter, track, room, every, visible)
        if self.now_minute is None or track.axis is not Axis.DOWN:
            return
        colours = self.scheme
        font = at_scale(time_font(painter.font()), "caption", self.scale(painter.font()))
        metrics = QFontMetricsF(font)
        words = clock_label(self.now_minute)
        width, height = round(metrics.horizontalAdvance(words)) + 8, max(16, round(metrics.height()) + 2)
        at = track.area.top() + track.offset(self.now_minute)
        tip = QRect(round(track.area.left()) - 3 - width, round(at - height / 2), width, height)
        painter.fillRect(tip, QColor(colours.tip))
        frame_in(painter, tip, QColor(colours.ink), QColor(colours.ink))
        painter.setFont(font)
        painter.setPen(QColor(colours.ink))
        painter.drawText(QRectF(tip), Qt.AlignmentFlag.AlignCenter, words)

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        colours = self.scheme
        fill, mark = category_paint(
            drawn.category or HOMEWORK, {"family": colours.family, "panel": colours.field}
        )
        if drawn.done or drawn.missed:
            fill = colours.light
        return QColor(fill or colours.face), QColor(colours.ink), None, QColor(mark or colours.shadow)

    def fonts(self, base: QFont) -> tuple[QFont, QFont]:
        """The mock-up writes a block's title and its time at the caption size on Day as on the week."""
        scale = self.scale(base)
        return at_scale(base, "caption", scale, WEIGHT_STRONG), at_scale(
            time_font(base), "caption", scale, WEIGHT_REGULAR
        )

    def body(self, painter: QPainter, rect: QRectF, drawn: Drawn) -> None:
        colours = self.scheme
        self.wide = self.day and rect.width() >= DAY_WIDE_LEAST
        fill, _ink, _outline, edge = self.fills(drawn)
        box = QRect(round(rect.left()), round(rect.top()), round(rect.width()), max(round(rect.height()), 1))
        painter.fillRect(box, fill)
        if colours.contrast:
            frame_in(painter, box, edge, edge)
        else:
            bevel(painter, box, colours, "block")
        painter.fillRect(QRect(box.left(), box.top(), EDGE_WIDTH, box.height()), edge)
        if drawn.held or drawn.chosen:
            refused = drawn.verdict is not None and not drawn.verdict.ok
            ring = QColor(colours.danger if refused else colours.accent)
            frame_in(painter, box, ring, ring)
            frame_in(painter, box.adjusted(1, 1, -1, -1), ring, ring)

    def words(
        self,
        painter: QPainter,
        rect: QRectF,
        drawn: Drawn,
        ink: QColor,
        visible: QRectF,
        fill: QColor | None = None,
        edge: QColor | None = None,
    ) -> list[QRectF]:
        shown = drawn if self.wide or drawn.held else Started(**vars(drawn))
        # Words from the block's top edge to its foot, where the shared ones keep 3 pixels and 1 clear:
        # the pixel face's own line height keeps them off the bevel, and at the mock-up's 40 pixels an
        # hour it is what lets a half hour say its name and an hour two lines of it.
        return super().words(painter, rect.adjusted(0, -TEXT_TOP, 0, 1), shown, ink, visible, fill, edge)


class RetroCanvas(HoursCanvas):
    """The week's names sit over the hours in Windows 98 buttons, while the rig can find them."""

    def __init__(self, hand: Hand, painter: RetroPainter, *, week: bool) -> None:
        super().__init__(hand, painter, _columns if week else None, gutter=GUTTER)
        self.day_buttons: dict[int, QWidget] = {}

    def day_name(self, day: int) -> QPoint:
        pick = self.day_buttons.get(day)
        return pick.mapToGlobal(pick.rect().center()) if pick is not None else super().day_name(day)


class Button98(QPushButton):
    """A Windows 98 push button: the face, its two-pixel bevel, pressed in while held, and its words
    and icon. `sunk` keeps it pressed in, as the taskbar button of the window in front; `ring` marks
    the dialog's default button; `dither` is the white-flecked face of that taskbar button."""

    def __init__(
        self,
        text: str,
        name: str,
        colours: Scheme,
        *,
        icon: str = "",
        icon_ink: str = "",
        left: bool = False,
        ring: bool = False,
        underline: int = -1,
    ) -> None:
        super().__init__(text)
        self.setObjectName(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scheme = colours
        self.icon_name, self.icon_ink = icon, icon_ink
        self.left, self.ring, self.underline = left, ring, underline
        self.sunk = self.dither = self.strong = False
        self.fill = ""

    def parts(self) -> list[tuple[str, bool]]:
        """Its words, each part in the strong weight or not."""
        return [(self.text(), self.strong)]

    def _font(self, strong: bool) -> QFont:
        return weighted(self.font(), WEIGHT_STRONG if strong else WEIGHT_REGULAR)

    def _icon_px(self) -> int:
        return round(QFontMetricsF(self.font()).ascent()) + 3

    def _words_width(self) -> float:
        return sum(
            QFontMetricsF(self._font(strong)).horizontalAdvance(words) for words, strong in self.parts()
        )

    def sizeHint(self) -> QSize:  # noqa: N802
        icon = self._icon_px() + 5 if self.icon_name else 0
        tall = QFontMetricsF(self.font()).height() + 10
        return QSize(round(self._words_width() + icon + 24), max(round(tall), 24))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(min(self.sizeHint().width(), 48), self.sizeHint().height())

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        colours = self.scheme
        box = self.rect()
        down = self.isDown() or self.sunk
        painter.fillRect(box, QColor(self.fill or colours.face))
        if self.dither:
            dither(painter, box, colours)
        if self.ring:
            dark = QColor(colours.dark)
            frame_in(painter, box, dark, dark)
            bevel(painter, box.adjusted(1, 1, -1, -1), colours, "pressed" if down else "raised")
        else:
            bevel(painter, box, colours, "pressed" if down else "raised")
        inner = QRectF(box.adjusted(6, 3, -6, -3))
        if self.isDown():
            inner.translate(1, 1)
        icon = self._icon_px() if self.icon_name else 0
        room = inner.width() - (icon + 5 if icon else 0)
        width = min(self._words_width(), room)
        at = (
            inner.left()
            if self.left
            else inner.left() + (inner.width() - width - (icon + 5 if icon else 0)) / 2
        )
        ink = QColor(colours.ink)
        if icon:
            pixmap = icons.pixmap(
                self.icon_name, self.icon_ink or colours.ink, icon, self.devicePixelRatioF(), "2"
            )
            painter.drawPixmap(QPointF(round(at), round(inner.center().y() - icon / 2)), pixmap)
            at += icon + 5
        painter.setPen(ink)
        start = at
        parts = self.parts()
        for index, (words, strong) in enumerate(parts):
            font = self._font(strong)
            metrics = QFontMetricsF(font)
            shown = words
            if index == len(parts) - 1 and at + metrics.horizontalAdvance(words) > inner.right() + 0.5:
                shown = metrics.elidedText(words, Qt.TextElideMode.ElideRight, max(inner.right() - at, 0))
            painter.setFont(font)
            painter.drawText(
                QRectF(at, inner.top(), inner.right() - at, inner.height()),
                Qt.AlignmentFlag.AlignVCenter,
                shown,
            )
            if self.underline >= 0 and index == 0:
                lead = metrics.horizontalAdvance(words[: self.underline])
                wide = metrics.horizontalAdvance(words[self.underline])
                base = round(inner.center().y() + metrics.ascent() / 2 + 2)
                painter.fillRect(QRectF(at + lead, base, wide, 1), ink)
            at += metrics.horizontalAdvance(shown)
        if self.ring or self.hasFocus():
            pen = QPen(ink, 1, Qt.PenStyle.DotLine)
            painter.setPen(pen)
            tall = QFontMetricsF(self.font()).height()
            painter.drawRect(
                QRectF(
                    round(start) - 3.5,
                    round(inner.center().y() - tall / 2) - 0.5,
                    round(at - start) + 6,
                    round(tall) + 1,
                )
            )


class DayHead(Button98):
    """A day's name over its column, "Mon 21" with the date strong; today's pressed in and paler. On
    the week it opens the day; over Day's one column it is only its name. When one of the row has no
    room for its date too, every one says its day alone, "Mon", so the row reads alike."""

    def __init__(self, name: str, colours: Scheme, opens: int | None) -> None:
        super().__init__("", name, colours)
        self.setProperty("role", "head")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        if opens is not None:
            self.setProperty("day_target", opens)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.number = ""
        self.day = 0

    def show_day(self, day: int, number: int, today: bool) -> None:
        self.day, self.number = day, str(number)
        self.setText(f"{DAYS[day]} {number}")
        self.sunk = self.strong = today
        self.fill = self.scheme.light if today else ""
        self.setProperty("chosen", "true" if today else "false")
        self.update()

    def _whole(self) -> list[tuple[str, bool]]:
        return [(self.text().removesuffix(self.number), self.strong), (self.number, True)]

    def _fits(self) -> bool:
        need = sum(
            QFontMetricsF(self._font(strong)).horizontalAdvance(words) for words, strong in self._whole()
        )
        return not self.width() or need <= self.width() - 12

    def parts(self) -> list[tuple[str, bool]]:
        row = self.parentWidget().findChildren(DayHead) if self.parentWidget() is not None else [self]
        return self._whole() if all(head._fits() for head in row) else [(DAYS[self.day], self.strong)]


class Cap(QWidget):
    """A bevelled cell: over the scroll bar beside the day names, or the dialog's question mark,
    which is a picture."""

    def __init__(self, colours: Scheme, rows: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.scheme, self.rows = colours, rows

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self.scheme.face))
        bevel(painter, self.rect(), self.scheme, "raised")
        if self.rows:
            glyph(painter, self.rect(), self.rows, QColor(self.scheme.ink))


class CapButton(QPushButton):
    """A title bar's minimise, maximise or close, its glyph drawn a pixel at a time."""

    def __init__(self, name: str, words: str, colours: Scheme, drawn: str) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setAccessibleName(words)
        self.setToolTip(words)
        self.setFixedSize(CAP)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scheme, self.drawn = colours, drawn

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        box = self.rect()
        painter.fillRect(box, QColor(self.scheme.face))
        bevel(painter, box, self.scheme, "pressed" if self.isDown() else "raised")
        glyph(
            painter,
            box.translated(1, 1) if self.isDown() else box,
            GLYPHS[self.drawn],
            QColor(self.scheme.ink),
        )


class TitleBar(QLabel):
    """A window's title bar: the gradient, its icon and name, and its buttons. Dragging it moves the
    window, kept inside the desktop; a double click maximises it, as Windows 98's did."""

    pressed = Signal()
    doubled = Signal()

    def __init__(self, window: Window98) -> None:
        super().__init__(window.win.title or window.win.name)
        self.setObjectName(f"retroTitle-{window.win.key}")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._window = window
        self._grab: QPoint | None = None
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 3, 0)
        self.row.setSpacing(0)
        self.row.addStretch(1)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, max(24, round(QFontMetricsF(weighted(self.font(), WEIGHT_STRONG)).height()) + 6))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        colours = self._window.scheme
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, QColor(colours.title))
        gradient.setColorAt(1, QColor(colours.title_end))
        painter.fillRect(self.rect(), gradient)
        ink = colours.title_ink
        side = 16
        painter.drawPixmap(
            QPointF(4, (self.height() - side) // 2),
            icons.pixmap(self._window.win.icon, ink, side, self.devicePixelRatioF(), "2"),
        )
        caps = [child for child in self.findChildren(QWidget) if child.isVisible()]
        right = min((child.x() for child in caps), default=self.width()) - 6
        left = 4 + side + 5
        font = weighted(self.font(), WEIGHT_STRONG)
        words = QFontMetricsF(font).elidedText(self.text(), Qt.TextElideMode.ElideRight, max(right - left, 0))
        painter.setFont(font)
        painter.setPen(QColor(ink))
        painter.drawText(
            QRectF(left, 0, max(right - left, 0), self.height()), Qt.AlignmentFlag.AlignVCenter, words
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.pressed.emit()
        if not self._window.maximised:
            self._grab = event.globalPosition().toPoint() - self._window.pos()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._grab is None:
            return
        desk = self._window.parentWidget()
        spot = event.globalPosition().toPoint() - self._grab
        limit_x = max(desk.width() - 60, 0) if desk is not None else spot.x()
        limit_y = max(desk.height() - 30, 0) if desk is not None else spot.y()
        self._window.move(min(max(spot.x(), 0), limit_x), min(max(spot.y(), 0), limit_y))
        self._window.setProperty("moved", True)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._grab = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.doubled.emit()


class Window98(QFrame):
    """A Windows 98 window on the desktop: the face and its bevel, a title bar and what it holds. It
    is made once and kept, so where it was put, whether it is maximised and what is in front last."""

    activated = Signal()

    def __init__(self, win: Win, colours: Scheme) -> None:
        super().__init__()
        self.win, self.scheme = win, colours
        self.setObjectName(f"retroWindow-{win.key}")
        self.setProperty("role", "window")
        self.setProperty("moved", False)
        self.maximised = False
        box = QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(0)
        self.bar = TitleBar(self)
        self.bar.pressed.connect(self.activated.emit)
        box.addWidget(self.bar)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        box.addLayout(self.body, 1)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self.scheme.face))
        bevel(painter, self.rect(), self.scheme, "window")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.activated.emit()
        super().mousePressEvent(event)


class Field(QFrame):
    """A sunken white field: the hours, Notepad's page and the folder's web view."""

    def __init__(self, name: str, colours: Scheme) -> None:
        super().__init__()
        self.setObjectName(name)
        self.scheme = colours

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self.scheme.field))
        bevel(painter, self.rect(), self.scheme, "sunken")


class Cell(QLabel):
    """A status bar's cell: words in a one-pixel sunken frame. Given shorter ways to say them, it says
    the longest that fits its width, rather than letting the frame cut them."""

    def __init__(self, choices: str | tuple[str, ...], name: str, colours: Scheme) -> None:
        self.choices = (choices,) if isinstance(choices, str) else choices
        super().__init__(self.choices[0])
        self.setObjectName(name)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.scheme = colours

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if len(self.choices) > 1:
            room = self.contentsRect().width()
            fits = [words for words in self.choices if self.fontMetrics().horizontalAdvance(words) <= room]
            fitted = fits[0] if fits else self.choices[-1]
            if fitted != self.text():
                self.setText(fitted)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        bevel(painter, self.rect(), self.scheme, "status")


class Well(QFrame):
    """The taskbar's tray, sunk a pixel, with the clock in it."""

    def __init__(self, name: str, colours: Scheme) -> None:
        super().__init__()
        self.setObjectName(name)
        self.scheme = colours

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        bevel(QPainter(self), self.rect(), self.scheme, "status")


class RetroBar(QScrollBar):
    """Windows 98's scroll bar: arrow buttons, a dithered track and a raised thumb, which fills the
    track when there is nothing to scroll, as the mock-up draws Notepad's. The stylesheet gives it
    Windows 98's measures, so where it is pressed is where it is drawn."""

    def __init__(self, name: str, colours: Scheme) -> None:
        super().__init__(Qt.Orientation.Vertical)
        self.setObjectName(name)
        self.setProperty("retro", True)
        self.scheme = colours

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        style = self.style()

        def part(control: QStyle.SubControl) -> QRect:
            return style.subControlRect(QStyle.ComplexControl.CC_ScrollBar, option, control, self)

        painter = QPainter(self)
        colours = self.scheme
        dither(painter, self.rect(), colours)
        if colours.contrast:
            shadow = QColor(colours.shadow)
            frame_in(painter, self.rect(), shadow, shadow)
        held = bool(option.state & QStyle.StateFlag.State_Sunken)
        for control, drawn in (
            (QStyle.SubControl.SC_ScrollBarSubLine, "up"),
            (QStyle.SubControl.SC_ScrollBarAddLine, "down"),
        ):
            box = part(control)
            down = held and bool(option.activeSubControls & control)
            painter.fillRect(box, QColor(colours.face))
            bevel(painter, box, colours, "pressed" if down else "raised")
            glyph(painter, box.translated(1, 1) if down else box, GLYPHS[drawn], QColor(colours.ink))
        movable = self.maximum() > self.minimum()
        thumb = part(
            QStyle.SubControl.SC_ScrollBarSlider if movable else QStyle.SubControl.SC_ScrollBarGroove
        )
        painter.fillRect(thumb, QColor(colours.face))
        bevel(painter, thumb, colours, "raised")


class Mirror(QObject):
    """One scroll bar kept in step with another: Week.exe's stands beside the hours under a cap level
    with the day names, where the hours' own would run up beside the names."""

    def __init__(self, source: QScrollBar, shown: QScrollBar, port: QWidget) -> None:
        super().__init__(shown)
        self.source, self.shown = source, shown
        self._copying = False
        source.rangeChanged.connect(self.sync)
        source.valueChanged.connect(shown.setValue)
        shown.valueChanged.connect(self._moved)
        port.installEventFilter(self)
        self.sync()

    def sync(self, *_: object) -> None:
        """The hours' range, copied. A smaller range cuts the drawn bar's value, and that cut is not
        the student scrolling: written back, it moved the hours before they could keep their place."""
        self._copying = True
        try:
            self.shown.setRange(self.source.minimum(), self.source.maximum())
            self.shown.setPageStep(self.source.pageStep())
            self.shown.setSingleStep(self.source.singleStep())
            self.shown.setValue(self.source.value())
        finally:
            self._copying = False

    def _moved(self, value: int) -> None:
        if not self._copying:
            self.source.setValue(value)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self.sync)
        return False


class Grid(Field):
    """Week.exe's field of hours: the day names over them, and Windows 98's scroll bar beside them."""

    def __init__(self, scroll: HoursScroll, colours: Scheme) -> None:
        super().__init__(f"{scroll.objectName()}Field", colours)
        self.scroll = scroll
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(0)
        row.addWidget(scroll, 1)
        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(0)
        self.cap = Cap(colours)
        self.cap.setFixedWidth(BAR)
        self.bar = RetroBar(f"{scroll.objectName()}Bar", colours)
        side.addWidget(self.cap)
        side.addWidget(self.bar, 1)
        row.addLayout(side)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.buttons.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        Mirror(scroll.verticalScrollBar(), self.bar, scroll.viewport())

    def dress(self, colours: Scheme) -> None:
        self.scheme = self.cap.scheme = self.bar.scheme = colours
        self.fit_cap()
        self.update()

    def fit_cap(self) -> None:
        self.cap.setFixedHeight(max(self.scroll.viewportMargins().top(), 1))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_cap)


class NoteLines:
    """A homework's line of Notepad, in VT323 and as many lines as the page's width gives it (see
    `note_lines`), selected as Notepad selects text while it has the focus or the pointer."""

    line: Deadline
    scheme: Scheme
    lines: list[str]

    def dress(self, line: Deadline, name: str, colours: Scheme) -> None:
        self.setObjectName(name)
        self.setProperty("role", "note")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.line, self.scheme = line, colours
        self.lines = [f"{line.title}  {line.length}  {line.when}"]

    def set_lines(self, lines: list[str]) -> None:
        self.lines = lines
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = QFontMetricsF(self.font())
        wide = max(metrics.horizontalAdvance(line) for line in self.lines)
        return QSize(round(wide) + 2, round(metrics.lineSpacing() * len(self.lines)))

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        metrics = QFontMetricsF(self.font())
        chosen = self.hasFocus() or self.underMouse()
        painter.setFont(self.font())
        for index, words in enumerate(self.lines):
            box = QRectF(
                0, index * metrics.lineSpacing(), metrics.horizontalAdvance(words) + 2, metrics.lineSpacing()
            )
            if chosen:
                painter.fillRect(box, QColor(self.scheme.title))
            painter.setPen(QColor(self.scheme.title_ink if chosen else self.scheme.ink))
            painter.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, words)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.update()


class NoteRow(NoteLines, QPushButton):
    """A placed homework's line of Notepad: a click opens it."""

    def __init__(self, line: Deadline, name: str, colours: Scheme) -> None:
        QPushButton.__init__(self, f"{line.title}  {line.length}  {line.when}")
        self.dress(line, name, colours)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class NoteChip(NoteLines, TrayChip):
    """Homework not placed yet, as a line of Notepad. Drag it onto Week.exe to give it a time; a click
    opens it. Its text keeps its whole words, for a screen reader and its tooltip."""

    def __init__(self, hand: Hand, line: Deadline, name: str, colours: Scheme) -> None:
        assert line.waiting is not None
        TrayChip.__init__(self, hand, line.waiting)
        self.dress(line, name, colours)

    def _fit(self) -> None:
        return


class Page(QWidget):
    """Notepad's page: its lines, with the columns fitted to its width whenever that changes."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[NoteRow | NoteChip] = []

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fit()

    def fit(self) -> None:
        if not self.rows:
            return
        chars = int((self.width() - 14) // max(QFontMetricsF(self.rows[0].font()).horizontalAdvance("0"), 1))
        widths = note_widths([row.line for row in self.rows], chars)
        for row in self.rows:
            fitted = note_lines(row.line, widths, chars)
            if fitted != row.lines:
                row.set_lines(fitted)


class Swatch(QWidget):
    """A category's key in the web view: its fill with the mark down its left, and the book for homework."""

    def __init__(self, category: str, colours: Scheme) -> None:
        super().__init__()
        self.category, self.scheme = category, colours
        self.setFixedSize(14, 12)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        colours = self.scheme
        fill, mark = category_paint(self.category, {"family": colours.family, "panel": colours.field})
        painter.fillRect(self.rect(), QColor(fill or colours.face))
        shadow = QColor(colours.shadow)
        frame_in(painter, self.rect(), shadow, shadow)
        painter.fillRect(QRect(0, 0, 3, self.height()), QColor(mark or colours.shadow))
        if self.category == HOMEWORK:
            painter.drawPixmap(
                QPointF(3, 1), icons.pixmap("book-open", colours.ink, 10, self.devicePixelRatioF(), "2")
            )


class Rule(QWidget):
    """The web view's rule under the day's name: the title bar's gradient running out into the page."""

    def __init__(self, colours: Scheme) -> None:
        super().__init__()
        self.scheme = colours
        self.setFixedHeight(3)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, QColor(self.scheme.title))
        gradient.setColorAt(0.6, QColor(self.scheme.title_end))
        gradient.setColorAt(1, QColor(self.scheme.field))
        painter.fillRect(self.rect(), gradient)


def paint_icon(
    widget: QWidget, painter: QPainter, drawn: tuple[str, str, str], colours: Scheme, chosen: bool
) -> None:
    """A desktop icon: its picture, white inside as Windows 98's were, over its name, which is
    selected while its window is the one in front."""
    words, art, inside = drawn
    ratio = widget.devicePixelRatioF()
    fill = getattr(colours, inside) if not colours.contrast else colours.field
    picture = icons.pixmap(art, colours.ink, ICON_PX, ratio, "1.5", fill)
    painter.drawPixmap(QPointF((widget.width() - ICON_PX) // 2, 0), picture)
    font = widget.font()
    metrics = QFontMetricsF(font)
    lines = fit_lines(words, font, widget.width(), metrics.lineSpacing() * 2)
    painter.setFont(font)
    top = ICON_PX + 4
    for line in lines:
        wide = metrics.horizontalAdvance(line) + 6
        box = QRectF((widget.width() - wide) / 2, top, wide, metrics.lineSpacing())
        if chosen:
            painter.fillRect(box, QColor(colours.title))
        painter.setPen(QColor(colours.title_ink if chosen else colours.desk_ink))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, line)
        top += metrics.lineSpacing()
    if chosen and lines:
        pen = QPen(QColor(colours.desk_ink), 1, Qt.PenStyle.DotLine)
        painter.setPen(pen)
        wide = max(metrics.horizontalAdvance(line) for line in lines) + 6
        painter.drawRect(
            QRectF((widget.width() - wide) / 2 - 0.5, ICON_PX + 3.5, wide + 1, top - ICON_PX - 3)
        )


def icon_size(widget: QWidget, words: str) -> QSize:
    metrics = QFontMetricsF(widget.font())
    lines = max(len(fit_lines(words, widget.font(), ICONS_WIDE, metrics.lineSpacing() * 2)), 1)
    return QSize(ICONS_WIDE, ICON_PX + 6 + round(metrics.lineSpacing() * lines))


class DeskIcon(QWidget):
    """A desktop icon that is a picture only: Homework, Focus timer and the Recycle Bin."""

    def __init__(self, drawn: tuple[str, str, str], name: str, colours: Scheme) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setAccessibleName(drawn[0])
        self.drawn, self.scheme, self.chosen = drawn, colours, False

    def sizeHint(self) -> QSize:  # noqa: N802
        return icon_size(self, self.drawn[0])

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        paint_icon(self, QPainter(self), self.drawn, self.scheme, self.chosen)


class DeskShortcut(QPushButton):
    """A desktop icon that opens its window and brings it to the front: Week.exe and deadlines.txt."""

    def __init__(self, drawn: tuple[str, str, str], name: str, colours: Scheme) -> None:
        super().__init__(drawn[0])
        self.setObjectName(name)
        self.setAccessibleName(f"Open {drawn[0]}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drawn, self.scheme, self.chosen = drawn, colours, False

    def sizeHint(self) -> QSize:  # noqa: N802
        return icon_size(self, self.drawn[0])

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        paint_icon(self, QPainter(self), self.drawn, self.scheme, self.chosen or self.hasFocus())


class Desk(QWidget):
    """The desktop the windows sit on, in the colourway's colour or the look's accent."""

    resized = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("retroDesk")
        self.colour = STANDARD["shadow"]

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        QPainter(self).fillRect(self.rect(), QColor(self.colour))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.resized.emit()


class Taskbar(QFrame):
    """The taskbar: the face, lit along its top."""

    def __init__(self, colours: Scheme) -> None:
        super().__init__()
        self.setObjectName("retroTaskbar")
        self.scheme = colours

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        colours = self.scheme
        painter.fillRect(self.rect(), QColor(colours.face))
        painter.fillRect(QRect(0, 0, self.width(), 1), QColor(colours.light))
        painter.fillRect(QRect(0, 1, self.width(), 1), QColor(colours.hi))


class Divider(QWidget):
    """The groove between Start and the windows' buttons."""

    def __init__(self, colours: Scheme) -> None:
        super().__init__()
        self.scheme = colours
        self.setFixedSize(2, 26)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(QRect(0, 0, 1, self.height()), QColor(self.scheme.shadow))
        painter.fillRect(QRect(1, 0, 1, self.height()), QColor(self.scheme.hi))


class Zoom(QWidget):
    """Windows 98's zoom rectangle: the title bar of a window opening, flown from the button or icon
    that opened it to where the window's title bar lands, growing on the way. It only paints."""

    def __init__(self, parent: QWidget, colours: Scheme, start: QRectF, end: QRectF) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.colours, self.start, self.end, self.share = colours, start, end, 0.0
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def fly(self, share: object) -> None:
        self.share = float(share)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        rect = between(self.start, self.end, self.share)
        gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
        gradient.setColorAt(0, QColor(self.colours.title))
        gradient.setColorAt(1, QColor(self.colours.title_end))
        painter = QPainter(self)
        painter.fillRect(rect, gradient)
        painter.end()


def picture(name: str, colour: str, size: int, ratio: float, stroke: str = "2", fill: str = "none") -> QLabel:
    """An icon that is only a picture, such as the tray's bell."""
    made = QLabel()
    made.setPixmap(icons.pixmap(name, colour, size, ratio, stroke, fill))
    made.setFixedSize(size, size)
    return made


class RetroView(LayoutView):
    layout_id = "retro"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        # The design's own faces, there even for a picture of it drawn without the window.
        load_fonts()
        self._scheme = scheme(RETRO[0][2])
        self._open: dict[str, bool] = {}
        self._opened_for = ""
        # Back to front: the last one open is the window in front, whose taskbar button is pressed in.
        self._order = ["next", "notes", "week"]
        self._grids: dict[str, Grid] = {}
        self._next_tall = NEXT_TALL
        self.hand.preview_changed.connect(self._status)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._surface = QWidget()
        self._surface.setObjectName("retroSurface")
        surface = QVBoxLayout(self._surface)
        surface.setContentsMargins(0, 0, 0, 0)
        surface.setSpacing(0)
        self._desk = Desk()
        self._desk.resized.connect(self._arrange)
        surface.addWidget(scrolling(self._desk, "retroScroll"), 1)
        self._bar = Taskbar(self._scheme)
        self._bar_row = QHBoxLayout(self._bar)
        self._bar_row.setContentsMargins(4, 4, 4, 3)
        self._bar_row.setSpacing(4)
        surface.addWidget(self._bar)
        outer.addWidget(self._surface)
        # Hours kept between renders wait here while their window is rebuilt.
        self._parked = QWidget(self)
        self._parked.hide()
        self._windows = {win.key: self._window(win) for win in WINDOWS}
        self._icons: list[DeskIcon | DeskShortcut] = []
        for index, (words, art, inside, opens) in enumerate(ICONS):
            name = f"retroIcon{index}"
            icon = (
                DeskShortcut((words, art, inside), name, self._scheme)
                if opens
                else DeskIcon((words, art, inside), name, self._scheme)
            )
            if opens:
                icon.clicked.connect(lambda _=False, key=opens, icon=icon: self._bring(key, icon))
            icon.setProperty("opens", opens or "")
            icon.setProperty("role", "icon")
            icon.setParent(self._desk)
            self._icons.append(icon)

    # The windows

    def _window(self, win: Win) -> Window98:
        made = Window98(win, self._scheme)
        made.activated.connect(lambda key=win.key: self._front(key))
        made.bar.doubled.connect(lambda key=win.key: self._maximise(key) if key != "next" else None)
        caps: list[QWidget] = []
        if win.key == "next":
            caps.append(Cap(self._scheme, GLYPHS["help"]))
            caps[-1].setFixedSize(CAP)
        else:
            low = CapButton(f"retroMin-{win.key}", f"Minimise {win.name}", self._scheme, "min")
            low.clicked.connect(lambda _=False, key=win.key: self._hide(key))
            high = CapButton(f"retroMax-{win.key}", f"Maximise {win.name}", self._scheme, "max")
            high.clicked.connect(lambda _=False, key=win.key: self._maximise(key))
            caps += [low, high]
        close = CapButton(f"retroClose-{win.key}", f"Close {win.name}", self._scheme, "close")
        close.clicked.connect(lambda _=False, key=win.key: self._hide(key))
        for cap in caps:
            made.bar.row.addWidget(cap)
        made.bar.row.addSpacing(2)
        made.bar.row.addWidget(close)
        made.setParent(self._desk)
        made.hide()
        return made

    def _shown_front(self) -> str:
        return next((key for key in reversed(self._order) if self._open.get(key)), "")

    def _front(self, key: str) -> None:
        self._order = [other for other in self._order if other != key] + [key]
        self._windows[key].raise_()
        self._mark_front()

    def _bring(self, key: str, opener: QWidget | None = None) -> None:
        """Open a window if it is closed, zooming out from `opener`, and put it in front."""
        if not self._open.get(key):
            # Where the opener is now: a taskbar button is made again as the window opens.
            start = QRectF(QRect(opener.mapTo(self, QPoint(0, 0)), opener.size())) if opener else None
            self._open[key] = True
            self._rerender()
            self._zoom(key, start)
        self._front(key)

    def _zoom(self, key: str, start: QRectF | None) -> None:
        """Windows 98's zoom rectangle (decision 35 of 0.17): the window's title bar flies out from
        what opened it, and the window shows where it lands. Where things may not travel, the window
        fades in instead."""
        window = self._windows[key]
        level = app_level()
        if start is None or not moves(level):
            appear(window, level)
            return
        window.layout().activate()
        end = QRectF(QRect(window.bar.mapTo(self, QPoint(0, 0)), window.bar.size()))
        flight = Zoom(self, self._scheme, start, end)
        # Live at once, as every window is, and seen once its title bar has landed.
        appear(window, level, delay_ms=ZOOM_MS, ms=0)
        clock = QVariantAnimation(flight)
        clock.setStartValue(0.0)
        clock.setEndValue(1.0)
        clock.setDuration(duration(ZOOM_MS, level))
        clock.valueChanged.connect(flight.fly)
        clock.finished.connect(flight.deleteLater)
        clock.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _hide(self, key: str) -> None:
        self._open[key] = False
        self._windows[key].maximised = False
        self._mark_maximised(self._windows[key])
        self._rerender()

    def _maximise(self, key: str) -> None:
        window = self._windows[key]
        window.maximised = not window.maximised
        self._mark_maximised(window)
        self._front(key)
        self._arrange()

    def _mark_maximised(self, window: Window98) -> None:
        """Maximise's glyph and name, or Restore's while the window fills the desktop."""
        high = window.findChild(CapButton, f"retroMax-{window.win.key}")
        if high is not None:
            high.drawn = "restore" if window.maximised else "max"
            high.setAccessibleName(f"{'Restore' if window.maximised else 'Maximise'} {window.win.name}")
            high.setToolTip(high.accessibleName())
            high.update()

    def _task(self, key: str) -> None:
        """A taskbar button, as Windows 98's: a closed window opens in front, the one in front is put
        away, any other comes to the front."""
        if not self._open.get(key):
            self._bring(key, self.findChild(Button98, f"retroTask-{key}"))
        elif self._shown_front() == key:
            self._hide(key)
        else:
            self._front(key)

    def _rerender(self) -> None:
        if self._scene is not None:
            self.render(self._scene, False)

    def _mark_front(self) -> None:
        front = self._shown_front()
        for win in WINDOWS:
            task = self.findChild(Button98, f"retroTask-{win.key}")
            if task is None:
                continue
            opened = bool(self._open.get(win.key))
            task.sunk = task.dither = task.strong = win.key == front
            task.setProperty("open", "true" if opened else "false")
            task.setAccessibleName(
                f"Hide {win.name}"
                if win.key == front
                else f"Show {win.name}"
                if not opened
                else f"Bring {win.name} to the front"
            )
            task.update()
        for icon in self._icons:
            icon.chosen = bool(icon.property("opens")) and icon.property("opens") == front
            icon.update()

    # Drawing the scene

    def _shown_day(self, scene: Scene) -> int:
        if scene.surface == "day" and scene.iso_day:
            for day in range(7):
                if scene.week.date_of(day).isoformat() == scene.iso_day:
                    return day
        return scene.today if scene.today is not None else 0

    def render(self, scene: Scene, week_changed: bool) -> None:
        colours = self._scheme = scheme(scene.tokens)
        wanted = scene.options.get("windows", "all")
        if wanted != self._opened_for:
            self._opened_for = wanted
            self._open = {win.key: wanted == "all" or win.key == "week" for win in WINDOWS}
        self.setStyleSheet(self._sheet(scene))
        rows = self._windows["week"].body.findChildren(QLayout)
        for grid in self._grids.values():
            # Out of its row through the row first. Moved while the row still lists it, Qt deletes the
            # row's item unseen by PySide, whose wrapper for that item then stands for whatever Qt makes
            # at its address next. A widget reached Python as a layout item, and the app segfaulted.
            for row in rows:
                row.removeWidget(grid)
            grid.hide()
            grid.setParent(self._parked)
        self._desk.colour = colours.desk
        self._desk.update()
        self._bar.scheme = colours
        for window in self._windows.values():
            window.scheme = colours
            for child in window.bar.findChildren(QWidget):
                if isinstance(child, (Cap, CapButton)):
                    child.scheme = colours
            empty(window.body)
        is_day = scene.surface == "day"
        day = self._shown_day(scene) if is_day else None
        self._windows["week"].bar.setText(self._week_title(scene, day))
        self._week_body(scene, day)
        self._notes_body(scene)
        self._next_body(scene)
        for key, window in self._windows.items():
            window.setVisible(bool(self._open.get(key)))
            window.update()
        for icon in self._icons:
            icon.scheme = colours
            icon.adjustSize()
        self._taskbar(scene)
        self._mark_front()
        self._arrange()
        QTimer.singleShot(0, self._arrange)

    def _sheet(self, scene: Scene) -> str:
        colours, sizes = self._scheme, type_sizes(scene.scale)
        edge = f"{colours.hi} {colours.dark} {colours.dark} {colours.hi}"
        return base_sheet(self.objectName(), scene.tokens) + rules(
            self.objectName(),
            {
                "#retroSurface QWidget": css(
                    background="transparent", font_family=PIXEL_FACE, font_size=sizes["body"], font_weight=400
                ),
                "#retroSurface QLabel, #retroSurface QPushButton": css(color=colours.ink),
                # Every button here draws itself at the size its words need: the app's taller buttons at
                # large text stretched the title bars' buttons past their glyphs and spaced out Notepad.
                "#retroSurface QPushButton": css(min_height="0", padding="0"),
                '#retroSurface QLabel[role="menu"]': css(padding="1px 7px"),
                '#retroSurface QLabel[role="caption"], #retroSurface QPushButton[role="head"]': css(
                    font_size=sizes["caption"]
                ),
                '#retroSurface QWidget[role="icon"], #retroSurface QPushButton[role="icon"]': css(
                    font_size=sizes["caption"]
                ),
                '#retroSurface QLabel[role="strong"]': css(font_weight=600),
                '#retroSurface QLabel[role="heading"]': css(font_size=sizes["heading"], font_weight=600),
                '#retroSurface QLabel[role="display"]': css(font_size=sizes["display"], font_weight=600),
                '#retroSurface QLabel[role="note"], #retroSurface QPushButton[role="note"]': css(
                    font_family=NOTE_FACE, font_size=sizes["heading"], color=colours.ink
                ),
                '#retroSurface QLabel[role="cell"]': css(font_size=sizes["caption"], padding="0 6px"),
                '#retroSurface QLabel#retroStatus[verdict="refused"]': css(color=colours.danger),
                '#retroSurface QFrame[role="webrow"]': css(
                    border="none", border_bottom=f"1px solid {colours.rule}"
                ),
                '#retroSurface QPushButton[role="chip"]': css(
                    background=colours.field,
                    border=f"1px solid {colours.shadow}",
                    border_radius="0",
                    text_align="left",
                    padding="2px 6px",
                    font_size=sizes["caption"],
                ),
                '#retroSurface QWidget[zoomPill="true"]': css(
                    background=colours.face,
                    border_style="solid",
                    border_width="1px",
                    border_color=edge,
                    border_radius="0",
                ),
                "#retroSurface QWidget#retroWeekZoom, #retroSurface QWidget#retroDayZoom": css(
                    background=colours.face, border_style="solid", border_width="1px", border_color=edge
                ),
                "#retroSurface QWidget#zoomDivider": css(background=colours.shadow),
                '#retroSurface QPushButton[zoom="true"]': css(
                    background="transparent", color=colours.ink, border="none", border_radius="0"
                ),
                '#retroSurface QPushButton[zoom="true"]:disabled': css(color=colours.shadow),
                'QScrollBar[retro="true"]:vertical': css(
                    width=f"{BAR}px", margin=f"{BAR}px 0 {BAR}px 0", background="transparent", border="none"
                ),
                'QScrollBar[retro="true"]::sub-line:vertical': css(
                    width=f"{BAR}px", height=f"{BAR}px", subcontrol_position="top", subcontrol_origin="margin"
                ),
                'QScrollBar[retro="true"]::add-line:vertical': css(
                    width=f"{BAR}px",
                    height=f"{BAR}px",
                    subcontrol_position="bottom",
                    subcontrol_origin="margin",
                ),
                'QScrollBar[retro="true"]::handle:vertical': css(min_height="12px", margin="0"),
            },
        )

    def _week_title(self, scene: Scene, day: int | None) -> str:
        week = scene.week
        if day is not None:
            shown = week.date_of(day)
            return f"Week.exe - {DAY_FULL[day]} {shown.day} {MONTHS[shown.month - 1]}"
        return f"Week.exe - {planner_title(week, 'week')}"

    def _menu(self, key: str) -> QHBoxLayout:
        """A window's menu bar, as drawn. Its menus are pictures: FlexWeek's own are in More and Start."""
        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(0)
        for words in MENUS[key]:
            made = QLabel(f"<u>{words[0]}</u>{words[1:]}")
            made.setTextFormat(Qt.TextFormat.RichText)
            made.setProperty("role", "menu")
            made.setMinimumHeight(24)
            row.addWidget(made)
        row.addStretch(1)
        return row

    def _week_body(self, scene: Scene, day: int | None) -> None:
        body, colours = self._windows["week"].body, self._scheme
        body.addLayout(self._menu("week"))
        grid = self._grid(scene, day)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        if day is not None:
            row.addWidget(self._webview(scene, day))
        row.addWidget(grid, 1)
        body.addLayout(row, 1)
        grid.show()
        grid.dress(colours)
        if scene.week.waiting and not self._open.get("notes"):
            # Notepad is where they live; here only while it is closed, so they are never shown twice.
            words = label("Not placed yet · deadlines.txt", "retroWaitingLabel")
            words.setProperty("role", "caption")
            body.addSpacing(4)
            body.addWidget(words)
            body.addLayout(self._tray(scene))
        status = QHBoxLayout()
        status.setContentsMargins(0, 2, 0, 0)
        status.setSpacing(2)
        ready = Cell("Ready", "retroStatus", colours)
        ready.setMinimumWidth(96)
        ahead = self._ahead(scene, day)
        middle = Cell(ahead or "", "retroStatusNow", colours)
        waiting = len(scene.week.waiting)
        right = Cell(
            (f"{waiting} homework {NOT_PLACED}", f"{waiting} {NOT_PLACED}")
            if waiting
            else "Everything has a time",
            "retroStatusWaiting",
            colours,
        )
        for index, cell in enumerate((ready, middle, right)):
            cell.setProperty("role", "cell")
            cell.setFixedHeight(24)
            cell.setSizePolicy(
                QSizePolicy.Policy.Ignored if index else QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )
            status.addWidget(cell, 1 if index else 0)
        # Shown before it has a parent, a widget is a window of its own for a moment, which takes the
        # keyboard from FlexWeek's. Hidden, it stays hidden; otherwise it shows with its parent.
        if not ahead:
            middle.hide()
        body.addLayout(status)
        self._status()

    def _ahead(self, scene: Scene, day: int | None) -> tuple[str, ...]:
        """The status bar's middle, and shorter ways to say it: today and now on the week, what is
        still to come on today's Day."""
        if scene.today is None or day not in (None, scene.today):
            return ()
        if day is None:
            number, now = scene.week.date_of(scene.today).day, clock_label(scene.minute)
            return (f"{DAY_FULL[scene.today]} {number}, {now}", f"{DAYS[scene.today]} {number}, {now}", now)
        ahead = sum(item.start > scene.minute for item in scene.week.on_day(day))
        return (f"{ahead} still to come", f"{ahead} to come")

    def _grid(self, scene: Scene, day: int | None) -> Grid:
        key = "week" if day is None else "day"
        grid = self._grids.get(key)
        if grid is None:
            canvas = RetroCanvas(
                self.hand, RetroPainter(self._scheme, wide=day is not None), week=day is None
            )
            canvas.setObjectName("retroHours")
            canvas.day_opened.connect(
                lambda chosen: self.day_activated.emit(self.scene.week.date_of(chosen).isoformat())
            )
            scroll = self.keep_zoom(
                HoursScroll(
                    canvas,
                    WEEK_SCALE if day is None else DAY_SCALE,
                    _height,
                    name=f"retro{key.title()}",
                    gutter=GUTTER,
                )
            )
            names = QWidget()
            names.setObjectName(f"retro{key.title()}Names")
            row = QHBoxLayout(names)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            if day is None:
                for target in range(7):
                    head = DayHead(f"retroDay{target}", self._scheme, target)
                    head.clicked.connect(
                        lambda _=False, chosen=target: self.day_activated.emit(
                            self.scene.week.date_of(chosen).isoformat()
                        )
                    )
                    canvas.day_buttons[target] = head
                    row.addWidget(head, 1)
            else:
                row.addWidget(DayHead("retroDayHead", self._scheme, None), 1)
            scroll.set_header(names)
            grid = self._grids[key] = Grid(scroll, self._scheme)
        scroll, canvas = grid.scroll, grid.scroll.canvas
        canvas.set_painter(RetroPainter(self._scheme, wide=day is not None))
        for head in scroll.header.findChildren(DayHead):
            head.scheme = self._scheme
        if day is not None:
            canvas._lay_out = lambda area: [LinearTrack(day, area.adjusted(0, PAD, 0, -PAD))]
            canvas.relayout()
            items = scene.week.on_day(day)
            scroll.header.findChild(DayHead, "retroDayHead").show_day(day, scene.week.date_of(day).day, True)
        else:
            items = scene.week.occurrences
            for target, head in canvas.day_buttons.items():
                head.show_day(target, scene.week.date_of(target).day, target == scene.today)
        canvas.set_week(items, scene.today, scene.minute)
        open_hours(
            scroll,
            scene.week.week_start if day is None else (scene.week.week_start, day),
            scene.week,
            scene.today,
            scene.minute,
            day,
        )
        return grid

    def _tray(self, scene: Scene) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        for index, waiting in enumerate(scene.week.waiting):
            chip = TrayChip(self.hand, waiting)
            chip.setObjectName(f"retroWaiting{index}")
            chip.setProperty("role", "chip")
            chip.setToolTip(f"{chip.toolTip()} {waiting.reason}")
            chip.clicked.connect(
                lambda _=False, block_id=waiting.block_id: self.block_activated.emit(block_id)
            )
            row.addWidget(chip, 1)
        return row

    def _status(self) -> None:
        status = self.findChild(QLabel, "retroStatus")
        if status is None:
            return
        preview = self.hand.preview
        if preview is None:
            status.setText("Ready")
            status.setProperty("verdict", "ready")
        else:
            times = f"{clock_label(preview.span.start)}–{clock_label(preview.span.end)}"
            words = preview.verdict.words
            if preview.verdict.ok:
                status.setText(words or times)
            else:
                status.setText(f"{times} · {words}" if words else times)
            status.setProperty("verdict", "ok" if preview.verdict.ok else "refused")
        status.style().unpolish(status)
        status.style().polish(status)

    def _webview(self, scene: Scene, day: int) -> QFrame:
        """Windows 98's folder web view beside Day's hours: the day's name and date, how much is planned
        and still to come, the day by category, and its free time."""
        colours = self._scheme
        pane = Field("retroWebview", colours)
        pane.setFixedWidth(round(WEBVIEW * scene.scale))
        box = QVBoxLayout(pane)
        box.setContentsMargins(16, 16, 16, 12)
        box.setSpacing(0)
        shown = scene.week.date_of(day)
        items = scene.week.on_day(day)
        today = day == scene.today
        name = label(DAY_FULL[day], "retroWebDay")
        name.setProperty("role", "display")
        box.addWidget(name)
        box.addSpacing(8)
        box.addWidget(Rule(colours))
        box.addSpacing(12)
        dated = label(f"{shown.day} {MONTHS[shown.month - 1]}", "retroWebDate")
        dated.setProperty("role", "strong")
        box.addWidget(dated)
        ahead = sum(item.start > scene.minute for item in items) if today else None
        planned = label(planned_words(items, ahead), "retroWebPlanned", wrap=True)
        planned.setProperty("role", "caption")
        box.addWidget(planned)
        kinds = category_minutes(items)
        if kinds:
            box.addWidget(self._subhead("Your day", "retroWebYourDay"))
            for index, (category, minutes) in enumerate(kinds):
                box.addWidget(
                    self._web_row(
                        category_title(category),
                        length_label(minutes),
                        f"retroWebKey{index}",
                        Swatch(category, colours),
                    )
                )
        if today or scene.today is None or day > scene.today:
            free = free_from(items, scene.minute if today else FREE_FROM)
            if free:
                box.addWidget(self._subhead("Free from now" if today else "Free", "retroWebFreeHead"))
                for index, (start, end) in enumerate(free):
                    words = f"{clock_label(start)}–{clock_label(end)}"
                    box.addWidget(self._web_row(words, length_label(end - start), f"retroWebFree{index}"))
        box.addStretch(1)
        return pane

    def _subhead(self, words: str, name: str) -> QLabel:
        made = label(words, name)
        made.setProperty("role", "strong")
        made.setContentsMargins(0, 16, 0, 6)
        return made

    def _web_row(self, words: str, length: str, name: str, key: QWidget | None = None) -> QFrame:
        row = QFrame()
        row.setObjectName(name)
        row.setProperty("role", "webrow")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 3, 0, 3)
        line.setSpacing(6)
        if key is not None:
            line.addWidget(key)
        said = label(words, f"{name}Name")
        said.setProperty("role", "caption")
        line.addWidget(said, 1)
        long = label(length, f"{name}Length")
        long.setProperty("role", "caption")
        line.addWidget(long)
        return row

    def _notes_body(self, scene: Scene) -> None:
        colours = self._scheme
        body = self._windows["notes"].body
        body.addLayout(self._menu("notes"))
        page = Field("retroNotepad", colours)
        inside = QHBoxLayout(page)
        inside.setContentsMargins(2, 2, 2, 2)
        inside.setSpacing(0)
        area = QScrollArea()
        area.setObjectName("retroNotesScroll")
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setVerticalScrollBar(RetroBar("retroNotesBar", colours))
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        text = Page()
        lines = QVBoxLayout(text)
        lines.setContentsMargins(6, 4, 6, 4)
        lines.setSpacing(0)
        groups = deadlines(scene.week, scene.today)
        placed = waiting = 0
        for group in groups:
            lines.addWidget(self._note(group.heading, "retroNoteDue", wrap=True))
            lines.addWidget(self._note("", "retroNoteBlank"))
            for line in group.lines:
                if line.waiting is not None:
                    row: NoteRow | NoteChip = NoteChip(self.hand, line, f"retroNoteWaiting{waiting}", colours)
                    row.setToolTip(f"{row.toolTip()} {line.waiting.reason}")
                    waiting += 1
                else:
                    row = NoteRow(line, f"retroNote{placed}", colours)
                    placed += 1
                row.clicked.connect(
                    lambda _=False, block_id=line.block_id: self.block_activated.emit(block_id)
                )
                text.rows.append(row)
                lines.addWidget(row)
            lines.addWidget(self._note("", "retroNoteBlank"))
        count = len(scene.week.waiting)
        if count:
            them = "it" if count == 1 else "them"
            hint = f"{count} {NOT_PLACED}: drag {them} onto Week.exe, or use Plan my homework."
            lines.addWidget(self._note(hint, "retroNotesHint", wrap=True))
        else:
            lines.addWidget(self._note("Everything has a time.", "retroNotesNoWaiting", wrap=True))
        lines.addStretch(1)
        area.setWidget(text)
        inside.addWidget(area)
        body.addWidget(page, 1)
        text.fit()

    def _note(self, words: str, name: str, *, wrap: bool = False) -> QLabel:
        made = label(words, name, wrap=wrap)
        made.setProperty("role", "note")
        return made

    def _next_body(self, scene: Scene) -> None:
        colours = self._scheme
        body = self._windows["next"].body
        said = up_next(scene)
        row = QHBoxLayout()
        row.setContentsMargins(16, 14, 16, 4)
        row.setSpacing(16)
        art = picture("clock", colours.ink, ICON_PX, self.devicePixelRatioF(), "1.5", colours.field)
        row.addWidget(art, 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(2)
        head = label(said.title, "retroNextTitle", wrap=True)
        head.setProperty("role", "heading")
        # Hidden, never shown, before they have a parent: see the status bar's middle cell.
        if not said.title:
            head.hide()
        words.addWidget(head)
        words.addWidget(label(said.line, "retroNextText", wrap=True))
        then = label(said.then, "retroNextThen", wrap=True)
        then.setContentsMargins(0, 6, 0, 0)
        if not said.then:
            then.hide()
        words.addWidget(then)
        words.addStretch(1)
        row.addLayout(words, 1)
        body.addLayout(row, 1)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 6, 0, 10)
        buttons.setSpacing(8)
        buttons.addStretch(1)
        ok = Button98("OK", "retroNextOk", colours, ring=True)
        ok.clicked.connect(lambda _=False: self._hide("next"))
        day = Button98("My day", "retroNextDay", colours, underline=0)
        day.clicked.connect(self.my_day_requested.emit)
        for made in (ok, day):
            made.setMinimumWidth(88)
            buttons.addWidget(made)
        buttons.addStretch(1)
        body.addLayout(buttons)
        box = self._windows["next"].layout()
        need = box.heightForWidth(self._side()) if box.hasHeightForWidth() else box.sizeHint().height()
        self._next_tall = max(need, round(NEXT_TALL * scene.scale))

    def _taskbar(self, scene: Scene) -> None:
        colours = self._scheme
        empty(self._bar_row)
        start = Button98("Start", "retroStart", colours, icon="calendar-days", icon_ink=colours.title)
        start.strong = True
        start.setToolTip("FlexWeek's menu")
        start.clicked.connect(lambda _=False: self.menu_requested.emit(start.mapToGlobal(QPoint(0, 0))))
        self._bar_row.addWidget(start)
        self._bar_row.addWidget(Divider(colours))
        for win in WINDOWS:
            task = Button98(win.name, f"retroTask-{win.key}", colours, icon=win.icon, left=True)
            task.setProperty("kind", "task")
            task.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            task.setMaximumWidth(168)
            task.clicked.connect(lambda _=False, key=win.key: self._task(key))
            self._bar_row.addWidget(task, 1)
        self._bar_row.addStretch(1)
        tray = Well("retroTray", colours)
        inside = QHBoxLayout(tray)
        inside.setContentsMargins(12, 0, 12, 0)
        inside.setSpacing(8)
        inside.addWidget(picture("bell", colours.ink, 14, self.devicePixelRatioF()))
        clock = label(clock_label(scene.minute), "retroClock")
        clock.setProperty("role", "caption")
        inside.addWidget(clock)
        tray.setFixedHeight(28)
        self._bar_row.addWidget(tray)

    # Where the windows sit

    def _side(self) -> int:
        width = self._desk.width() or self.width()
        return min(SIDE, max(SIDE_LEAST, round(width * SIDE / STAGE)))

    def bottom_inset(self) -> int:
        return self._bar.height()

    def _arrange(self) -> None:
        if self._scene is None:
            return
        self._desk.setMinimumSize(
            WEEK_LEAST + SIDE_LEAST + 3 * MARGIN, 2 * MARGIN + NOTES_LEAST + GAP + self._next_tall
        )
        homes, icons_shown = arrange(self._desk.size(), self._next_tall, self._scene.scale)
        for key, window in self._windows.items():
            if window.maximised:
                window.setGeometry(self._desk.rect())
            elif window.property("moved"):
                window.resize(homes[key].size())
                window.move(
                    min(max(window.x(), 0), max(self._desk.width() - 60, 0)),
                    min(max(window.y(), 0), max(self._desk.height() - 30, 0)),
                )
            else:
                window.setGeometry(homes[key])
        top = 10
        for icon in self._icons:
            icon.setVisible(icons_shown)
            icon.move(0, top)
            top += icon.height() + 16
        for key in self._order:
            self._windows[key].raise_()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, self._arrange)
