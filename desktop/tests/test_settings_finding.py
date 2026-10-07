"""Finding things in Settings (0.17.2 lane 3, Grok Bot's 0.17.0 audit: A10, T15, T33, T34).

More looks is a grid of small weeks in each look's colours; the footer says one thing; label columns
line up down a page; the design cards have one name each and fill their rows.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from desktop.native.layouts.dialog import DesignPicker
from desktop.native.look_preview import look_choice, look_preview
from desktop.native.settings import SettingsPage
from desktop.native.widgets import ChoiceCard, FieldLabel, card_columns
from desktop.native.window import NativeWindow
from desktop.tests.test_settings_words import page, prefs
from desktop.tests.window_support import qapp, server, signed_out, window  # noqa: F401

MORE = ["High contrast", "Nocturne", "Slate", "Poster", "Terminal", "Paper", "Ink", "Pastel"]


def tile(dialog: SettingsPage, name: str) -> ChoiceCard:
    return next(card for card in dialog.look.more.cards if card.accessibleName() == name)


def test_more_looks_is_a_grid_of_named_pictures(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    dialog = prefs(window)
    assert [card.accessibleName() for card in dialog.look.more.cards] == MORE
    assert all(not card.picture.pixmap().isNull() for card in dialog.look.more.cards)
    assert dialog.look.more.columns() > 1, "a grid, not one long column"
    dialog.close_page()


def test_the_looks_stand_four_in_a_row_and_widen_with_large_text(
    qapp: QApplication, window: NativeWindow  # noqa: F811
) -> None:
    """At 1280 wide the eight looks are two rows of four, which leaves the accent in sight under
    them. High contrast's text is Large, and a card as wide as at normal text wrapped its name onto
    a second line: the cards widen with the text, as far as the name needs."""
    window.resize(1280, 800)
    dialog = prefs(window)
    assert dialog.look.more.columns() == 4
    tile(dialog, "High contrast").chosen.emit()
    for _ in range(5):
        qapp.processEvents()
    label = tile(dialog, "High contrast").findChild(QLabel, "setupChoiceName")
    assert label.fontMetrics().horizontalAdvance(label.text()) <= label.contentsRect().width()
    assert label.heightForWidth(label.width()) <= label.fontMetrics().lineSpacing() + 2
    dialog.look.main.buttons()[0].click()
    for _ in range(5):
        qapp.processEvents()
    assert dialog.look.more.columns() == 4, "back at normal text, four in a row again"
    dialog.close_page()


def test_each_picture_is_drawn_in_its_looks_own_colours(qapp: QApplication) -> None:  # noqa: F811
    def page_colour(token: str) -> str:
        pack, look = look_choice(token, [])
        picture = look_preview(pack, look, 150)
        image = picture.toImage()
        # In the margin left of the first day, under the top bar: the page itself.
        return image.pixelColor(2, image.height() - 6).name()

    assert page_colour("pack:nocturne") == "#0a0e27"
    assert page_colour("preset:terminal") == "#0d1117"
    assert page_colour("preset:high-contrast") == "#000000"
    assert len({page_colour(f"preset:{name}") for name in ("paper", "poster", "terminal", "pastel")}) == 4


def test_a_saved_look_is_drawn_in_its_own_page_colour(qapp: QApplication) -> None:  # noqa: F811
    saved = [{"name": "Night study", "base": "light", "colours": {"page": "#262d3b"}}]
    pack, look = look_choice("saved:Night study", saved)
    image = look_preview(pack, look, 150).toImage()
    assert image.pixelColor(2, image.height() - 6).name() == "#262d3b"


def test_one_click_wears_a_look_and_marks_it_and_says_so(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    dialog = prefs(window)
    assert dialog.look.worn.isHidden(), "Light is worn: the segment shows it"
    tile(dialog, "Nocturne").chosen.emit()
    assert dialog.look.currentData() == "pack:nocturne"
    assert tile(dialog, "Nocturne").is_selected()
    assert [card.is_selected() for card in dialog.look.more.cards].count(True) == 1
    assert dialog.look.main.currentIndex() == -1, "Light, Dark and System show none"
    assert dialog.look.worn.isHidden(), "the card says it, inside itself, not a line under the grid"
    assert tile(dialog, "Nocturne").note.text() == "Wearing"
    dialog.look.main.buttons()[0].click()
    assert not any(card.is_selected() for card in dialog.look.more.cards)
    assert dialog.look.worn.isHidden()
    dialog.close_page()


def test_a_look_can_be_chosen_from_the_keyboard(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    dialog = prefs(window)
    card = tile(dialog, "Paper")
    assert card.focusPolicy() == Qt.FocusPolicy.StrongFocus
    QTest.keyClick(card, Qt.Key.Key_Space)
    assert dialog.look.currentText() == "Paper" and card.is_selected()
    dialog.close_page()


def test_your_looks_follow_the_ten_under_their_own_heading(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    dialog = prefs(window)
    assert dialog.look.yours_heading.isHidden() and dialog.look.yours.isHidden()
    dialog.look.set_saved([{"name": "Night study", "base": "light"}, {"name": "Bus", "base": "dark"}])
    assert [card.accessibleName() for card in dialog.look.yours.cards] == ["Night study", "Bus"]
    assert dialog.look.yours_heading.text() == "Your looks"
    assert not dialog.look.yours_heading.isHidden()
    dialog.look.set_saved([])
    assert dialog.look.yours.cards == [] and dialog.look.yours_heading.isHidden()
    dialog.close_page()


def test_the_footer_says_one_thing_however_a_save_goes(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    dialog = prefs(window)
    standing = "Changes are saved as you make them."
    assert dialog.save_state.text() == standing
    for routine in ("Saving preferences…", "Saved preferences.", "Saving…", "Saved.", "This week."):
        window.session.status.emit(routine)
        assert dialog.save_state.text() == standing
    window.session.status.emit("Could not reach the server.")
    assert dialog.save_state.text() == "Could not reach the server.", "what needs reading still shows"
    window.session.status.emit("Saved preferences.")
    assert dialog.save_state.text() == standing
    dialog.close_page()


@pytest.mark.parametrize("row", [0, 1, 2, 3, 4])
def test_label_columns_line_up_down_a_page(qapp: QApplication, window: NativeWindow, row: int) -> None:  # noqa: F811
    dialog = prefs(window)
    dialog.nav.setCurrentRow(row)
    for _ in range(5):
        qapp.processEvents()
    body = page(dialog, row)
    labels = [label for label in body.findChildren(FieldLabel) if label.isVisibleTo(body) and label.text()]
    # Every field starts to the right of the same line: the widest label's right edge.
    widths = {label.width() for label in labels}
    assert len(widths) <= 1, f"label widths differ on page {row}: {sorted(widths)}"
    dialog.close_page()


def test_updates_sit_at_the_same_x_as_account_and_setup(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    dialog = prefs(window)
    dialog.nav.setCurrentRow(4)
    for _ in range(5):
        qapp.processEvents()
    body = page(dialog, 4)
    fields = {
        name: body.findChild(QWidget, name).mapTo(body, body.findChild(QWidget, name).rect().topLeft()).x()
        for name in ("prefsAccount", "prefsRunSetup", "prefsCheckUpdates")
    }
    assert len(set(fields.values())) == 1, fields
    dialog.close_page()


def test_design_cards_fill_their_rows(qapp: QApplication) -> None:  # noqa: F811
    six = 6
    assert card_columns(six, 3 * 240, 228, 12) == 3, "two full rows of three"
    assert card_columns(six, 2 * 240, 228, 12) == 2, "three full rows of two"
    assert card_columns(six, 4 * 240, 228, 12) == 3, "four fit but would leave two alone"
    assert card_columns(2, 2 * 240, 228, 12) == 2, "Day screen's two sit side by side"
    assert card_columns(5, 4 * 240, 228, 12) == 3, "five, when nothing divides, share out as 3 and 2"
    assert card_columns(6, 100, 228, 12) == 1, "a window narrower than a card gets one column"
    assert card_columns(1, 1000, 228, 12) == 1


def test_no_design_card_stands_alone_on_a_row(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    window.resize(1280, 800)
    dialog = prefs(window)
    for role in ("layoutMain", "layoutDay"):
        picker = page(dialog, 0).findChild(DesignPicker, role)
        rows: dict[int, list[ChoiceCard]] = {}
        for card in picker.cards:
            rows.setdefault(card.mapTo(picker, QPoint(0, 0)).y(), []).append(card)
        counts = [len(cards) for cards in rows.values()]
        assert min(counts) > 1, f"{role}: a lone card in a row ({counts})"
        for cards in rows.values():
            assert len({card.height() for card in cards}) == 1, f"{role}: uneven card heights in a row"
    dialog.close_page()
