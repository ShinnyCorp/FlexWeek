"""Settings in the 0.17 system (decision 24 of docs/0.17/plan.md, look-review.md section 8).

The cards stood at 760 pixels against the left with a quarter of the window empty; the section list
was plain words; Look was one long dropdown and Accent another; the number boxes were four widths;
and the cards ran on under the footer with nothing to end them.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton, QSpinBox, QWidget

from desktop.native.look import ACCENT_COLORS, look_menu_token, resolved_palette
from desktop.native.settings import SETTINGS_COLUMN, SettingsPage
from desktop.native.widgets import Segmented, Swatches
from desktop.native.window import NativeWindow
from desktop.tests.window_support import qapp, server, signed_out, window  # noqa: F401


def open_settings(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    size: tuple[int, int] = (1280, 800),
) -> SettingsPage:
    window.resize(*size)
    window._open_settings()
    page = window._settings
    for _ in range(10):
        qapp.processEvents()
    return page


def palette_of(window: NativeWindow) -> dict:  # noqa: F811
    pack, dark, accent = window._look_inputs()
    return resolved_palette(pack, dark, window._look, accent)


def test_the_column_of_cards_is_centred_up_to_960(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    page = open_settings(qapp, window, (1600, 900))
    area = page.stack.currentWidget()
    body = area.widget()
    column = body.layout().itemAt(1).widget()
    assert column.width() == SETTINGS_COLUMN == 960
    left = column.mapTo(area.viewport(), QPoint(0, 0)).x()
    right = area.viewport().width() - left - column.width()
    assert abs(left - right) <= 2, (left, right)
    page.close_page()


def test_each_section_has_its_icon_and_the_chosen_one_an_accent_bar(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    page = open_settings(qapp, window)
    nav = page.nav
    assert all(not nav.item(row).icon().isNull() for row in range(nav.count()))
    accent = QColor(palette_of(window)["accent"])
    picture = nav.viewport().grab().toImage()
    for row in range(nav.count()):
        box = nav.visualItemRect(nav.item(row))
        edge = picture.pixelColor(box.left() + 1, box.center().y())
        assert (edge == accent) == (row == nav.currentRow()), row
    page.close_page()


def test_look_is_light_dark_or_system_and_the_other_looks_are_under_more_looks(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    page = open_settings(qapp, window)
    main = page.findChild(Segmented, "prefThemeMain")
    more = page.findChild(QComboBox, "prefThemeMore")
    assert [button.text() for button in main.buttons()] == ["Light", "Dark", "System"]
    shown = [more.itemText(index) for index in range(more.count())]
    assert "High contrast" in shown and "Nocturne" in shown
    assert not {"Light", "Dark", "System"} & set(shown)
    more.setCurrentIndex(more.findData(look_menu_token("pack", "nocturne")))
    more.activated.emit(more.currentIndex())
    assert page.updates()["theme_pack"] == "nocturne"
    assert not any(button.isChecked() for button in main.buttons()), "no segment claims Nocturne"
    main.buttons()[1].click()
    assert page.updates()["theme_pack"] == "dark-frost"
    assert more.currentIndex() == -1 and more.currentText() == "", "More looks shows its hint again"
    page.close_page()


def test_the_accent_is_swatches_in_the_looks_own_colours(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    page = open_settings(qapp, window)
    swatches = page.findChild(Swatches, "prefAccent")
    assert [button.text() for button in swatches.buttons()] == ["Blue", "Sky", "Gold", "Sea", "Sand"]
    sea = swatches.buttons()[3]
    sea.click()
    for _ in range(5):
        qapp.processEvents()
    assert page.updates()["accent"] == "sea" and sea.isChecked()
    axis = palette_of(window)["axis"]
    picture = sea.grab().toImage()
    ring = sea.SIZE + 8
    edge = QPoint(sea.width() // 2 - sea.SIZE // 2 + 3, ring // 2)
    assert picture.pixelColor(edge).name() == ACCENT_COLORS["sea"][axis][0]
    page.close_page()


def test_customise_has_its_row_under_look_and_opens_the_look_editor(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Plan, "Customise": B, the look editor, full window over Settings."""
    page = open_settings(qapp, window)
    button = page.findChild(QPushButton, "prefCustomise")
    label = page.colours_card.layout().labelForField(button)
    assert isinstance(label, QLabel) and label.text() == "Customise"
    assert button.isEnabled() and button.toolTip()
    look = page.findChild(QWidget, "prefTheme")
    assert button.mapTo(page, QPoint(0, 0)).y() > look.mapTo(page, QPoint(0, 0)).y()
    button.click()
    for _ in range(10):
        qapp.processEvents()
    editor = page.findChild(QWidget, "lookEditor")
    assert editor is not None and editor.isVisible()
    assert editor.geometry() == page.rect(), "the editor fills the page"
    assert not page.nav.isVisible(), "Settings' own list is put away under it"
    page.close_page()


def test_every_number_box_on_a_page_is_one_width(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    """Focus's boxes were 30, 15, 30 and "4 focus sessions" wide, each sized to its text."""
    page = open_settings(qapp, window)
    page.nav.setCurrentRow(2)
    for _ in range(5):
        qapp.processEvents()
    focus = page.stack.currentWidget().widget()
    widths = [box.width() for box in focus.findChildren(QSpinBox)]
    assert len(widths) >= 4 and len(set(widths)) == 1, widths
    page.close_page()


def test_a_hairline_ends_the_page_above_the_footer(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    page = open_settings(qapp, window)
    footer = page.findChild(QWidget, "settingsFooter")
    picture = footer.grab().toImage()
    assert picture.pixelColor(footer.width() // 2, 0).name() == palette_of(window)["hairline"]
    page.close_page()


def test_high_contrast_says_it_keeps_its_own_yellow(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    page = open_settings(qapp, window)
    note = page.accent_note
    assert not note.isVisibleTo(page)
    page.look.setCurrentIndex(page.look.findData(look_menu_token("preset", "high-contrast")))
    for _ in range(5):
        qapp.processEvents()
    assert note.isVisibleTo(page)
    page.close_page()
