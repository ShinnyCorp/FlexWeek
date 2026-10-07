"""Settings in 0.18.3 (batch B, mockup 8): a fade above the footer, the Appearance page's chosen marks
and stretched grids, and one control width per column (#66, #67, #68).

Expected values come from the brief and the mockup, not from what the page printed: the ring is the
look's accent, a grid's last card ends within 16 px of its row, a column of controls is 260 px.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from desktop.native import motion
from desktop.native.layouts.registry import LAYOUTS
from desktop.native.look import resolved_palette
from desktop.native.settings import FADE_PX, SettingsPage
from desktop.native.widgets import ChoiceCard
from desktop.native.window import NativeWindow

# The fixtures are used by name, so each test's argument list redefines them.
# ruff: noqa: F811
from desktop.tests.window_support import qapp, server, signed_out, window  # noqa: F401

APPEARANCE, PLANNING, FOCUS, ALERTS, COMPUTER = range(5)
CONTROL_WIDTH = 260


@pytest.fixture(autouse=True)
def still() -> Iterator[None]:
    was = motion.app_level()
    motion.apply_ui_effects("off")
    yield
    motion.apply_ui_effects(was)


def open_settings(qapp: QApplication, window: NativeWindow, size: tuple[int, int]) -> SettingsPage:
    window.resize(*size)
    window._open_settings()
    page = window._settings
    assert page is not None
    page.motion_level = "off"
    show_section(qapp, page, APPEARANCE)
    return page


def show_section(qapp: QApplication, page: SettingsPage, row: int) -> QWidget:
    page.nav.setCurrentRow(row)
    for _ in range(12):
        qapp.processEvents()
    return page.stack.widget(row).widget()


def palette_of(window: NativeWindow) -> dict:
    pack, dark, accent = window._look_inputs()
    return resolved_palette(pack, dark, window._look, accent)


def near(found: QColor, wanted: str, slack: int = 2) -> bool:
    other = QColor(wanted)
    return all(
        abs(a - b) <= slack
        for a, b in ((found.red(), other.red()), (found.green(), other.green()), (found.blue(), other.blue()))
    )


def seen(image: QImage, x: int, y: int, behind: str) -> QColor:
    """A pixel as the eye sees it: a viewport grab leaves the gaps between cards clear, over the page."""
    found = image.pixelColor(x, y)
    if found.alpha() == 255:
        return found
    back = QColor(behind)
    mix = found.alphaF()
    return QColor(
        round(found.red() * mix + back.red() * (1 - mix)),
        round(found.green() * mix + back.green() * (1 - mix)),
        round(found.blue() * mix + back.blue() * (1 - mix)),
    )


def tile(page: SettingsPage, name: str) -> ChoiceCard:
    return next(card for card in page.look.more.cards if card.accessibleName() == name)


def where(widget: QWidget, within: QWidget) -> QPoint:
    return widget.mapTo(within, QPoint(0, 0))


# --- #66: the fade above the footer and the padding under the last card ---------------------------


@pytest.mark.parametrize("size", [(1024, 700), (1280, 800)])
def test_every_section_ends_clear_of_the_footer(
    qapp: QApplication, window: NativeWindow, size: tuple[int, int]
) -> None:
    page = open_settings(qapp, window, size)
    footer = page.findChild(QWidget, "settingsFooter")
    for row in range(5):
        body = show_section(qapp, page, row)
        area = page.stack.widget(row)
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
        qapp.processEvents()
        assert body.layout().contentsMargins().bottom() >= footer.height(), (row, footer.height())
        lowest = max(
            where(widget, page).y() + widget.height()
            for widget in body.findChildren(QWidget)
            if widget.isVisibleTo(body)
        )
        assert lowest <= where(footer, page).y(), (row, lowest, where(footer, page).y())
    page.close_page()


@pytest.mark.parametrize("size", [(1024, 700), (1280, 800)])
def test_mid_scroll_the_row_above_the_footer_is_the_fade(
    qapp: QApplication, window: NativeWindow, size: tuple[int, int]
) -> None:
    page = open_settings(qapp, window, size)
    page_colour = palette_of(window)["window"]
    footer = page.findChild(QWidget, "settingsFooter")
    edge = where(footer, page).y()
    # Only the stage: the section list beside it is a panel of its own colour.
    across = range(where(footer, page).x(), where(footer, page).x() + footer.width())
    checked = 0
    for row in range(5):
        show_section(qapp, page, row)
        area = page.stack.widget(row)
        bar = area.verticalScrollBar()
        if bar.maximum() <= 0:
            continue
        half = FADE_PX // 2
        origin = where(area.viewport(), page)
        at = edge - origin.y()
        # A scroll position with content behind the footer's top edge, so a hard cut would show it; on
        # Appearance, one with a dark look's picture behind the middle of the ramp as well.
        for value in range(0, bar.maximum(), 10):
            bar.setValue(value)
            qapp.processEvents()
            raw = area.viewport().grab().toImage()
            under = sum(not near(seen(raw, x, at - 1, page_colour), page_colour) for x in range(raw.width()))
            dark = [
                x
                for x in range(raw.width() - 24)
                if sum(seen(raw, x, at - half, page_colour).getRgb()[:3]) < 300
            ]
            if under > 100 and (dark or row != APPEARANCE):
                break
        else:
            raise AssertionError(f"section {row} never had content behind the footer")
        shown = page.grab().toImage()
        assert all(near(shown.pixelColor(x, edge - 1), page_colour) for x in across), row
        # The ramp begins FADE_PX up and leaves what is above it as it was. The right edge is left out:
        # the scroll bar is drawn over the page there, not on the viewport.
        sides = range(0, raw.width() - 24, 7)
        high = at - FADE_PX - 16
        assert all(
            shown.pixelColor(origin.x() + x, origin.y() + high) == seen(raw, x, high, page_colour)
            for x in sides
        ), row
        # Half way up, a dark picture is part faded: the picture and the page colour mixed in that ratio.
        mix = (half + 0.5) / (FADE_PX - 1)
        back = QColor(page_colour)
        for x in dark:
            was = seen(raw, x, at - half, page_colour)
            got = shown.pixelColor(origin.x() + x, origin.y() + at - half)
            for have, before, after in (
                (got.red(), was.red(), back.red()),
                (got.green(), was.green(), back.green()),
                (got.blue(), was.blue(), back.blue()),
            ):
                assert abs(have - (before * (1 - mix) + after * mix)) <= 6, (row, x, got.name(), was.name())
        checked += 1
    assert checked >= 2
    page.close_page()


# --- #67: Appearance ---------------------------------------------------------------------------


def test_the_chosen_look_card_is_ringed_and_says_wearing_inside_the_card(
    qapp: QApplication, window: NativeWindow
) -> None:
    page = open_settings(qapp, window, (1280, 800))
    height = page.look.sizeHint().height()
    tile(page, "Nocturne").chosen.emit()
    for _ in range(5):
        qapp.processEvents()
    assert page.look.sizeHint().height() == height, "wearing a look moves nothing below it"
    accent = palette_of(window)["accent"]
    worn = tile(page, "Nocturne")
    ring = worn.grab().toImage()
    assert near(ring.pixelColor(worn.width() // 2, 1), accent)
    inside = [label.text() for label in worn.findChildren(QLabel) if label.isVisibleTo(worn)]
    assert "Wearing" in inside
    for other in page.look.more.cards:
        if other is not worn:
            assert not near(other.grab().toImage().pixelColor(other.width() // 2, 1), accent)
            assert "Wearing" not in [
                label.text() for label in other.findChildren(QLabel) if label.isVisibleTo(other)
            ]
    assert page.look.worn.isHidden(), "no line under the grid: the card says it"
    page.close_page()


def test_light_dark_and_system_show_the_chosen_one_the_same_way(
    qapp: QApplication, window: NativeWindow
) -> None:
    page = open_settings(qapp, window, (1280, 800))
    segments = page.look.main.buttons()
    height = page.look.sizeHint().height()
    segments[2].click()
    for _ in range(5):
        qapp.processEvents()
    assert page.look.sizeHint().height() == height, "wearing System moves nothing below it"
    accent = palette_of(window)["accent"]
    assert near(segments[2].grab().toImage().pixelColor(segments[2].width() // 2, 1), accent)
    assert not near(segments[0].grab().toImage().pixelColor(segments[0].width() // 2, 1), accent)
    line = page.look.main_worn
    assert line.text() == "Wearing System" and line.isVisibleTo(page)
    assert where(line, page).y() >= where(page.look.main, page).y() + page.look.main.height()
    tile(page, "Nocturne").chosen.emit()
    for _ in range(5):
        qapp.processEvents()
    assert not near(segments[2].grab().toImage().pixelColor(segments[2].width() // 2, 1), accent)
    assert line.text().strip() == ""
    page.close_page()


@pytest.mark.parametrize("size", [(1024, 700), (1280, 800)])
def test_the_look_grids_stretch_to_the_row(
    qapp: QApplication, window: NativeWindow, size: tuple[int, int]
) -> None:
    page = open_settings(qapp, window, size)
    page.look.set_saved([{"name": "Night study", "base": "light"}, {"name": "Bus", "base": "dark"}])
    for _ in range(8):
        qapp.processEvents()
    for grid in (page.look.more, page.look.yours):
        assert grid.cards
        right = max(card.geometry().right() + 1 for card in grid.cards)
        assert grid.width() - right <= 16, (size, grid.width(), right)
        for card in grid.cards:
            sharp = card.picture.pixmap().width() / card.picture.pixmap().devicePixelRatio()
            assert abs(sharp - card.picture.width()) <= 2, "the picture is drawn at the card's width"
    page.close_page()


def test_the_button_and_the_description_have_their_new_words(
    qapp: QApplication, window: NativeWindow
) -> None:
    page = open_settings(qapp, window, (1280, 800))
    assert page.findChild(QPushButton, "prefCustomise").text() == "Edit your own look…"
    sentence = "The week grid with the sidebar. Its colours come from the look you choose above."
    assert LAYOUTS["classic"].summary == sentence
    card = next(card for card in page.findChildren(ChoiceCard) if card.accessibleName() == "Today's app")
    assert card.note.text() == sentence
    page.close_page()


# --- #68: one control width per column ---------------------------------------------------------


def test_focus_puts_the_preset_first_and_every_control_is_one_width(
    qapp: QApplication, window: NativeWindow
) -> None:
    page = open_settings(qapp, window, (1280, 800))
    show_section(qapp, page, FOCUS)
    steppers = page.focus_steppers
    rows = [page.preset_timer, *steppers[:3], steppers[3]]
    tops = [where(widget, page).y() for widget in rows]
    assert tops == sorted(tops) and len(set(tops)) == 5, tops
    assert {widget.width() for widget in rows} == {CONTROL_WIDTH}, [widget.width() for widget in rows]
    page.close_page()


def test_alerts_controls_are_one_width_and_no_alarms_yet_is_grey(
    qapp: QApplication, window: NativeWindow
) -> None:
    page = open_settings(qapp, window, (1280, 800))
    page.alarm_tone.setCurrentIndex(page.alarm_tone.findData("spotify"))
    show_section(qapp, page, ALERTS)
    controls = [
        page.lead.parentWidget(),
        page.volume.parentWidget(),
        page.alarm_tone,
        page.spotify,
        page.alarm_name,
        page.alarm_time,
        page.alarm_sound,
        page.alarm_spotify,
    ]
    assert all(widget.isVisibleTo(page) for widget in controls)
    # 260 px, or the widest one's own width where a label needs more: "A Spotify song or playlist" is
    # wider than 260 in the sound dropdown, and every control follows it.
    widths = {widget.width() for widget in controls}
    assert len(widths) == 1 and min(widths) >= CONTROL_WIDTH, [widget.width() for widget in controls]
    hint = page.findChild(QLabel, "prefTrayNote")
    empty = page.alarm_empty
    assert empty.isVisibleTo(page)
    grey = palette_of(window)["muted"]
    assert near(hint.palette().color(QPalette.ColorRole.WindowText), grey)
    assert near(empty.palette().color(QPalette.ColorRole.WindowText), grey)
    page.close_page()


def test_this_computer_values_start_where_focus_and_alerts_values_start(
    qapp: QApplication, window: NativeWindow
) -> None:
    page = open_settings(qapp, window, (1280, 800))
    starts: dict[str, int] = {}
    show_section(qapp, page, FOCUS)
    starts["focus"] = where(page.preset_timer, page).x()
    show_section(qapp, page, ALERTS)
    starts["alerts"] = where(page.lead.parentWidget(), page).x()
    starts["alarm name"] = where(page.alarm_name, page).x()
    computer = show_section(qapp, page, COMPUTER)
    names = (
        "prefPreferredView",
        "prefClock",
        "prefsAccount",
        "prefsRunSetup",
        "prefsVersion",
        "prefsCheckUpdates",
    )
    for name in names:
        starts[name] = where(computer.findChild(QWidget, name), page).x()
    assert len(set(starts.values())) == 1, starts
    buttons = [
        computer.findChild(QPushButton, name)
        for name in ("prefsAccount", "prefsRunSetup", "prefsCheckUpdates")
    ]
    assert len({button.width() for button in buttons}) == 1, [button.width() for button in buttons]
    page.close_page()
