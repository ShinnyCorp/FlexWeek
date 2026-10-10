"""The look editor: a look of the student's own, made from any of the ten, in a full-window editor with
the controls on the left and the week at full size on the right (0.17's Customise, option B).

The controls wear the look being customised as it comes, so a colour that does not read never hides
them. The window wears every change at once, and the right side is a picture of its week page. What a
look may hold, how it reads and how it is kept are custom_look.py's and look.py's; this is the screen.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPalette, QPen, QPixmap, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.native import icons
from desktop.native.calendar import CATEGORIES
from desktop.native.custom_look import (
    FILE_MAX_BYTES,
    UNNAMED,
    LookNameError,
    Problem,
    apply_fix,
    base_of,
    delete_look,
    duplicate_look,
    export_look,
    free_name,
    import_look,
    readability,
    rename_look,
    reset_look,
    save_look,
    start_custom,
    wear,
)
from desktop.native.hours.canvas import EDGE_WIDTH
from desktop.native.look import (
    AA_TEXT,
    ACCENT_COLORS,
    ACCENTS,
    BASE_LABELS,
    CUSTOM_COLOURS,
    CUSTOM_RANGES,
    FONT_FAMILIES,
    LOOK_BASES,
    NAME_MAX,
    OWN_ACCENT,
    PRESET_PALETTES,
    block_paint,
    category_paint,
    effective_look,
    look_measures,
    look_motion,
    pack_stylesheet,
    readable_ink,
    resolved_palette,
    sanitize_custom,
    sanitize_look,
)
from desktop.native.look_preview import SAVED_PREFIX, look_choice, look_preview
from desktop.native.motion import switch_page
from desktop.native.previews import CANVAS, system_dark
from desktop.native.previews import render as render_preview
from desktop.native.tokens import MARK, SPACING, fit_lightness, mix, oklch, oklch_of
from desktop.native.widgets import (
    CARD_WIDTH_PAD,
    SHEET_LIST,
    SHEET_PAD,
    SHEET_PREVIEW,
    CardGrid,
    ChoiceCard,
    ConfirmSheet,
    Dialog,
    Segmented,
    SwatchButton,
    Swatches,
    Switch,
    WhyOff,
    bare,
    confirm,
    control_art,
    overlay_scroll_bars,
    sheet_button,
    sheet_footer,
    sheet_note,
)

TITLE = "Look editor"
START_FROM = "Start from"
START_NOTE = "Pick a look to start your own from. What you have not saved is left behind."
START_YOURS = "Your look"
START_TILE = 112
NAME = "Name"
LOOKS = "Looks"
YOUR_LOOKS = "Your looks"
SAVED_STATE = "Saved"
CHANGED_STATE = "Changed, not saved"
CHANGED_TAG = "Changed"
BACK_TIP = "Back to Settings (Esc)"
READABILITY = "Readability"
EVERYTHING_READS = "Everything reads"
FIX, FIX_ALL = "Fix", "Fix all"
MORE_ROWS = "{count} more under 4.5:1. Fix all fixes them too."
BLOCK_ROWS = "Text on {count} block colours is {ratio}:1 at worst"
RESET, RESET_ALL = "Reset", "Reset all"
EXPORT, IMPORT = "Export", "Import"
SAVE_AS_NEW, DONE = "Save as new", "Done"
FIT_NOTE = "The whole window, fitted to this space."
ACTUAL_NOTE = "The whole window, at its real size: scroll to see all of it."
ANY_COLOUR, YOUR_COLOUR = "Any colour", "Your colour"
EXACT = "Exact colour"
COLOURS_NOTE = "The paler text and the other shades follow from these four."
CATEGORIES_NOTE = (
    "A colour picked on the slider always stays readable. Exact colour takes any colour, and Readability "
    "warns if text on it is hard to read."
)
EDGE_NOTE = "Filled blocks have no edge."
PLAY = "Play it on the preview"
MOTION_NOTES = {
    "normal": "Fades, and views slide 12 px.",
    "extra": "Longer, and views slide 16 px.",
    "reduce": "Fades only, nothing slides. The Paper look uses this.",
    "off": "Nothing moves.",
}
LEAVE_TITLE = "Leave the look editor"
LEAVE_SAVED = "Save the changes to {name}?"
LEAVE_NEW = "Save your look as {name}?"
LEAVE_NOTE = "Keep without saving leaves the changes on until you choose another look."
SAVE, KEEP, DISCARD = "Save", "Keep without saving", "Discard changes"
CANCEL = "Cancel"
# Wide enough for its four answers in one row at their roomy sizes, which a plain list's width was not.
LEAVE_WIDTH = SHEET_LIST + 2 * SHEET_PAD + 24
DELETE_TITLE = "Delete look"
DELETE_QUESTION = "Delete {name}? This can't be undone."
EXPORT_TITLE, IMPORT_TITLE = "Export look", "Import look"
LOOK_FILES = "FlexWeek look (*.json)"
NOT_OPENED = "That file could not be opened."
EXPORTED = "Exported {name}."
IMPORTED = "Imported {name}."
COPIED = "Saved a copy as {name}."
WRITE_FAILED = "Could not write that file."

ACCENT_LABELS = {"default": "Blue"}
FACES = (("Sans", "sans"), ("Serif", "serif"), ("Mono", "mono"))
TEXT_SIZES = (("Small", 0.9), ("Normal", 1.0), ("Large", 1.2))
MOTION_CHOICES = (("Normal", "normal"), ("More", "extra"), ("Reduce", "reduce"), ("Off", "off"))
# The mock-up's column: 360 pixels at Normal text, readability first, then the groups.
COLUMN_WIDTH = 360
READABILITY_ROWS = 8
# Fix all moves one colour at a time, since each move changes what the next pair is measured against.
FIX_ALL_ROUNDS = 16
PAIR_SIZE = QSize(34, 24)
CHIP_SIZE = QSize(48, 30)
HEX = re.compile(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

FieldPath = tuple[str, ...]


@dataclass(frozen=True)
class Group:
    """One card of the column: its name, its icon, and the settings it holds, each where it sits in a
    custom look."""

    key: str
    name: str
    icon: str
    fields: tuple[FieldPath, ...]


GROUPS = (
    Group("colours", "Colours", "palette", (("accent",), *(("colours", key) for key in CUSTOM_COLOURS))),
    Group("categories", "Categories", "swatch-book", tuple(("categories", key) for key in CATEGORIES)),
    Group("shape", "Shape", "square-round-corner", (("corners",), ("spacing",), ("shadows",))),
    Group("type", "Type", "type", (("body_font",), ("heading_font",), ("text_scale",))),
    Group(
        "blocks",
        "Blocks",
        "calendar-range",
        (("blocks",), ("edge_width",), ("show_times",), ("show_lengths",)),
    ),
    Group("grid", "Grid", "grid-3x3", (("hour_lines",), ("now_line",), ("today_highlight",))),
    Group("motion", "Motion", "wind", (("motion",),)),
)
FIELDS = tuple(field for group in GROUPS for field in group.fields)


def setting(custom: dict, path: FieldPath) -> object:
    """What `custom` sets at `path`, or None where it leaves its base's own."""
    value: object = custom
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def with_setting(custom: dict, path: FieldPath, value: object) -> dict:
    """`custom` with `path` set to `value`, or back to its base's own for None."""
    head, rest = path[0], path[1:]
    changed = dict(custom)
    if rest:
        inner = with_setting(dict(custom.get(head) or {}), rest, value)
        if inner:
            changed[head] = inner
        else:
            changed.pop(head, None)
    elif value is None:
        changed.pop(head, None)
    else:
        changed[head] = value
    return changed


@dataclass(frozen=True)
class Draft:
    """The look being made; the look it is measured from, as it came or as it was last saved, which
    Reset goes back to; and the name of the saved look it is, or None for a new one."""

    look: dict
    start: dict
    saved_as: str | None = None

    def changed(self, fields: tuple[FieldPath, ...] = FIELDS) -> bool:
        return any(setting(self.look, path) != setting(self.start, path) for path in fields)

    def state(self) -> str:
        if self.changed():
            return CHANGED_STATE
        return SAVED_STATE if self.saved_as else ""


def open_draft(pack: object, look: dict, accent: object, saved: list[dict]) -> Draft:
    """What the editor opens on: the look worn, as a custom look. One of the student's saved looks is
    that look, with any changes kept without saving still to save; a custom look not saved has all its
    changes still to save; a built-in look has none."""
    custom = start_custom(pack, look, accent)
    if "custom" not in sanitize_look(look):
        return Draft(custom, dict(custom))
    name = str(custom.get("name") or "").casefold()
    kept = next((entry for entry in saved if entry["name"].casefold() == name), None)
    if kept is not None:
        return Draft(custom, dict(kept), kept["name"])
    return Draft(custom, reset_look(custom))


@dataclass(frozen=True)
class Row:
    """A line of Readability: what reads badly, drawn in its own colours, and the fixes its Fix makes."""

    words: str
    ink: str
    ground: str
    fixes: tuple[Problem, ...]


def ratio_words(ratio: float) -> str:
    # Rounded down, so a pair short of 4.5 to 1 never shows as 4.5.
    return f"{math.floor(ratio * 10) / 10:.1f}"


def problem_rows(problems: list[Problem]) -> list[Row]:
    """Each pair under 4.5 to 1 with its Fix. Three or more block colours are one line, at the worst."""
    blocks = [problem for problem in problems if problem.field[0] == "categories"]
    together = len(blocks) >= 3
    rows = [
        Row(
            f"{problem.words} {'are' if problem.plural else 'is'} {ratio_words(problem.ratio)}:1",
            problem.ink,
            problem.ground,
            (problem,),
        )
        for problem in problems
        if not (together and problem in blocks)
    ]
    if together:
        worst = min(blocks, key=lambda problem: problem.ratio)
        words = BLOCK_ROWS.format(count=len(blocks), ratio=ratio_words(worst.ratio))
        rows.append(Row(words, worst.ink, worst.ground, tuple(blocks)))
    return rows


def fix_all(custom: dict, dark: bool) -> dict:
    """Every problem fixed, not the first only: each round applies the Fix of one problem for each colour
    that has any (two rows of the accent share one), then looks again, since a moved colour can change
    what another reads on."""
    for _round in range(FIX_ALL_ROUNDS):
        found = readability(custom, dark)
        if not found:
            break
        for problem in {problem.field: problem for problem in reversed(found)}.values():
            custom = apply_fix(custom, problem)
    return custom


def hex_colour(text: str) -> str | None:
    """A colour typed as #3d6fc4, 3d6fc4 or #36c, as #3d6fc4; None for anything else."""
    match = HEX.fullmatch(text.strip())
    if match is None:
        return None
    digits = match.group(1).lower()
    return "#" + ("".join(digit * 2 for digit in digits) if len(digits) == 3 else digits)


def file_stem(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "look"


def editor_rules(palette: dict, radius: int) -> str:
    """What the editor draws beyond Settings' own controls: its bars, the cards' heads, the sliders
    (a hue slider shows the family's marks), the colour fields and the Changed tag. Its type is the
    window stylesheet's (look.py's `settings_rules`), as every screen's is."""
    line, strong = palette["hairline"], palette["hairline_strong"]
    text, muted, accent, panel = palette["text"], palette["muted"], palette["accent"], palette["panel"]
    contrast_look = palette.get("family") == "contrast"
    tint = "transparent" if contrast_look else mix(accent, panel, 0.12)
    tag_edge = f"1px solid {accent}" if contrast_look else "none"
    # The plain accent is 2.3 to 1 on its own tint when pale (#94): its hue, moved only as far as 4.5 takes.
    tag_words = fit_lightness(accent, (panel if contrast_look else tint,), AA_TEXT)
    hover = mix(text, panel, 0.06)
    light, chroma = MARK[palette.get("family", "light")]
    stops = ", ".join(f"stop:{step / 8:.3f} {oklch(light, chroma, step * 45)}" for step in range(9))
    return (
        f"QWidget#lookEditor, QWidget#lookEditorHead, QWidget#lookEditorFoot, QWidget#lookEditorZoom "
        f"{{ background: {palette['window']}; }}"
        f"QWidget#lookEditorHead {{ border-bottom: 1px solid {line}; }}"
        f"QWidget#lookEditorFoot, QWidget#lookEditorZoom {{ border-top: 1px solid {line}; }}"
        f"QScrollArea#lookEditorColumn {{ background: {palette['window']}; border: none; "
        f"border-right: 1px solid {line}; border-radius: 0; padding: 0; }}"
        "QScrollArea#lookPicture { background: transparent; border: none; border-radius: 0; padding: 0; }"
        "QLabel#lookInlineLabel, QLabel#lookNote, QLabel#lookOut, QLabel#lookEditorState, "
        f'QLabel#lookEverythingReads, QCheckBox[exact="true"] {{ color: {muted}; }}'
        f"QLabel#lookTag {{ background: {tint}; color: {tag_words}; border: {tag_edge}; border-radius: 10px; "
        "padding: 2px 6px; }"
        f"QWidget#lookGroupLine {{ background: {line}; }}"
        f"QPushButton#lookGroupToggle {{ background: transparent; border: 2px solid transparent; "
        f"border-radius: {radius}px; padding: 0; min-height: 44px; text-align: left; }}"
        f"QPushButton#lookGroupToggle:hover {{ background: {hover}; }}"
        'QPushButton[small="true"] { padding: 2px 4px; min-height: 0; }'
        'QPushButton[iconOnly="true"] { padding: 0; min-height: 0; }'
        # The column's segments share its width, as the mock-up's do, so four fit in 360 pixels.
        f'QScrollArea#lookEditorColumn QRadioButton[segment="true"] {{ padding: 4px {SPACING[1]}px; }}'
        # Settings draws a quiet button that cannot be pressed with an edge; here it is its words at 40 %.
        'QWidget#lookEditor QPushButton[quiet="true"]:disabled { background: transparent; '
        f"border: 2px solid transparent; color: {mix(text, palette['window'], 0.4)}; }}"
        f"QPushButton#lookSwatch {{ background: {panel}; border: 1px solid {strong}; "
        f"border-radius: {radius}px; padding: 3px; min-height: 0; }}"
        f"QPushButton#lookSwatch:hover {{ border-color: {accent}; }}"
        f"QLineEdit#lookHex {{ font-family: {FONT_FAMILIES['mono']}; }}"
        f'QLineEdit#lookHex[problem="true"] {{ border: 1px solid {palette["error"]}; }}'
        "QSlider { background: transparent; min-height: 24px; }"
        f"QSlider::groove:horizontal {{ height: 6px; border-radius: 3px; background: {strong}; }}"
        f"QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 3px; }}"
        f"QSlider::add-page:horizontal {{ background: {strong}; border-radius: 3px; }}"
        f"QSlider::handle:horizontal {{ background: {panel}; border: 2px solid {text}; width: 14px; "
        "height: 14px; margin: -6px 0; border-radius: 9px; }"
        f"QSlider::handle:horizontal:focus {{ border-color: {accent}; }}"
        f"QSlider::sub-page:horizontal:disabled {{ background: {mix(accent, palette['window'], 0.4)}; }}"
        f"QSlider::handle:horizontal:disabled {{ border-color: {mix(text, palette['window'], 0.4)}; }}"
        f"QSlider#lookHue::groove:horizontal {{ "
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {stops}); }}"
        "QSlider#lookHue::sub-page:horizontal, QSlider#lookHue::add-page:horizontal { "
        "background: transparent; }"
    )


def _colour_picture(colour: str, size: QSize, edge: str, radius: int) -> QPixmap:
    """A colour field's swatch: the colour inside a hairline, so white shows on a white card."""
    picture = QPixmap(size)
    picture.fill(Qt.GlobalColor.transparent)
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(edge), 1))
    painter.setBrush(QColor(colour))
    painter.drawRoundedRect(QRectF(0.5, 0.5, size.width() - 1, size.height() - 1), radius, radius)
    painter.end()
    return picture


def _label(words: str, name: str, wrap: bool = False) -> QLabel:
    made = QLabel(words)
    made.setObjectName(name)
    made.setWordWrap(wrap)
    return made


def _button(words: str, name: str, icon: str | None = None, kind: str = "") -> QPushButton:
    """A button of the editor: filled, or dressed by each word of `kind` (secondary, quiet, small,
    iconOnly)."""
    made = QPushButton(words)
    made.setObjectName(name)
    made.setAutoDefault(False)
    made.setCursor(Qt.CursorShape.PointingHandCursor)
    for prop in kind.split():
        made.setProperty(prop, True)
    if icon:
        icons.tint(made, icon)
    return made


def _icon_button(icon: str | None, name: str, tip: str) -> QPushButton:
    """An icon alone, in the text colour; None for one whose icon is drawn in another colour."""
    made = _button("", name, icon, "quiet iconOnly")
    made.setToolTip(tip)
    made.setAccessibleName(tip)
    made.setFixedSize(32, 32)
    return made


def leave_sheet(parent: QWidget, name: str, saved: bool) -> ConfirmSheet:
    """The one question on the way out of the editor with changes not saved: Save is the filled answer,
    Discard is outlined in red, Cancel and Keep are quiet."""
    return ConfirmSheet(
        parent,
        LEAVE_TITLE,
        (LEAVE_SAVED if saved else LEAVE_NEW).format(name=name),
        (("stay", CANCEL, "quiet"), ("discard", DISCARD, "outlined danger"), ("save", SAVE, "")),
        default="save",
        note=LEAVE_NOTE,
        width=LEAVE_WIDTH,
        left=("keep", KEEP, "quiet"),
    )


# A dozen hues after the five named accents, each readable as a colour in any look: the picker is a
# few good choices and a code box, not a colour wheel.
PICKER_HUES = (
    "#c0392b", "#d35400", "#e67e22", "#27ae60", "#16a085", "#2980b9",
    "#5c6bc0", "#8e44ad", "#7d3c98", "#f06292", "#789262", "#2c3e50",
)  # fmt: skip
PICKER_NOTE = "Pick a colour, or paste a code."
PICKER_USE, PICKER_CODE_HINT = "Use this colour", "Type a code such as #3a6cc1."
PICKER_PER_ROW = 9


class ColourDot(SwatchButton):
    """A round swatch with no name under it: the picker's colours are told apart by their colour, and
    each is named to a screen reader."""

    def __init__(self, colour: str, name: str) -> None:
        super().__init__("")
        self.fill, self.ink = colour, readable_ink(colour)
        self.setAccessibleName(name)
        self.setToolTip(name)

    def sizeHint(self) -> QSize:  # noqa: N802
        ring = self.SIZE + 2 * SPACING[0]
        return QSize(ring, ring)


class ColourSheet(Dialog):
    """Any colour, as a sheet over the editor: the five named accents and a dozen hues as round swatches,
    and a code box with a chip showing the colour. The editor wears each colour as it is tried; Cancel,
    Esc and the close button put the first colour back."""

    picked = Signal(str)

    def __init__(self, parent: QWidget, colour: str) -> None:
        super().__init__(parent, sheet=True)
        self.setObjectName("colourSheet")
        self._colour = colour
        box = self.card_body(ANY_COLOUR)
        box.addWidget(sheet_note(PICKER_NOTE))
        axis = "dark" if self.palette().color(QPalette.ColorRole.WindowText).lightness() > 128 else "light"
        named = [(name.capitalize(), ACCENT_COLORS[name][axis][0]) for name in ACCENTS]
        grid = QGridLayout()
        grid.setSpacing(SPACING[2])
        self.dots: list[ColourDot] = []
        for index, (name, hue) in enumerate((*named, *((hue, hue) for hue in PICKER_HUES))):
            dot = ColourDot(hue, name)
            dot.clicked.connect(self._dot_pressed)
            self.dots.append(dot)
            grid.addWidget(dot, index // PICKER_PER_ROW, index % PICKER_PER_ROW)
        box.addLayout(grid)
        line = QHBoxLayout()
        line.addWidget(_label("Code", "fieldLabel"))
        self.code = QLineEdit()
        self.code.setObjectName("colourCode")
        self.code.setMaxLength(7)
        self.code.setFixedWidth(120)
        self.code.setAccessibleName("Colour code")
        self.code.textEdited.connect(self._typed)
        line.addWidget(self.code)
        self.chip = QFrame()
        self.chip.setObjectName("colourChip")
        self.chip.setFixedSize(28, 28)
        line.addWidget(self.chip)
        line.addStretch(1)
        box.addLayout(line)
        self.use = sheet_button(PICKER_USE, "", "colourUse")
        self.use.setDefault(True)
        self.use.clicked.connect(self.accept)
        cancel = sheet_button("Cancel", "outlined", "colourCancel")
        cancel.clicked.connect(self.reject)
        sheet_footer(box, cancel, self.use)
        box.addWidget(WhyOff(self.use, PICKER_CODE_HINT))
        self._show(colour)

    def colour(self) -> str:
        return self._colour

    def _dot_pressed(self) -> None:
        # Its colour is read off the swatch pressed: a lambda naming the sheet kept it from being freed.
        colour = self.sender().fill
        self._show(colour)
        self.picked.emit(colour)

    def _typed(self, text: str) -> None:
        colour = hex_colour(text)
        self.use.setEnabled(colour is not None)
        if colour is not None:
            self._colour = colour
            self._ring(colour)
            self.chip.setStyleSheet(self._chip(colour))
            self.picked.emit(colour)

    def _show(self, colour: str) -> None:
        self._colour = colour
        self.code.setText(colour)
        self.use.setEnabled(True)
        self._ring(colour)
        self.chip.setStyleSheet(self._chip(colour))

    def _ring(self, colour: str) -> None:
        for dot in self.dots:
            dot.setChecked(dot.fill.lower() == colour.lower())

    @staticmethod
    def _chip(colour: str) -> str:
        return (
            f"QFrame#colourChip {{ background: {colour}; border: 1px solid rgba(0, 0, 0, 90); "
            "border-radius: 6px; padding: 0; }"
        )


class ColourField(QWidget):
    """A colour, shown as a swatch that opens the colour chooser and as a hex code that can be typed."""

    picked = Signal(str)

    def __init__(self, name: str) -> None:
        super().__init__()
        bare(self)
        self._name = name
        self._colour = "#000000"
        self._edge = "#808080"
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(SPACING[1])
        self.swatch = QPushButton()
        self.swatch.setObjectName("lookSwatch")
        self.swatch.setAutoDefault(False)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.setFixedSize(40, 32)
        self.swatch.setIconSize(QSize(32, 24))
        self.swatch.setToolTip(f"Choose the {name.lower()} colour")
        self.swatch.setAccessibleName(f"{name}, choose a colour")
        self.swatch.clicked.connect(self._choose)
        self.hex = QLineEdit()
        self.hex.setObjectName("lookHex")
        self.hex.setMaxLength(7)
        self.hex.setFixedWidth(108)
        self.hex.setAccessibleName(f"{name}, as a hex code")
        self.hex.textEdited.connect(self._typed)
        self.hex.editingFinished.connect(self._typed_done)
        line.addWidget(self.swatch)
        line.addWidget(self.hex)

    def show_colour(self, colour: str, edge: str | None = None, radius: int = 4) -> None:
        self._colour = colour
        self._edge = edge or self._edge
        self.swatch.setIcon(_colour_picture(colour, QSize(32, 24), self._edge, radius))
        if not self.hex.hasFocus():
            self.hex.setText(colour)
            self._problem(False)

    def _typed(self, text: str) -> None:
        colour = hex_colour(text)
        self._problem(colour is None)
        if colour is not None:
            self._colour = colour
            self.picked.emit(colour)

    def _typed_done(self) -> None:
        # What was typed and is not a colour gives way to the colour in use.
        self.hex.setText(self._colour)
        self._problem(False)

    def _problem(self, on: bool) -> None:
        if bool(self.hex.property("problem")) != on:
            self.hex.setProperty("problem", on)
            self.hex.style().unpolish(self.hex)
            self.hex.style().polish(self.hex)

    def _choose(self) -> None:
        """The colour sheet, the look following each colour tried; Cancel puts it back."""
        before = self._colour
        chooser = ColourSheet(self, before)
        chooser.picked.connect(self.picked)
        if chooser.exec() == QDialog.DialogCode.Accepted:
            self.picked.emit(chooser.colour())
        else:
            self.picked.emit(before)
        chooser.deleteLater()


class StartGrid(CardGrid):
    """The looks to start from, as cards in rows. The arrow keys move between the cards, Home and End go
    to the first and last, and a card takes Space or Enter itself."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        columns = max(self.columns(), 1)
        key = event.key()
        at = next((index for index, card in enumerate(self.cards) if card.hasFocus()), None)
        steps = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -columns, Qt.Key.Key_Down: columns}
        if at is None or (key not in steps and key not in (Qt.Key.Key_Home, Qt.Key.Key_End)):
            super().keyPressEvent(event)
            return
        if key == Qt.Key.Key_Home:
            target = 0
        elif key == Qt.Key.Key_End:
            target = len(self.cards) - 1
        else:
            target = at + steps[key]
        if 0 <= target < len(self.cards):
            self.cards[target].setFocus(Qt.FocusReason.TabFocusReason)
        event.accept()


class StartSheet(Dialog):
    """Start from: a small picture of every look, the ten as they come and then the student's own, as a
    sheet over the editor. The look worn now is ringed. Choosing a card closes the sheet with its token
    ("base:dark", "saved:Mine"); Esc and the close button leave the look as it was."""

    def __init__(self, parent: QWidget, token: str, saved: list[dict]) -> None:
        super().__init__(parent, sheet=True)
        self.setObjectName("startSheet")
        self._token = ""
        box = self.card_body(START_FROM, SHEET_PREVIEW)
        box.addWidget(sheet_note(START_NOTE))
        cards = []
        for base, words in BASE_LABELS.items():
            pack, preset = LOOK_BASES[base]
            look = {} if preset == "default" else {"preset": preset}
            cards.append(self._card(words, "", f"base:{base}", pack, look))
        for entry in saved:
            pack, look = look_choice(SAVED_PREFIX + entry["name"], saved)
            cards.append(self._card(entry["name"], START_YOURS, f"saved:{entry['name']}", pack, look))
        for card in cards:
            card.select(card.property("token") == token)
        self.looks = StartGrid(START_TILE + CARD_WIDTH_PAD)
        self.looks.setAccessibleName(START_FROM)
        self.looks.set_cards(cards)
        box.addWidget(self.looks)

    def _card(self, words: str, note: str, token: str, pack: str, look: dict) -> ChoiceCard:
        card = ChoiceCard(words, note, START_TILE)
        card.setProperty("token", token)
        card.set_picture(look_preview(pack, look, START_TILE))
        card.chosen.connect(self._chose)
        return card

    def token(self) -> str:
        return self._token

    def _chose(self) -> None:
        self._token = str(self.sender().property("token"))
        self.accept()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        worn = next((card for card in self.looks.cards if card.is_selected()), self.looks.cards[0])
        worn.setFocus(Qt.FocusReason.PopupFocusReason)


class CategoryRow(QWidget):
    """A category's colour: a hue on the family's lightness, which always reads, or an exact colour. Its
    sample block is drawn as the week draws the category's blocks."""

    changed = Signal(object)

    def __init__(self, key: str) -> None:
        super().__init__()
        bare(self)
        self.key = key
        info = CATEGORIES[key]
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(SPACING[1])
        head = QHBoxLayout()
        head.setSpacing(6)
        self.chip = QLabel("Aa")
        self.chip.setObjectName("lookChip")
        self.chip.setFixedSize(CHIP_SIZE)
        self.chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(self.chip)
        # Homework carries its book wherever its colour goes, so it is told by more than colour.
        self.book = QLabel() if key == "assignments" else None
        if self.book is not None:
            head.addWidget(self.book)
        name = _label(info["label"], "lookCategoryName")
        head.addWidget(name, 1)
        # In the caption size, as the mock-up sets it, so a row fits the column.
        self.exact = Switch(EXACT)
        self.exact.setObjectName(f"lookExact-{key}")
        self.exact.setProperty("exact", True)
        self.exact.setAccessibleName(f"{info['label']}: {EXACT.lower()}")
        policy = self.exact.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Fixed)
        self.exact.setSizePolicy(policy)
        self.exact.toggled.connect(self._exact_toggled)
        head.addWidget(self.exact)
        box.addLayout(head)
        self.hue = QSlider(Qt.Orientation.Horizontal)
        self.hue.setObjectName("lookHue")
        self.hue.setRange(0, 359)
        self.hue.setPageStep(15)
        self.hue.setAccessibleName(f"{info['label']} hue")
        self.hue.valueChanged.connect(lambda hue: self.changed.emit({"hue": hue}))
        box.addWidget(self.hue)
        self.colour = ColourField(info["label"])
        self.colour.picked.connect(lambda colour: self.changed.emit({"colour": colour}))
        box.addWidget(self.colour, 0, Qt.AlignmentFlag.AlignLeft)
        self._fill = "#ffffff"
        self._chip_sheet = ""

    def show_spec(self, spec: dict | None, look: dict, palette: dict, chrome: dict) -> None:
        """Shows the category as `look` draws it on `palette`; `chrome` is the editor's own colours."""
        fill, mark = category_paint(self.key, palette)
        self._fill = fill or "#ffffff"
        exact = isinstance(spec, dict) and "colour" in spec
        for widget in (self.exact, self.hue):
            widget.blockSignals(True)
        self.exact.setChecked(exact)
        hue = spec.get("hue") if isinstance(spec, dict) else None
        if hue is None:
            hue = oklch_of(spec["colour"])[2] if exact else CATEGORIES[self.key]["hue"]
        if not self.hue.isSliderDown():
            self.hue.setValue(round(hue) % 360)
        for widget in (self.exact, self.hue):
            widget.blockSignals(False)
        self.hue.setVisible(not exact)
        self.colour.setVisible(exact)
        measures = look_measures(look)
        radius = measures["radius"]
        self.colour.show_colour(self._fill, chrome["hairline_strong"], radius)
        drawn = block_paint(look, palette, fill, CATEGORIES[self.key]["kind"], mark)
        if drawn["mode"] == "outline":
            paint = f"background: {drawn['fill']}; border: 2px solid {drawn['outline']};"
        elif drawn["mode"] == "edge":
            width = measures["edge_width"] or EDGE_WIDTH
            paint = (
                f"background: {drawn['fill']}; border: none; border-left: {width}px solid {drawn['edge']};"
            )
        else:
            paint = f"background: {drawn['fill']}; border: none;"
        sheet = (
            f"QLabel#lookChip {{ {paint} color: {drawn['ink']}; border-radius: {radius}px; }}"
        )
        if sheet != self._chip_sheet:
            self._chip_sheet = sheet
            self.chip.setStyleSheet(sheet)
        if self.book is not None:
            ratio = self.devicePixelRatioF()
            self.book.setPixmap(icons.pixmap("book-open", mark or chrome["text"], 16, ratio))

    def _exact_toggled(self, on: bool) -> None:
        # From a hue to the exact colour it drew, or from a colour to its hue on the family.
        self.changed.emit({"colour": self._fill} if on else {"hue": round(oklch_of(self._fill)[2]) % 360})


class GroupCard(QFrame):
    """One group of settings as a card that folds, with its own Reset and a tag while it differs from
    how the look came."""

    def __init__(self, group: Group, open_: bool) -> None:
        super().__init__()
        self.setObjectName("settingsCard")
        self.group = group
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(SPACING[0], SPACING[0], SPACING[0], SPACING[0])
        head.setSpacing(SPACING[1])
        self.toggle = QPushButton()
        self.toggle.setObjectName("lookGroupToggle")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(open_)
        self.toggle.setAutoDefault(False)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setAccessibleName(group.name)
        self.toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        inside = QHBoxLayout(self.toggle)
        inside.setContentsMargins(2, 0, 2, 0)
        inside.setSpacing(SPACING[0])
        self.icon = QLabel()
        self.name = _label(group.name, "lookGroupName")
        self.tag = _label(CHANGED_TAG, "lookTag")
        self.tag.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.chevron = QLabel()
        for part in (self.icon, self.name, self.tag, self.chevron):
            part.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        inside.addWidget(self.icon)
        inside.addWidget(self.name)
        inside.addWidget(self.tag, 0, Qt.AlignmentFlag.AlignVCenter)
        inside.addStretch(1)
        inside.addWidget(self.chevron)
        head.addWidget(self.toggle, 1)
        self.reset = _button(RESET, f"lookReset-{group.key}", "rotate-ccw", "quiet small")
        self.reset.setIconSize(QSize(14, 14))
        self.reset.setToolTip(f"{RESET} {group.name.lower()}")
        self.reset.setAccessibleName(f"{RESET} {group.name}")
        head.addWidget(self.reset)
        box.addLayout(head)
        self.line = QWidget()
        self.line.setObjectName("lookGroupLine")
        self.line.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.line.setFixedHeight(1)
        box.addWidget(self.line)
        self.body = bare(QWidget())
        self.fields = QVBoxLayout(self.body)
        self.fields.setContentsMargins(SPACING[2], SPACING[3], SPACING[2], SPACING[3])
        self.fields.setSpacing(SPACING[2])
        box.addWidget(self.body)
        self.toggle.toggled.connect(self._fold)
        self._fold(open_)

    def _fold(self, open_: bool) -> None:
        self.body.setVisible(open_)
        self.line.setVisible(open_)

    def dress(self, chrome: dict) -> None:
        ratio = self.devicePixelRatioF()
        self.icon.setPixmap(icons.pixmap(self.group.icon, chrome["text"], 16, ratio))
        chevron = "chevron-up" if self.toggle.isChecked() else "chevron-down"
        self.chevron.setPixmap(icons.pixmap(chevron, chrome["muted"], 16, ratio))

    def show_changed(self, changed: bool) -> None:
        self.tag.setVisible(changed)
        self.reset.setEnabled(changed)


class Picture(QScrollArea):
    """The window as a picture: fitted to the room, or at its real size and scrolled."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("lookPicture")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.image = QLabel()
        self.image.setObjectName("lookPreviewImage")
        self.setWidget(self.image)
        overlay_scroll_bars(self)
        self.source = QPixmap()
        self.fit = True

    def show_picture(self, picture: QPixmap, fit: bool) -> None:
        self.source, self.fit = picture, fit
        self._lay_out()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._lay_out()

    def _lay_out(self) -> None:
        policy = Qt.ScrollBarPolicy.ScrollBarAlwaysOff if self.fit else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        self.setHorizontalScrollBarPolicy(policy)
        self.setVerticalScrollBarPolicy(policy)
        if self.source.isNull():
            return
        shown = self.source
        if self.fit:
            ratio = self.source.devicePixelRatio()
            room = self.viewport().size()
            shown = self.source.scaled(
                room * ratio, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            shown.setDevicePixelRatio(ratio)
        self.image.setPixmap(shown)
        self.image.resize(shown.deviceIndependentSize().toSize())


class LookEditor(QWidget):
    """The look editor. It says what to wear with `worn` (the device look and the saved looks) every
    time either changes, and `closed` when the student leaves it."""

    worn = Signal(dict, list)
    closed = Signal()

    def __init__(
        self, parent: QWidget | None, look: dict, saved: list[dict], pack: str, accent: str
    ) -> None:
        super().__init__(parent)
        self.setObjectName("lookEditor")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._pack, self._accent, self._dark = pack, accent, system_dark()
        self._before = sanitize_look(look)
        self._saved = [dict(entry) for entry in saved]
        self._draft = open_draft(pack, self._before, accent, self._saved)
        self._look = self._before
        self._palette: dict = {}
        self._chrome: dict = {}
        self._dressed: tuple | None = None
        self._rows_shown: tuple | None = None
        self._wear_pending = False
        self._worn_any = False
        self._fit = True
        self._bound: list[tuple[FieldPath, QWidget, Callable[[object], None]]] = []
        self._outs: list[QLabel] = []
        self._soon = QTimer(self)
        self._soon.setSingleShot(True)
        self._soon.setInterval(0)
        self._soon.timeout.connect(self._refresh)
        self._picture_soon = QTimer(self)
        self._picture_soon.setSingleShot(True)
        self._picture_soon.setInterval(0)
        self._picture_soon.timeout.connect(self._take_picture)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_head())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_column())
        body.addWidget(self._build_preview(), 1)
        outer.addLayout(body, 1)
        outer.addWidget(self._build_foot())
        self._change(self._draft, wear_it=False)
        self._refresh()

    # Building.

    def _build_head(self) -> QWidget:
        head = QWidget()
        head.setObjectName("lookEditorHead")
        head.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        head.setFixedHeight(60)
        line = QHBoxLayout(head)
        line.setContentsMargins(SPACING[2], 0, SPACING[3], 0)
        line.setSpacing(SPACING[3])
        self.back = _icon_button("arrow-left", "lookEditorBack", BACK_TIP)
        self.back.clicked.connect(self.leave)
        line.addWidget(self.back)
        line.addWidget(_label(TITLE, "lookEditorTitle"))
        line.addSpacing(SPACING[1])
        line.addWidget(_label(START_FROM, "lookInlineLabel"))
        self.start_from = _button("", "lookEditorFrom", None, "secondary")
        self.start_from.setMinimumWidth(200)
        self.start_from.clicked.connect(self._choose_start)
        line.addWidget(self.start_from)
        line.addWidget(_label(NAME, "lookInlineLabel"))
        self.name = QLineEdit()
        self.name.setObjectName("lookEditorName")
        self.name.setAccessibleName("Name of your look")
        self.name.setMaxLength(NAME_MAX)
        self.name.setFixedWidth(200)
        self.name.textEdited.connect(self._named)
        self.name.editingFinished.connect(self._rename)
        line.addWidget(self.name)
        self.duplicate = _icon_button("copy", "lookEditorDuplicate", "Duplicate")
        self.duplicate.clicked.connect(self._duplicate)
        # In the error colour, which `_dress` gives it.
        self.delete = _icon_button(None, "lookEditorDelete", "Delete")
        self.delete.clicked.connect(self._delete)
        line.addWidget(self.duplicate)
        line.addWidget(self.delete)
        line.addStretch(1)
        self.state = _label("", "lookEditorState")
        line.addWidget(self.state)
        return head

    def _build_column(self) -> QWidget:
        column = QScrollArea()
        column.setObjectName("lookEditorColumn")
        column.setWidgetResizable(True)
        column.setFrameShape(QFrame.Shape.NoFrame)
        column.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        column.setFixedWidth(COLUMN_WIDTH)
        overlay_scroll_bars(column)
        inner = bare(QWidget())
        cards = QVBoxLayout(inner)
        cards.setContentsMargins(SPACING[2], SPACING[2], SPACING[2], SPACING[3])
        cards.setSpacing(SPACING[2])
        cards.addWidget(self._build_readability())
        builders = {
            "colours": self._build_colours,
            "categories": self._build_categories,
            "shape": self._build_shape,
            "type": self._build_type,
            "blocks": self._build_blocks,
            "grid": self._build_grid,
            "motion": self._build_motion,
        }
        self.groups: dict[str, GroupCard] = {}
        for group in GROUPS:
            card = GroupCard(group, open_=group.key == "colours")
            card.reset.clicked.connect(lambda _checked=False, chosen=group: self._reset_group(chosen))
            card.toggle.toggled.connect(lambda _on, made=card: made.dress(self._chrome))
            builders[group.key](card.fields)
            self.groups[group.key] = card
            cards.addWidget(card)
        cards.addStretch(1)
        column.setWidget(inner)
        self.column = column
        return column

    def _build_readability(self) -> QWidget:
        card = QFrame()
        card.setObjectName("settingsCard")
        card.setAccessibleName(READABILITY)
        box = QVBoxLayout(card)
        box.setContentsMargins(SPACING[2], SPACING[2], SPACING[2], SPACING[2])
        box.setSpacing(SPACING[1])
        head = QHBoxLayout()
        head.addWidget(_label(READABILITY, "lookFieldLabel"))
        head.addStretch(1)
        self.fix_all = _button(FIX_ALL, "lookFixAll", kind="secondary small")
        self.fix_all.clicked.connect(self._fix_all)
        head.addWidget(self.fix_all)
        box.addLayout(head)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(SPACING[1])
        box.addLayout(self.rows)
        self.readability = card
        return card

    def _field(self, fields: QVBoxLayout, words: str, control: QWidget, out: str = "") -> QLabel:
        """A setting's name over its control, and at the right its value, `_sync` says which by `out`."""
        head = QHBoxLayout()
        head.addWidget(_label(words, "lookFieldLabel"))
        head.addStretch(1)
        said = _label("", "lookOut")
        said.setProperty("out", out)
        said.setVisible(bool(out))
        if out:
            self._outs.append(said)
        head.addWidget(said)
        fields.addLayout(head)
        fields.addWidget(control)
        return said

    def _segmented(self, path: FieldPath, choices: tuple[tuple[str, object], ...], name: str) -> Segmented:
        made = Segmented(choices, name)
        made.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        made.setAccessibleName(name)
        made.currentIndexChanged.connect(lambda _index, box=made: self._set(path, box.currentData()))
        self._bound.append((path, made, lambda value, box=made: box.setCurrentIndex(box.findData(value))))
        return made

    def _slider(self, path: FieldPath, name: str, low: int, high: int, step: int, scale: int = 1) -> QSlider:
        made = QSlider(Qt.Orientation.Horizontal)
        made.setObjectName(name)
        made.setRange(low, high)
        made.setSingleStep(step)
        made.setPageStep(step * 2)
        made.setAccessibleName(name)

        def moved(value: int) -> None:
            stepped = round(value / step) * step
            self._set(path, stepped / scale if scale != 1 else stepped)

        made.valueChanged.connect(moved)
        self._bound.append((path, made, lambda value, bar=made: bar.setValue(round(float(value) * scale))))
        return made

    def _switch(self, path: FieldPath, words: str, name: str) -> Switch:
        made = Switch(words)
        made.setObjectName(name)
        made.toggled.connect(lambda on: self._set(path, on))
        self._bound.append((path, made, lambda value, box=made: box.setChecked(bool(value))))
        return made

    def _colour(self, path: FieldPath, name: str) -> ColourField:
        made = ColourField(name)
        made.setObjectName(f"lookColour-{path[-1]}")
        made.picked.connect(lambda colour: self._set(path, colour))
        self._bound.append((path, made, lambda value, field=made: self._show_colour(field, str(value))))
        return made

    def _build_colours(self, fields: QVBoxLayout) -> None:
        # The swatches go in first, by `_build_accents`: High contrast's own yellow joins them.
        self.accents: Swatches | None = None
        accent = bare(QWidget())
        self.accent_box = QVBoxLayout(accent)
        self.accent_box.setContentsMargins(0, 0, 0, 0)
        self.accent_box.setSpacing(SPACING[1])
        any_line = QHBoxLayout()
        any_line.addWidget(_label(ANY_COLOUR, "lookNote"))
        # Its swatch and code box end where the other colours' do, so the column reads as one.
        any_line.addStretch(1)
        self.any_accent = ColourField("Accent")
        self.any_accent.setObjectName("lookColour-accent")
        self.any_accent.picked.connect(lambda colour: self._set(("accent",), colour))
        any_line.addWidget(self.any_accent)
        self.accent_box.addLayout(any_line)
        self._field(fields, "Accent", accent, "accent")
        for key, words in (("page", "Page"), ("card", "Cards"), ("text", "Text"), ("line", "Lines")):
            line = QHBoxLayout()
            line.addWidget(_label(words, "lookFieldLabel"))
            line.addStretch(1)
            line.addWidget(self._colour(("colours", key), words))
            fields.addLayout(line)
        fields.addWidget(_label(COLOURS_NOTE, "lookNote", wrap=True))

    def _build_categories(self, fields: QVBoxLayout) -> None:
        self.categories: dict[str, CategoryRow] = {}
        for key in CATEGORIES:
            row = CategoryRow(key)
            row.changed.connect(lambda spec, path=("categories", key): self._set(path, spec))
            self.categories[key] = row
            fields.addWidget(row)
        fields.addWidget(_label(CATEGORIES_NOTE, "lookNote", wrap=True))

    def _build_shape(self, fields: QVBoxLayout) -> None:
        low, high, _whole = CUSTOM_RANGES["corners"]
        self._field(fields, "Corners", self._slider(("corners",), "lookCorners", low, high, 1), "corners")
        spacing = (("Comfortable", "comfortable"), ("Compact", "compact"))
        self._field(fields, "Spacing", self._segmented(("spacing",), spacing, "lookSpacing"))
        shadows = (("None", "none"), ("Soft", "soft"), ("Bold", "bold"))
        self._field(fields, "Shadows", self._segmented(("shadows",), shadows, "lookShadows"))

    def _build_type(self, fields: QVBoxLayout) -> None:
        for path, words, name in (
            (("body_font",), "Text font", "lookBodyFont"),
            (("heading_font",), "Heading font", "lookHeadingFont"),
        ):
            faces = self._segmented(path, FACES, name)
            for button, (_words, face) in zip(faces.buttons(), FACES, strict=True):
                # Each face named in itself.
                button.setStyleSheet(f"font-family: {FONT_FAMILIES[face]};")
            self._field(fields, words, faces)
        sizes = self._segmented(("text_scale",), TEXT_SIZES, "lookTextSizes")
        self._field(fields, "Text size", sizes, "size")
        low, high, _whole = CUSTOM_RANGES["text_scale"]
        percent = self._slider(("text_scale",), "lookTextSize", round(low * 100), round(high * 100), 5, 100)
        fields.addWidget(percent)

    def _build_blocks(self, fields: QVBoxLayout) -> None:
        styles = (("Edge", "edge"), ("Filled", "filled"), ("Outline", "outline"))
        self._field(fields, "Block style", self._segmented(("blocks",), styles, "lookBlocks"))
        low, high, _whole = CUSTOM_RANGES["edge_width"]
        self.edge = self._slider(("edge_width",), "lookEdgeWidth", low, high, 1)
        self._field(fields, "Edge width", self.edge, "edge")
        self.edge_note = _label(EDGE_NOTE, "lookNote", wrap=True)
        fields.addWidget(self.edge_note)
        fields.addWidget(self._switch(("show_times",), "Show times", "lookShowTimes"))
        fields.addWidget(self._switch(("show_lengths",), "Show lengths", "lookShowLengths"))

    def _build_grid(self, fields: QVBoxLayout) -> None:
        hours = (("None", "none"), ("Faint", "faint"), ("Clear", "clear"))
        self._field(fields, "Hour lines", self._segmented(("hour_lines",), hours, "lookHourLines"))
        now = (("Accent", "accent"), ("Text colour", "text"))
        self._field(fields, "Line at the time now", self._segmented(("now_line",), now, "lookNowLine"))
        fields.addWidget(self._switch(("today_highlight",), "Today's highlight", "lookTodayHighlight"))

    def _build_motion(self, fields: QVBoxLayout) -> None:
        self._field(fields, "Motion", self._segmented(("motion",), MOTION_CHOICES, "lookMotion"))
        self.motion_note = _label("", "lookNote", wrap=True)
        fields.addWidget(self.motion_note)
        play = _button(PLAY, "lookPlayMotion", "circle-play", "secondary")
        play.clicked.connect(self._play)
        fields.addWidget(play, 0, Qt.AlignmentFlag.AlignLeft)

    def _build_preview(self) -> QWidget:
        right = bare(QWidget())
        box = QVBoxLayout(right)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        self.stage = QStackedWidget()
        self.stage.setObjectName("lookPreview")
        self.stage.setAccessibleName("Your week in this look")
        self.pictures = (Picture(), Picture())
        for picture in self.pictures:
            self.stage.addWidget(picture)
        box.addWidget(self.stage, 1)
        zoom = QWidget()
        zoom.setObjectName("lookEditorZoom")
        zoom.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        zoom.setFixedHeight(44)
        line = QHBoxLayout(zoom)
        line.setContentsMargins(SPACING[3], 0, SPACING[3], 0)
        self.zoom_note = _label(FIT_NOTE, "lookNote")
        line.addWidget(self.zoom_note)
        line.addStretch(1)
        self.zoom = Segmented((("Fit", True), ("Actual size", False)), "lookPreviewSize")
        self.zoom.setAccessibleName("Preview size")
        self.zoom.currentIndexChanged.connect(self._zoomed)
        line.addWidget(self.zoom)
        box.addWidget(zoom)
        return right

    def _build_foot(self) -> QWidget:
        foot = QWidget()
        foot.setObjectName("lookEditorFoot")
        foot.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        foot.setMinimumHeight(56)
        line = QHBoxLayout(foot)
        line.setContentsMargins(SPACING[2], SPACING[1], SPACING[3], SPACING[1])
        line.setSpacing(SPACING[1])
        self.reset_all = _button(RESET_ALL, "lookResetAll", "rotate-ccw", "outlined")
        self.reset_all.clicked.connect(lambda: self._change(replace(self._draft, look=self._named_start())))
        export = _button(EXPORT, "lookExport", "download", "outlined")
        export.clicked.connect(self._export)
        load = _button(IMPORT, "lookImport", "upload", "outlined")
        load.clicked.connect(self._import)
        for button in (self.reset_all, export, load):
            line.addWidget(button)
        # What Save, Export or Import has to say, between the two groups of buttons.
        message = bare(QWidget())
        said = QHBoxLayout(message)
        said.setContentsMargins(SPACING[1], 0, 0, 0)
        said.setSpacing(SPACING[1])
        self.message_icon = QLabel()
        self.message_text = _label("", "lookMessageText", wrap=True)
        self.message_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.dismiss = _icon_button("x", "lookMessageDismiss", "Dismiss")
        self.dismiss.clicked.connect(self._unsay)
        said.addWidget(self.message_icon)
        said.addWidget(self.message_text, 1)
        said.addWidget(self.dismiss)
        line.addWidget(message, 1)
        self._unsay()
        self.save_new = _button(SAVE_AS_NEW, "lookSaveAsNew", "plus", "outline")
        self.save_new.clicked.connect(lambda: self._save(None))
        self.done = _button(DONE, "lookEditorDone")
        self.done.clicked.connect(self.finish)
        line.addWidget(self.save_new)
        line.addWidget(self.done)
        return foot

    # What is shown.

    def _change(self, draft: Draft, *, wear_it: bool = True) -> None:
        """Take `draft` as the look being made; the screen, the window and the picture follow once the
        events waiting now are done, so a slider dragged across many values restyles the window once."""
        clean = sanitize_custom(draft.look)[0] or draft.look
        self._draft = replace(draft, look=clean)
        self._look = wear(self._before, clean)
        self._palette = resolved_palette(self._pack, self._dark, self._look, self._accent)
        self._wear_pending = self._wear_pending or wear_it
        self._soon.start()

    def _refresh(self) -> None:
        self._soon.stop()
        self._dress()
        self._sync()
        self._show_rows()
        if self._wear_pending:
            self._wear_pending = False
            self._worn_any = True
            self.worn.emit(self._look, [dict(entry) for entry in self._saved])
        self._picture_soon.start()

    def _dress(self) -> None:
        """The editor in the look it starts from, as that look comes: its controls stay readable whatever
        is chosen for the look being made."""
        base = self._draft.look["base"]
        dressed = (base, self._accent, self._dark)
        if dressed == self._dressed:
            return
        self._dressed = dressed
        plain = wear(self._before, {"name": UNNAMED, "base": base})
        self._chrome = resolved_palette(self._pack, self._dark, plain, self._accent)
        measures = look_measures(plain)
        art = control_art(self._chrome)
        sheet = pack_stylesheet(self._pack, self._dark, plain, self._accent, self._chrome, art)
        rules = editor_rules(self._chrome, measures["radius"])
        self.setStyleSheet(sheet + rules)
        # Wider with larger text, as High contrast's, so no card is cut at the column's edge.
        self.column.setFixedWidth(round(COLUMN_WIDTH * max(1.0, float(measures["scale"]))))
        self.delete.setIcon(icons.icon("trash", self._chrome["error"]))
        for card in self.groups.values():
            card.dress(self._chrome)
        self._build_accents(base in OWN_ACCENT)
        self._rows_shown = None

    def _build_accents(self, own: bool) -> None:
        """The accent swatches: High contrast's yellow first on High contrast, then the five."""
        if self.accents is not None and self.accents.property("own") == own:
            return
        if self.accents is not None:
            self.accents.setParent(None)
            self.accents.deleteLater()
        choices = tuple((ACCENT_LABELS.get(name, name.title()), name) for name in ACCENTS)
        if own:
            choices = (("Yellow", None), *choices)
        self.accents = Swatches(choices, "lookAccent")
        self.accents.setProperty("own", own)
        # Six swatches at High contrast's large text fit the column a step closer together.
        self.accents.layout().setSpacing(SPACING[1])
        self.accents.setAccessibleName("Accent")
        self.accents.currentIndexChanged.connect(
            lambda _index, box=self.accents: self._set(("accent",), box.currentData())
        )
        self.accent_box.insertWidget(0, self.accents, 0, Qt.AlignmentFlag.AlignLeft)

    def _show_colour(self, field: ColourField, colour: str) -> None:
        field.show_colour(colour, self._chrome.get("hairline_strong"), look_measures(self._look)["radius"])

    def _shown(self) -> dict[FieldPath, object]:
        """Every setting as the look draws it: what the student set, else its base's own."""
        custom, palette = self._draft.look, self._palette
        knobs, measures = effective_look(self._look), look_measures(self._look)
        faces = {family: face for face, family in FONT_FAMILIES.items()}
        shown: dict[FieldPath, object] = {
            ("colours", "page"): palette["window"],
            ("colours", "card"): palette["panel"],
            ("colours", "text"): palette["text"],
            ("colours", "line"): palette["hairline"],
            ("corners",): measures["card_radius"],
            ("spacing",): knobs["density"],
            ("shadows",): knobs["depth"],
            ("body_font",): faces.get(measures["body"], "sans"),
            ("heading_font",): faces.get(measures["heading"], "sans"),
            ("text_scale",): round(float(measures["scale"]), 2),
            ("blocks",): knobs["blocks"],
            ("edge_width",): measures["edge_width"] or EDGE_WIDTH,
            ("show_times",): measures["show_times"],
            ("show_lengths",): measures["show_lengths"],
            ("today_highlight",): measures["today_highlight"],
            ("hour_lines",): custom.get("hour_lines", "faint"),
            ("now_line",): custom.get("now_line", "accent"),
            ("motion",): look_motion(self._look),
        }
        return shown

    def _sync(self) -> None:
        """Every control in step with the look, except a field being typed in or a slider held."""
        shown = self._shown()
        for path, control, show in self._bound:
            if isinstance(control, QSlider) and control.isSliderDown():
                continue
            control.blockSignals(True)
            show(shown[path])
            control.blockSignals(False)
        custom, palette = self._draft.look, self._palette
        accent = custom.get("accent", None if custom["base"] in OWN_ACCENT else self._accent)
        if self.accents is not None:
            axis = palette["axis"]
            colours = {name: ACCENT_COLORS[name][axis] for name in ACCENTS}
            yellow = PRESET_PALETTES["high-contrast"]
            colours[None] = (yellow["accent"], yellow["accent_ink"])
            self.accents.set_colours(colours)
            self.accents.blockSignals(True)
            self.accents.setCurrentIndex(self.accents.findData(accent))
            self.accents.blockSignals(False)
        typed = self.accents is None or self.accents.currentIndex() < 0
        swatch = "Yellow" if accent is None else ACCENT_LABELS.get(str(accent), str(accent).title())
        self._show_colour(self.any_accent, palette["accent"])
        for key, row in self.categories.items():
            row.show_spec(setting(custom, ("categories", key)), self._look, palette, self._chrome)
        measures = look_measures(self._look)
        outs = {
            "accent": YOUR_COLOUR if typed else swatch,
            "corners": f"{shown[('corners',)]} px",
            "size": f"{round(float(measures['scale']) * 100)} %",
            "edge": f"{shown[('edge_width',)]} px",
        }
        for said in self._outs:
            said.setText(outs[said.property("out")])
        filled = shown[("blocks",)] == "filled"
        self.edge.setEnabled(not filled)
        self.edge_note.setVisible(filled)
        self.motion_note.setText(MOTION_NOTES[str(shown[("motion",)])])
        for card in self.groups.values():
            card.show_changed(self._draft.changed(card.group.fields))
        self.reset_all.setEnabled(self._draft.changed())
        self.state.setText(self._draft.state())
        saved_as = self._draft.saved_as
        self.duplicate.setVisible(saved_as is not None)
        self.delete.setVisible(saved_as is not None)
        if not self.name.hasFocus():
            self.name.setText(saved_as or str(custom.get("name") or UNNAMED))
        self._show_start_from()

    def _start_token(self) -> str:
        if self._draft.saved_as:
            return f"saved:{self._draft.saved_as}"
        return f"base:{self._draft.look['base']}"

    def _show_start_from(self) -> None:
        """The button names the look this one is, or started from."""
        kind, _sep, value = self._start_token().partition(":")
        name = BASE_LABELS.get(value, value) if kind == "base" else value
        self.start_from.setText(name)
        self.start_from.setAccessibleName(f"{START_FROM}: {name}")

    def _show_rows(self) -> None:
        rows = problem_rows(readability(self._draft.look, self._dark))
        shown = tuple((row.words, row.ink, row.ground) for row in rows)
        if shown == self._rows_shown:
            return
        self._rows_shown = shown
        while self.rows.count():
            gone = self.rows.takeAt(0).widget()
            if gone is not None:
                # Out of sight now; freed once the events waiting are done.
                gone.hide()
                gone.deleteLater()
        self.fix_all.setVisible(len(rows) > 1)
        ratio = self.devicePixelRatioF()
        if not rows:
            line = bare(QWidget())
            box = QHBoxLayout(line)
            box.setContentsMargins(0, 0, 0, 0)
            mark = QLabel()
            mark.setPixmap(icons.pixmap("circle-check", self._chrome["text"], 16, ratio))
            box.addWidget(mark)
            box.addWidget(_label(EVERYTHING_READS, "lookEverythingReads"), 1)
            self.rows.addWidget(line)
            return
        for row in rows[:READABILITY_ROWS]:
            line = bare(QWidget())
            box = QHBoxLayout(line)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(SPACING[1])
            mark = QLabel()
            mark.setPixmap(icons.pixmap("triangle-alert", self._chrome["text"], 16, ratio))
            pair = QLabel("Aa")
            pair.setObjectName("lookPair")
            pair.setFixedSize(PAIR_SIZE)
            pair.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pair.setStyleSheet(
                f"QLabel#lookPair {{ background: {row.ground}; color: {row.ink}; "
                f"border: 1px solid {self._chrome['hairline_strong']}; border-radius: 4px; }}"
            )
            words = _label(row.words, "lookWarnText", wrap=True)
            fix = _button(FIX, "lookFix", kind="secondary small")
            fix.setAccessibleName(f"{FIX}: {row.words}")
            fix.clicked.connect(lambda _checked=False, chosen=row: self._fix(chosen))
            box.addWidget(mark)
            box.addWidget(pair)
            box.addWidget(words, 1)
            box.addWidget(fix)
            self.rows.addWidget(line)
        if len(rows) > READABILITY_ROWS:
            more = MORE_ROWS.format(count=len(rows) - READABILITY_ROWS)
            self.rows.addWidget(_label(more, "lookNote", wrap=True))

    def _take_picture(self) -> None:
        """The window's own week page as the look dresses it, or, with no window about it, Today's app's
        week on the sample week."""
        week = self.window().findChild(QWidget, "weekPage") if self.window() is not self else None
        if week is not None:
            picture = week.grab()
        else:
            picture = render_preview("classic", None, self._pack, self._look, CANVAS.width(), CANVAS)
        for page in self.pictures:
            page.show_picture(picture, self._fit)

    def _zoomed(self, _index: int) -> None:
        self._fit = bool(self.zoom.currentData())
        self.zoom_note.setText(FIT_NOTE if self._fit else ACTUAL_NOTE)
        for page in self.pictures:
            page.show_picture(page.source, self._fit)

    def _play(self) -> None:
        """The look's motion on the picture: a page change as the app makes one at this level."""
        shown = self.stage.currentWidget()
        other = self.pictures[1 - self.pictures.index(shown)]
        for bar in ("horizontalScrollBar", "verticalScrollBar"):
            getattr(other, bar)().setValue(getattr(shown, bar)().value())
        switch_page(self.stage, other, str(self._shown()[("motion",)]), 1)

    def _say(self, words: str, *, problem: bool = False, detail: str = "") -> None:
        icon = "triangle-alert" if problem else "circle-check"
        self.message_icon.setPixmap(icons.pixmap(icon, self._chrome["text"], 16, self.devicePixelRatioF()))
        self.message_text.setText(words)
        self.message_text.setToolTip(detail)
        for part in (self.message_icon, self.message_text, self.dismiss):
            part.show()

    def _unsay(self) -> None:
        self.message_text.setText("")
        for part in (self.message_icon, self.message_text, self.dismiss):
            part.hide()

    def said(self) -> str:
        """What the line at the foot says now, empty when nothing."""
        return self.message_text.text() if self.message_text.isVisibleTo(self) else ""

    # What the student does.

    def _set(self, path: FieldPath, value: object) -> None:
        look = with_setting(self._draft.look, path, value)
        # A muted colour fixed against the text and the cards is theirs: new ones leave it to follow.
        text_or_card = path in (("colours", "text"), ("colours", "card"))
        if text_or_card and setting(self._draft.start, ("colours", "muted")) is None:
            look = with_setting(look, ("colours", "muted"), None)
        self._change(replace(self._draft, look=look))

    def _named_start(self) -> dict:
        return {**self._draft.start, "name": self._draft.look.get("name") or UNNAMED}

    def _reset_group(self, group: Group) -> None:
        look = self._draft.look
        for path in group.fields:
            look = with_setting(look, path, setting(self._draft.start, path))
        self._change(replace(self._draft, look=look))

    def _fix(self, row: Row) -> None:
        look = self._draft.look
        for problem in row.fixes:
            look = apply_fix(look, problem)
        self._change(replace(self._draft, look=look))

    def _fix_all(self) -> None:
        self._change(replace(self._draft, look=fix_all(self._draft.look, self._dark)))

    def _choose_start(self) -> None:
        """The sheet of pictures; a card chosen starts the look from it."""
        sheet = StartSheet(self, self._start_token(), self._saved)
        if sheet.exec() == QDialog.DialogCode.Accepted:
            self._start_from(sheet.token())
        sheet.deleteLater()

    def _start_from(self, token: str) -> None:
        """Another look to start from: one of the ten as it comes, under the name given so far, or a
        saved look to change. As the mock-up draws it, what was not saved is left behind."""
        kind, _sep, value = token.partition(":")
        self._unsay()
        if kind == "saved":
            kept = next((entry for entry in self._saved if entry["name"] == value), None)
            if kept is not None:
                self._change(Draft(dict(kept), dict(kept), kept["name"]))
        elif kind == "base":
            name = self._draft.look.get("name") if self._draft.saved_as is None else UNNAMED
            fresh = reset_look({"name": name or UNNAMED, "base": value})
            self._change(Draft(fresh, dict(fresh)))

    def _named(self, text: str) -> None:
        """A new look takes its name as it is typed, and wears it when the typing is done; a saved one is
        renamed then. Restyling the window for each letter would make typing lag."""
        if self._draft.saved_as is None:
            name = " ".join(text.split())[:NAME_MAX] or UNNAMED
            self._change(replace(self._draft, look={**self._draft.look, "name": name}), wear_it=False)

    def _rename(self) -> None:
        old = self._draft.saved_as
        if old is None:
            self._change(self._draft)
            return
        wanted = self.name.text()
        if " ".join(wanted.split()) == old:
            return
        try:
            saved = rename_look(self._saved, old, wanted)
        except LookNameError as error:
            self.name.setText(old)
            self._say(str(error), problem=True)
            return
        at = next(index for index, entry in enumerate(self._saved) if entry["name"] == old)
        self._saved = saved
        new = saved[at]["name"]
        self._change(Draft({**self._draft.look, "name": new}, {**self._draft.start, "name": new}, new))

    def _save(self, name: str | None) -> bool:
        """Keep the look under `name`, in that saved look's place, or else as a new saved look under the
        name it was given, numbered if another saved look has it."""
        try:
            chosen = name or free_name(self._saved, self._draft.look.get("name") or UNNAMED)
            self._saved = save_look(self._saved, self._draft.look, chosen)
        except LookNameError as error:
            self._say(str(error), problem=True)
            return False
        look = {**self._draft.look, "name": chosen}
        self._change(Draft(look, dict(look), chosen))
        return True

    def _duplicate(self) -> None:
        if self._draft.saved_as is None:
            return
        self._saved, copy = duplicate_look(self._saved, self._draft.saved_as)
        self._change(self._draft)
        self._say(COPIED.format(name=copy))

    def _delete(self) -> None:
        name = self._draft.saved_as
        if name is None or not confirm(self, DELETE_TITLE, DELETE_QUESTION.format(name=name), "Delete"):
            return
        self._saved = delete_look(self._saved, name)
        # The look stays on, as a new one with nothing saved of it.
        look = {**self._draft.look, "name": UNNAMED}
        self._change(Draft(look, reset_look(look)))

    def export_to(self, path: Path) -> bool:
        name = self._draft.saved_as or str(self._draft.look.get("name") or UNNAMED)
        try:
            path.write_text(export_look({**self._draft.look, "name": name}), encoding="utf-8")
        except OSError as error:
            self._say(WRITE_FAILED, problem=True, detail=str(error))
            return False
        self._say(EXPORTED.format(name=name))
        return True

    def import_from(self, path: Path) -> bool:
        """Read a look file into the saved looks and start changing it; a file that is not one says so."""
        try:
            with path.open("rb") as stream:
                text = stream.read(FILE_MAX_BYTES + 1)
        except OSError as error:
            self._say(NOT_OPENED, problem=True, detail=str(error))
            return False
        read = import_look(text)
        if read.look is None:
            self._say(read.problems[0], problem=True, detail=" ".join(read.problems))
            return False
        try:
            name = free_name(self._saved, read.look.get("name") or UNNAMED)
        except LookNameError:
            name = free_name(self._saved, UNNAMED)
        self._saved = save_look(self._saved, read.look, name)
        look = {**read.look, "name": name}
        self._change(Draft(look, dict(look), name))
        words = IMPORTED.format(name=name)
        self._say(" ".join((words, *read.problems[:1])), detail=" ".join(read.problems))
        return True

    def _export(self) -> None:
        name = self._draft.saved_as or str(self._draft.look.get("name") or UNNAMED)
        suggested = f"{file_stem(name)}.flexweek-look.json"
        chosen, _kind = QFileDialog.getSaveFileName(self, EXPORT_TITLE, suggested, LOOK_FILES)
        if chosen:
            self.export_to(Path(chosen))

    def _import(self) -> None:
        chosen, _kind = QFileDialog.getOpenFileName(self, IMPORT_TITLE, "", f"{LOOK_FILES};;All files (*)")
        if chosen:
            self.import_from(Path(chosen))

    # Leaving.

    def finish(self) -> None:
        """Done: the look kept under the name it was given, then back to Settings."""
        if self._draft.changed() and not self._save(self._draft.saved_as):
            return
        self._close()

    def leave(self) -> None:
        """Back or Esc: straight out when everything is saved; asked once, when it is not, whether to
        save the changes, keep them on without saving, or go back to the look as it was."""
        if not self._draft.changed():
            self._close()
            return
        answer = self.ask_leave()
        if answer == "save":
            if self._save(self._draft.saved_as):
                self._close()
        elif answer == "keep":
            self._close()
        elif answer == "discard":
            self._close(self.discarded())

    def discarded(self) -> dict:
        """The look to wear once the changes not saved are let go: the saved look as it was saved, or
        else the look worn before any look of the student's own was put on."""
        kept = next((entry for entry in self._saved if entry["name"] == self._draft.saved_as), None)
        if kept is not None:
            return wear(self._before, kept)
        return sanitize_look({key: value for key, value in self._before.items() if key != "custom"})

    def ask_leave(self) -> str | None:
        """"save", "keep" or "discard", or None to stay in the editor."""
        draft = self._draft
        name = draft.saved_as or str(draft.look.get("name") or UNNAMED)
        sheet = leave_sheet(self, name, draft.saved_as is not None)
        sheet.exec()
        return sheet.answer if sheet.answer in ("save", "keep", "discard") else None

    def _close(self, look: dict | None = None) -> None:
        if self._soon.isActive():
            self._refresh()
        draft = self._draft
        untouched = draft.saved_as is None and not draft.changed() and "custom" not in self._before
        same_base = draft.look["base"] == base_of(self._pack, self._before)
        if look is None and untouched and same_base and self._worn_any:
            # Nothing was made from the look worn before: it stays the look it was, not a copy of it.
            look = self._before
        if look is not None:
            self.worn.emit(look, [dict(entry) for entry in self._saved])
        self.closed.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.leave()
            return
        super().keyPressEvent(event)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._picture_soon.start()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        # The week page is the window's size too; it is laid out again first.
        self._picture_soon.start()
