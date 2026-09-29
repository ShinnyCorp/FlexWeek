"""Every control takes the design's colours, and none of them disappears on a dark palette.

Left to Fusion, an unticked box, an unselected radio button and a spin box's arrows could not be seen
on dark-frost, the dropdown list kept Fusion's grey, and menu section headings were never drawn.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QLabel,
        QMenu,
        QRadioButton,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )

    from desktop.native.layouts.registry import tokens_for
    from desktop.native.look import mix, pack_stylesheet, palette_from_tokens, resolved_palette
    from desktop.native.widgets import Switch, add_heading, control_art


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-controls-test"])


def palettes() -> dict[str, tuple[str, bool, dict]]:
    light = resolved_palette("light-frost", False, None)
    high_contrast = {"preset": "high-contrast", "knobs": {}}
    return {
        "light-frost": ("light-frost", False, light),
        "dark-frost": ("dark-frost", True, resolved_palette("dark-frost", True, None)),
        "high-contrast": ("system", False, resolved_palette("system", False, high_contrast)),
        # A design's page in its own dark colours, which the controls on it wear.
        "bento-midnight": (
            "light-frost",
            False,
            palette_from_tokens(tokens_for("bento", "midnight", light), light),
        ),
    }


def styled(qapp: QApplication, name: str) -> tuple[QWidget, dict]:
    pack, dark, palette = palettes()[name]
    page = QWidget()
    page.setStyleSheet(pack_stylesheet(pack, dark, None, "default", palette, control_art(palette)))
    QVBoxLayout(page)
    return page, palette


def marks(image: QImage, background: str, columns: range) -> int:
    """Pixels in `columns` that stand out from `background`: what a student can actually see."""
    base = QColor(background).lightness()
    return sum(
        1
        for x in columns
        for y in range(image.height())
        if x < image.width() and abs(image.pixelColor(x, y).lightness() - base) > 40
    )


@pytest.mark.parametrize("name", ["light-frost", "dark-frost", "high-contrast", "bento-midnight"])
def test_an_unticked_box_and_an_unselected_radio_button_can_be_seen(qapp: QApplication, name: str) -> None:
    page, palette = styled(qapp, name)
    box, radio = QCheckBox("Play a sound"), QRadioButton("I'll place it")
    page.layout().addWidget(box)
    page.layout().addWidget(radio)
    page.show()
    qapp.processEvents()
    for control in (box, radio):
        assert marks(control.grab().toImage(), palette["window"], range(0, 22)) >= 20, (name, control.text())
    box.setChecked(True)
    qapp.processEvents()
    ticked = box.grab().toImage()
    accent = QColor(palette["accent"]).name()
    filled = sum(
        1 for x in range(0, 20) for y in range(ticked.height()) if ticked.pixelColor(x, y).name() == accent
    )
    assert filled >= 80, (name, filled)
    page.close()


@pytest.mark.parametrize("name", ["light-frost", "dark-frost", "high-contrast", "bento-midnight"])
def test_a_spin_box_shows_its_arrows(qapp: QApplication, name: str) -> None:
    page, palette = styled(qapp, name)
    spin = QSpinBox()
    spin.setValue(25)
    page.layout().addWidget(spin)
    page.resize(240, 60)
    page.show()
    qapp.processEvents()
    image = spin.grab().toImage()
    # In the design's muted ink, not only visible: Fusion's own arrows showed offscreen but took the
    # desktop palette on KDE and vanished on dark-frost there.
    # A thin chevron is smoothed into the field, so its strokes are the ink at most of its strength:
    # bright ink on High contrast's black comes out 70 % of the way, which a fixed distance missed.
    inks = [QColor(mix(palette["muted"], palette["field"], share / 100)) for share in range(60, 101, 5)]

    def near(colour: QColor) -> bool:
        return any(
            max(
                abs(colour.red() - ink.red()),
                abs(colour.green() - ink.green()),
                abs(colour.blue() - ink.blue()),
            )
            < 40
            for ink in inks
        )

    arrows = sum(
        1
        for x in range(image.width() - 22, image.width() - 4)
        for y in range(image.height())
        if near(image.pixelColor(x, y))
    )
    assert arrows >= 6, (name, arrows)
    page.close()


@pytest.mark.parametrize("name", ["light-frost", "dark-frost", "high-contrast", "bento-midnight"])
def test_a_dropdown_list_uses_the_design_and_marks_the_choice(qapp: QApplication, name: str) -> None:
    page, palette = styled(qapp, name)
    combo = QComboBox()
    combo.addItems(["Calendar · Today's app", "Agenda · Timeline", "Dashboard · Bento"])
    combo.setCurrentIndex(2)
    page.layout().addWidget(combo)
    page.resize(320, 80)
    page.show()
    qapp.processEvents()
    combo.showPopup()
    for _ in range(5):
        qapp.processEvents()
    view = combo.view()
    image = view.grab().toImage()

    def accent_share(row: int) -> float:
        rect = view.visualRect(view.model().index(row, 0))
        accent = QColor(palette["accent"]).name()
        hits = sum(
            1
            for x in range(rect.left(), rect.right())
            if image.pixelColor(x, rect.center().y()).name() == accent
        )
        return hits / max(rect.width(), 1)

    assert accent_share(2) > 0.6, name
    assert accent_share(0) < 0.05, name
    combo.hidePopup()
    page.close()


def test_a_menu_heading_is_drawn_as_text(qapp: QApplication) -> None:
    """Fusion drew `addSection` as a plain line, so More never showed Adding or Planning."""
    page, _palette = styled(qapp, "light-frost")
    menu = QMenu(page)
    add_heading(menu, "Adding")
    menu.addAction("Add homework")
    menu.popup(page.mapToGlobal(page.rect().center()))
    for _ in range(5):
        qapp.processEvents()
    heading = menu.findChild(QLabel, "menuHeading")
    assert heading is not None and heading.text() == "Adding"
    assert heading.isVisible() and heading.height() >= heading.fontMetrics().height()
    menu.hide()


def view_control(qapp: QApplication, pack: str, dark: bool, look: dict | None) -> tuple[QImage, dict, list]:
    """Day, Week and Month as the top bar builds them, Week chosen, in a look."""
    from PySide6.QtWidgets import QHBoxLayout

    from desktop.native.widgets import Segment, SegmentTrack

    palette = resolved_palette(pack, dark, look)
    page = QWidget()
    page.setStyleSheet(pack_stylesheet(pack, dark, look, "default", palette, control_art(palette)))
    track = SegmentTrack(page)
    track.setObjectName("segments")
    QHBoxLayout(track)
    buttons = []
    for name, words in (("viewDay", "Day"), ("viewWeek", "Week"), ("viewMonth", "Month")):
        button = Segment(words)
        button.setObjectName(name)
        button.setCheckable(True)
        button.setChecked(name == "viewWeek")
        track.add(button)
        buttons.append(button)
    track.adjustSize()
    page.resize(track.size())
    page.show()
    qapp.processEvents()
    return track.grab().toImage(), palette, [button.geometry() for button in buttons]


def test_high_contrasts_choices_in_settings_read_every_one_and_fill_the_chosen_one(
    qapp: QApplication,
) -> None:
    """Settings' two- and three-way choices, as the top bar's: in High contrast every choice in the
    text colour on the page and the chosen one filled with the accent. Yellow on grey could not be
    read."""
    from desktop.native.widgets import Segmented

    look = {"preset": "high-contrast", "knobs": {}}
    palette = resolved_palette("system", False, look)
    page = QWidget()
    page.setStyleSheet(pack_stylesheet("system", False, look, "default", palette, control_art(palette)))
    choice = Segmented((("Light", "light"), ("Dark", "dark"), ("System", "system")), "lookChoice")
    choice.setParent(page)
    choice.setCurrentIndex(1)
    choice.adjustSize()
    page.resize(choice.size())
    page.show()
    qapp.processEvents()
    image = choice.grab().toImage()
    light, dark, _system = (button.geometry() for button in choice.buttons())
    assert image.pixelColor(dark.left() + 6, dark.center().y()).name() == palette["accent"]
    assert image.pixelColor(light.left() + 6, light.center().y()).name() == palette["window"]
    words = {
        image.pixelColor(x, y).name()
        for x in range(light.left(), light.right())
        for y in range(light.top(), light.bottom())
    }
    assert palette["text"] in words


def test_high_contrasts_view_control_reads_every_choice_and_fills_the_chosen_one(qapp: QApplication) -> None:
    """Yellow on light grey could not be read. Every segment is in the text colour on the page, and the
    chosen one is filled with the accent and written in its ink."""
    image, palette, (day, week, _month) = view_control(
        qapp, "system", False, {"preset": "high-contrast", "knobs": {}}
    )
    # Inside each pill's rounded ends, on its middle line.
    assert image.pixelColor(week.left() + 6, week.center().y()).name() == palette["accent"] == "#ffd400"
    assert image.pixelColor(day.left() + 6, day.center().y()).name() == palette["window"]

    def inks(box) -> set[str]:
        columns, rows = range(box.left(), box.right()), range(box.top(), box.bottom())
        return {image.pixelColor(x, y).name() for x in columns for y in rows}

    assert max(inks(day)) == palette["text"], max(inks(day))
    assert palette["accent_ink"] in inks(week)


@pytest.mark.parametrize("text", ["normal", "large"])
def test_a_switch_as_tall_as_it_asks_shows_every_line_of_its_words(qapp: QApplication, text: str) -> None:
    """The style centred the toggle in the whole switch and the words were drawn from the toggle, so
    words that wrapped began halfway down and lost their last line below the switch's foot."""
    look = {"preset": "default", "knobs": {"text": text}}
    palette = resolved_palette("light-frost", False, look)
    sheet = pack_stylesheet("light-frost", False, look, "default", palette, control_art(palette))
    words = "Remind before starting"

    def drawn(width: int, height: int) -> QImage:
        page = QWidget()
        page.setStyleSheet(sheet)
        Switch(words, page).setGeometry(0, 0, width, height)
        page.resize(width, height)
        page.show()
        qapp.processEvents()
        image = page.grab().toImage()
        page.close()
        return image

    def ink(image: QImage) -> int:
        return marks(image, palette["window"], range(image.width()))

    page = QWidget()
    page.setStyleSheet(sheet)
    switch = Switch(words, page)
    switch.ensurePolished()
    least, most = switch.minimumSizeHint(), switch.sizeHint()
    # Room for the longest word only, so no two of the three words share a line.
    narrow = least.width()
    tall = switch.heightForWidth(narrow)
    roomy = drawn(narrow, 4 * tall)
    background = QColor(palette["window"]).lightness()
    inked = [
        y
        for y in range(roomy.height())
        if any(abs(roomy.pixelColor(x, y).lightness() - background) > 40 for x in range(roomy.width()))
    ]
    assert inked[-1] - inked[0] > 2 * switch.fontMetrics().lineSpacing(), (text, "the words take three lines")
    assert ink(drawn(narrow, tall)) == ink(roomy), (text, "every line shows at heightForWidth", tall)
    one_line = drawn(most.width(), most.height())
    assert ink(one_line) == ink(drawn(most.width(), 4 * most.height())), (text, "sizeHint shows them", most)
    assert least.height() == most.height(), (text, "the least it asks for is one whole line", least, most)
