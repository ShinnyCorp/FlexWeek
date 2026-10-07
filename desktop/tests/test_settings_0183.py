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
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QWidget

from desktop.native import motion
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


