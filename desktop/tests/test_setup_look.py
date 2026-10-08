"""Setup as 0.17 draws it (decision 26): each page and its buttons centred up to 880 pixels, a tick on
every finished step, Next the one filled button, the school hint only when it is true, Play an icon.
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
    from PySide6.QtCore import QPoint, QSize, QStandardPaths
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget

    from desktop.native.calendar import monday_of
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.look import pack_stylesheet, resolved_palette
    from desktop.native.setup import (
        BADGE_PX,
        CURRENT,
        DONE,
        FINISHED,
        HOMEWORK,
        PENDING,
        REMINDERS,
        SETUP_COLUMN,
        STYLE,
        WEEK,
        SetupPage,
        SetupState,
        step_badge,
    )
    from desktop.native.widgets import control_art

STEPS = (STYLE, WEEK, HOMEWORK, REMINDERS, DONE)


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-setup-look-test"])


@pytest.fixture()
def dressed(qapp: QApplication) -> Iterator[tuple[SetupPage, dict]]:
    """Setup in Light, with the window's stylesheet, as a new account sees it."""
    palette = resolved_palette("light-frost", False, None)
    host = QWidget()
    host.setStyleSheet(pack_stylesheet("light-frost", False, None, "default", palette, control_art(palette)))
    setup = SetupPage(host)
    setup.motion = "off"
    setup.set_palette(palette)
    look = {"preset": "default", "knobs": {}}
    setup.open(SetupState("light-frost", look, sanitize_layout(None), {}, [], monday_of("2026-09-23")))
    host.resize(1600, 800)
    setup.resize(1600, 800)
    host.show()
    qapp.processEvents()
    yield setup, palette
    host.close()
    host.deleteLater()
    qapp.processEvents()


def column_of(setup: SetupPage) -> QWidget:
    """The page's centred column: the one holding its title."""
    return setup.stack.currentWidget().findChild(QWidget, "setupTitle").parentWidget()


def test_each_page_and_its_buttons_are_centred_up_to_880_pixels(
    qapp: QApplication, dressed: tuple[SetupPage, dict]
) -> None:
    setup, _palette = dressed
    for step in (STYLE, WEEK, REMINDERS):
        setup._show(step)
        qapp.processEvents()
        column = column_of(setup)
        page = setup.stack.currentWidget()
        assert column.width() == SETUP_COLUMN, step
        left = column.mapTo(page, QPoint(0, 0)).x()
        right = page.viewport().width() - (left + column.width())
        assert abs(left - right) <= 2, (step, left, right)
        # Next ends where the page above it ends, not at the window's edge; a page that scrolls is
        # centred beside its scroll bar, half a bar's width off.
        next_right = setup.next.mapTo(setup, QPoint(setup.next.width(), 0)).x()
        bar = page.width() - page.viewport().width()
        assert abs(next_right - column.mapTo(setup, QPoint(column.width(), 0)).x()) <= bar // 2 + 2, step
    setup.resize(1000, 800)
    qapp.processEvents()
    column = column_of(setup)
    assert column.width() < SETUP_COLUMN, "a narrow window gives the page all the room it has"


def picture(setup: SetupPage, index: int) -> object:
    return setup.rail_items[index].icon().pixmap(QSize(BADGE_PX, BADGE_PX)).toImage()


def badge(number: int, state: str, setup: SetupPage, palette: dict) -> object:
    family = setup.rail_items[0].font().family()
    return step_badge(number, state, palette, family).toImage()


def test_a_finished_step_shows_a_tick_on_the_rail(
    qapp: QApplication, dressed: tuple[SetupPage, dict]
) -> None:
    setup, palette = dressed
    setup.skip.click()
    setup.skip.click()
    assert setup.step == HOMEWORK
    states = [FINISHED, FINISHED, CURRENT, PENDING, PENDING, PENDING]
    for index, state in enumerate(states):
        assert picture(setup, index) == badge(index + 1, state, setup, palette), (index, state)
    assert [item.accessibleDescription() for item in setup.rail_items[:3]] == ["Done", "Done", ""]
    tick = badge(1, FINISHED, setup, palette)
    # Above the tick and inside the ring.
    assert tick.pixelColor(BADGE_PX // 2, 4) == QColor(palette["accent"]), "a tick on the accent"
    assert badge(1, PENDING, setup, palette).pixelColor(BADGE_PX // 2, 4).alpha() == 0, "a ring, not filled"


def filled(setup: SetupPage, accent: str) -> list[str]:
    """The buttons on screen painted in the accent, read from a picture of each."""
    found = []
    for button in setup.findChildren(QPushButton):
        if not button.isVisibleTo(setup) or button.width() < 8:
            continue
        # A ticked day or chip is an answer shown, like a segment, not a second thing to press.
        if button.isCheckable() and (button.property("pill") or button.objectName() == "setupChip"):
            continue
        # The carousel's chosen dot marks which style is picked, which is not a button to press on.
        if button.objectName() == "setupDot":
            continue
        # Above the words, so a link in the accent does not count as a fill.
        if button.grab().toImage().pixelColor(button.width() // 2, 3) == QColor(accent):
            found.append(button.text() or button.objectName())
    return found


def test_next_is_the_one_filled_button_on_every_page(
    qapp: QApplication, dressed: tuple[SetupPage, dict]
) -> None:
    """Add custom hours and Send a test reminder were filled like Next, and read as the way on."""
    setup, palette = dressed
    for step in STEPS:
        setup._show(step)
        qapp.processEvents()
        assert filled(setup, palette["accent"]) == ["Open my week" if step == DONE else "Next"], step


def test_the_school_hint_shows_only_when_no_school_day_is_picked(dressed: tuple[SetupPage, dict]) -> None:
    setup, _palette = dressed
    setup._show(WEEK)
    assert not setup.school_hint.isVisibleTo(setup), "under a week of school days it read as a warning"
    setup.school_days.set_days([])
    assert setup.school_hint.isVisibleTo(setup)
    setup.school_days.set_days([2])
    assert not setup.school_hint.isVisibleTo(setup)


def apart(first: QColor, second: QColor) -> int:
    return max(abs(a - b) for a, b in zip(first.getRgb()[:3], second.getRgb()[:3], strict=True))


def test_play_is_an_icon_in_the_looks_accent(dressed: tuple[SetupPage, dict]) -> None:
    setup, _palette = dressed
    setup._show(REMINDERS)
    dark = resolved_palette("dark-frost", False, None)
    setup.set_palette(dark)
    for play in setup.play_buttons:
        assert play.text() == "" and play.toolTip() == "Play"
        drawn = play.icon().pixmap(QSize(20, 20)).toImage()
        accent = QColor(dark["accent"])
        inked = [
            drawn.pixelColor(x, y)
            for x in range(drawn.width())
            for y in range(drawn.height())
            if drawn.pixelColor(x, y).alpha() >= 128
        ]
        assert inked, play.accessibleName()
        far = [seen.name() for seen in inked if apart(seen, accent) > 3]
        assert far == [], play.accessibleName()
