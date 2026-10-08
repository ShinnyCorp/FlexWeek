"""Main view and Day screen pickers, built from the registry so a new design needs no code here.

Each is a card: the designs as pictures, the standard ones first and the experimental ones under a
heading, then the picked design's Style options. Fine-tune waits behind one switch so the first look
stays short.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.native.layouts.base import empty
from desktop.native.layouts.registry import (
    LAYOUTS,
    LEVELS,
    MATCH,
    layouts_for,
    options_for,
)
from desktop.native.motion import OVER_MS, duration
from desktop.native.previews import Previews
from desktop.native.widgets import (
    CARD_GAP,
    CARD_WIDTH_PAD,
    CardGrid,
    ChoiceCard,
    Choices,
    Form,
    Segmented,
    Switch,
)

SLOTS = (
    ("main", "plan", "Main view", "Where you plan your week."),
    ("day", "day", "Day screen", "What you watch once the plan is made. Open it with My day."),
)
DESIGN_LINE = (
    "A design is how FlexWeek lays out your week. Your blocks and homework are the same in every one."
)
# A design in colours of its own wears them on its page only, so it says what keeps the student's,
# under the colours it is about.
COLOUR_NOTE = "Only the design's page takes these colours. The rest of FlexWeek keeps your Look and Accent."
# The width setup's design cards are drawn at, so a picture drawn for one is ready for the other.
PICTURE_WIDTH = 206
EXPERIMENTAL_TAG = "Experimental"
# A choice of more than this many is a dropdown; up to it, the choices sit side by side.
SEGMENTED_MOST = 3
# A moment past the slide before the first design picture is drawn, so its last frame is not caught.
PICTURES_AFTER_SLIDE_MS = 40


class DesignGrid(CardGrid):
    """Design cards share the row, as the look grids do. At a fixed picture width the row ended
    about 220 px short of the card beside it."""

    def __init__(self, card_width: int, gap: int, on_width: Callable[[ChoiceCard, int], None]) -> None:
        super().__init__(card_width, gap)
        self._on_width = on_width

    def _place(self, room: int) -> None:
        super()._place(room)
        columns = self.columns()
        if not columns:
            return
        picture = (room - (columns - 1) * self._gap) // columns - CARD_WIDTH_PAD
        for card in self.cards:
            if card.picture.width() != picture:
                card.set_width(picture)
                self._on_width(card, picture)


class DesignPicker(Choices):
    """The designs for one role as cards with a picture of each, answering a dropdown's calls."""

    def __init__(self, role: str, name: str, title: str, pack: str) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setProperty("designs", True)
        self.setAccessibleName(title)
        self._pack = pack
        self.cards: list[ChoiceCard] = []
        self._drawn: dict[int, int] = {}
        self._waiting: list[int] = []
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        # One grid for every design, the standard ones first, so its rows are full: with the
        # experimental ones under a heading of their own, Clay deck and Day screen's last card each
        # stood alone (Grok Bot's 0.17.0 audit, T34).
        self._grid = DesignGrid(PICTURE_WIDTH + CARD_WIDTH_PAD, CARD_GAP, self._width_changed)
        for spec in sorted(layouts_for(role), key=lambda spec: spec.experimental):
            index = self._remember(spec.label, spec.id)
            tag = EXPERIMENTAL_TAG if spec.experimental else ""
            card = ChoiceCard(spec.label, spec.summary, PICTURE_WIDTH, tag)
            card.setProperty("index", index)
            card.chosen.connect(self._card_chosen)
            self.cards.append(card)
        self._grid.set_cards(self.cards)
        box.addWidget(self._grid)
        # Drawn one at a time once the page is up, as setup does, so Settings opens at once. The
        # first waits until the page has slid in at the slowest level: each picture takes over
        # 100 ms, and drawn from the start they left Settings' first slide three frames.
        self._waiting = list(range(len(self.cards)))
        QTimer.singleShot(duration(OVER_MS, "extra") + PICTURES_AFTER_SLIDE_MS, self._draw_next)

    def _width_changed(self, card: ChoiceCard, width: int) -> None:
        index = int(card.property("index"))
        drawn = self._drawn.get(index)
        if drawn is None or drawn == width or index in self._waiting:
            return
        self._waiting.append(index)
        QTimer.singleShot(0, self._draw_next)

    def _card_chosen(self) -> None:
        self.setCurrentIndex(int(self.sender().property("index")))

    def _draw_next(self) -> None:
        if not self._waiting:
            return
        index = self._waiting.pop(0)
        layout_id = str(self._data[index])
        colourways = LAYOUTS[layout_id].colourways
        colour = colourways[0][0] if colourways else None
        card = self.cards[index]
        width = card.picture.width()
        card.set_picture(Previews().get(layout_id, colour, self._pack, None, width))
        self._drawn[index] = width
        if self._waiting:
            QTimer.singleShot(0, self._draw_next)

    def _show(self, index: int) -> None:
        for at, card in enumerate(self.cards):
            card.select(at == index)


class LayoutSection(QFrame):
    """One pick and the options of whatever is picked, as a card. Each design keeps its own settings
    while Settings is open, so trying another design and coming back loses nothing."""

    changed = Signal()

    def __init__(
        self, slot: str, role: str, title: str, blurb: str, choice: dict, pack: str = "system"
    ) -> None:
        super().__init__()
        self.slot = slot
        self.setObjectName("settingsCard")
        self._options = {spec.id: options_for(choice, spec.id) for spec in layouts_for(role)}
        self._colour_note: QLabel | None = None
        body = QVBoxLayout(self)
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName(f"layout{slot.title()}Heading")
        body.addWidget(heading)
        lines = (DESIGN_LINE, blurb) if slot == "main" else (blurb,)
        for line in lines:
            # Wrapped, or its one long line sets the width of the whole Settings page.
            intro = QLabel(line)
            intro.setObjectName("settingsCardNote")
            intro.setWordWrap(True)
            body.addWidget(intro)
        self.pick = DesignPicker(role, f"layout{slot.title()}", title, pack)
        self.pick.setCurrentIndex(max(self.pick.findData(choice[slot]), 0))
        body.addWidget(self.pick)
        self._form_host = QWidget()
        self._form_host.setObjectName("settingsRow")
        self._form = Form(self._form_host)
        # A long option drops its choices under its name rather than pushing the page wider than the
        # room it has.
        self._form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._form.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self._form_host)
        self.more = Switch("Show more options for this design")
        self.more.setObjectName(f"layout{slot.title()}More")
        body.addWidget(self.more)
        self.reset = QPushButton("Reset this layout's options")
        self.reset.setObjectName(f"layout{slot.title()}Reset")
        self.reset.setProperty("outline", True)
        reset_row = QHBoxLayout()
        reset_row.addWidget(self.reset)
        reset_row.addStretch(1)
        body.addLayout(reset_row)
        self.pick.currentIndexChanged.connect(lambda _index: (self._rebuild(True), self.changed.emit()))
        self.more.toggled.connect(lambda _on: self._rebuild(False))
        self.reset.clicked.connect(self._reset)
        self._rebuild(True)

    def chosen(self) -> str:
        return str(self.pick.currentData())

    def sync(self, choice: dict) -> None:
        """Every design's options as kept now. Settings stays built between opens, and an option
        changed on a design's own page meanwhile, as Timeline's fold, would otherwise be written back
        as it was."""
        self._options = {layout_id: options_for(choice, layout_id) for layout_id in self._options}
        self._rebuild(True)

    def values(self) -> dict[str, str]:
        """Every option of the design picked now, defaults included."""
        return dict(self._options[self.chosen()])

    def options(self) -> dict[str, dict[str, str]]:
        """Only what the student changed. Writing a design's defaults down would freeze them, and a
        default that later improves would never reach anyone who had opened this dialog."""
        changed = {}
        for layout_id, values in self._options.items():
            shipped = options_for(None, layout_id)
            differs = {key: value for key, value in values.items() if value != shipped[key]}
            if differs:
                changed[layout_id] = differs
        return changed

    def _reset(self) -> None:
        self._options[self.chosen()] = options_for(None, self.chosen())
        self._rebuild(True)
        self.changed.emit()

    def _rebuild(self, fresh: bool) -> None:
        spec = LAYOUTS[self.chosen()]
        values = self._options[spec.id]
        detail = [option for option in spec.options if option.level == "detail"]
        if fresh:
            # Fine-tuning that is already in use must not be hidden from the student who set it.
            self.more.blockSignals(True)
            self.more.setChecked(any(values[option.key] != option.default for option in detail))
            self.more.blockSignals(False)
        self.more.setVisible(bool(detail))
        self.reset.setVisible(bool(spec.options))
        empty(self._form)
        self._colour_note = None
        for level, heading in LEVELS:
            rows = [option for option in spec.options if option.level == level]
            if not rows or (level == "detail" and not self.more.isChecked()):
                continue
            title = QLabel(heading)
            title.setObjectName(f"layout{self.slot.title()}Level-{level}")
            self._form.addRow(title)
            for option in rows:
                name = f"layout{self.slot.title()}-{option.key}"
                box: QComboBox | Segmented
                if option.key == "colour" or len(option.choices) > SEGMENTED_MOST:
                    box = QComboBox()
                    box.setObjectName(name)
                else:
                    box = Segmented(name=name)
                for entry in option.choices:
                    box.addItem(entry.label, entry.value)
                box.blockSignals(True)
                box.setCurrentIndex(max(box.findData(values[option.key]), 0))
                box.blockSignals(False)
                box.currentIndexChanged.connect(
                    lambda _index, key=option.key, source=box, target=spec.id: self._options[
                        target
                    ].__setitem__(key, str(source.currentData()))
                )
                box.currentIndexChanged.connect(lambda _index: self.changed.emit())
                self._form.addRow(option.label, box)
                if option.key == "colour":
                    self._colour_note = QLabel(COLOUR_NOTE)
                    self._colour_note.setObjectName(f"layout{self.slot.title()}ColourNote")
                    self._colour_note.setWordWrap(True)
                    self._form.addRow("", self._colour_note)
                    box.currentIndexChanged.connect(self._sync_colour_note)
        self._sync_colour_note()

    def _sync_colour_note(self, *_index: object) -> None:
        if self._colour_note is not None:
            self._form.setRowVisible(self._colour_note, self._options[self.chosen()].get("colour") != MATCH)
