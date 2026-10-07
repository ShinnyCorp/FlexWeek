"""Setup as the 0.17.2 audit left it (Grok Bot's 0.17.0 audit, T35): picture cards whole at the
smallest window and at Large text, controls that look like controls, an example that reads as one,
School's times and a sport's at one x, and the one name for each design.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPoint, QRect, QStandardPaths
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

    from desktop.native.calendar import monday_of
    from desktop.native.layouts.registry import layouts_for, sanitize_layout
    from desktop.native.look import pack_stylesheet, resolved_palette, sanitize_look
    from desktop.native.setup import (
        DONE,
        FIRST,
        HOMEWORK,
        LOOK,
        REMINDERS,
        STYLE,
        WEEK,
        SetupPage,
        SetupState,
    )
    from desktop.native.widgets import control_art

SIZES = ((1280, 800), (810, 800))
TEXTS = ("normal", "large")


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-setup-audit-test"])


@contextmanager
def dressed(
    qapp: QApplication, size: tuple[int, int] = SIZES[0], text: str = "normal", pack: str = "light-frost"
) -> Iterator[tuple[SetupPage, dict]]:
    """Setup in this window size and text size, with the window's stylesheet, as a new account sees it."""
    look = sanitize_look({"preset": "default", "knobs": {"text": text}})
    palette = resolved_palette(pack, False, look)
    host = QWidget()
    host.setStyleSheet(pack_stylesheet(pack, False, look, "default", palette, control_art(palette)))
    setup = SetupPage(host)
    setup.motion = "off"
    setup.set_palette(palette)
    setup.open(SetupState(pack, look, sanitize_layout(None), {}, [], monday_of("2026-09-23")))
    host.resize(*size)
    setup.resize(*size)
    host.show()
    qapp.processEvents()
    try:
        yield setup, palette
    finally:
        host.close()
        host.deleteLater()
        qapp.processEvents()


def show(qapp: QApplication, setup: SetupPage, step: int) -> None:
    setup._show(step)
    qapp.processEvents()


def corner(widget: QWidget, x: int, y: int) -> QColor:
    return widget.grab().toImage().pixelColor(x, y)


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("size", SIZES)
def test_the_picture_cards_are_whole_at_the_end_of_their_page(
    qapp: QApplication, size: tuple[int, int], text: str
) -> None:
    """At 810 pixels two cards a row ran off the right edge of the page, and nothing scrolls sideways."""
    with dressed(qapp, size, text) as (setup, _palette):
        show(qapp, setup, LOOK)
        page = setup.pages[LOOK]
        bar = page.verticalScrollBar()
        bar.setValue(bar.maximum())
        qapp.processEvents()
        view = page.viewport()
        for key, card in setup.look_cards.items():
            box = QRect(card.mapTo(view, QPoint(0, 0)), card.size())
            where = (LOOK, key, size, text)
            assert box.left() >= 0 and box.right() < view.width(), (where, "cut at the side", box)
            assert box.bottom() < view.height(), (where, "cut at the bottom", box)
            for label in card.findChildren(QLabel):
                if label.wordWrap() and label.isVisibleTo(card):
                    assert label.height() >= label.heightForWidth(label.width()), (where, label.text())
        # The Style page's carousel keeps its middle picture and its words whole; the neighbours are
        # meant to run off the sides.
        show(qapp, setup, STYLE)
        carousel = setup.carousel
        front = carousel.slides[carousel.key()]
        view = setup.pages[STYLE].viewport()
        box = QRect(front.mapTo(view, QPoint(0, 0)), front.size())
        assert box.left() >= 0 and box.right() < view.width(), ((size, text), "the middle is cut", box)
        for label in (carousel.name, carousel.note):
            assert label.height() >= label.heightForWidth(label.width()), (size, text, label.text())


def test_the_planning_hours_chips_are_the_pills_the_day_picker_uses(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        show(qapp, setup, WEEK)
        day = setup.school_days.buttons[6]
        assert not day.isChecked()
        day_ground, day_height = corner(day, 4, day.height() // 2), day.height()
        show(qapp, setup, HOMEWORK)
        chips = [
            button
            for button in setup.work_editor.findChildren(QPushButton)
            if button.objectName().startswith("workWindowPreset")
        ]
        assert [chip.text() for chip in chips] == ["+ After school", "+ Evenings", "+ Weekend mornings"]
        for chip in chips:
            assert chip.property("chip") is True, chip.text()
            assert corner(chip, 4, chip.height() // 2) == day_ground, f"{chip.text()} is drawn as a pill"
            assert chip.height() == day_height, chip.text()


@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_send_a_test_reminder_and_add_custom_hours_are_outlined_buttons(
    qapp: QApplication, pack: str
) -> None:
    """Both were words alone, in the page's own colour, and read as plain text."""
    with dressed(qapp, pack=pack) as (setup, palette):
        show(qapp, setup, REMINDERS)
        button = setup.test
        assert button.property("outline") is True and not button.property("quiet")
        assert corner(button, button.width() // 2, 0) == QColor(palette["hairline_strong"]), "an edge"
        assert corner(button, 10, button.height() // 2) == QColor(palette["panel"]), "on the card's ground"
        show(qapp, setup, HOMEWORK)
        add = setup.work_editor.add_button
        assert add.property("outline") is True and not add.property("quiet")
        assert corner(add, add.width() // 2, 0) == QColor(palette["hairline_strong"])


def gap(one: QColor, other: QColor) -> int:
    return abs(one.red() - other.red()) + abs(one.green() - other.green()) + abs(one.blue() - other.blue())


def darkest_ink(widget: QWidget) -> QColor:
    """The strongest colour a field's words are drawn in: the pixel furthest from the field's ground."""
    image = widget.grab().toImage()
    ground = image.pixelColor(image.width() // 2, 3)
    inner = [
        image.pixelColor(x, y)
        for x in range(6, image.width() - 6)
        for y in range(6, image.height() - 6)
    ]
    return max(inner, key=lambda pixel: gap(pixel, ground))


def test_the_example_homework_reads_as_an_example_and_adds_nothing(qapp: QApplication) -> None:
    """A grey "History essay" read as a filled value, and Done then said None yet. The example is not
    added: it is words in an empty box, so a student who leaves it is told, truly, that none is set."""
    with dressed(qapp) as (setup, palette):
        show(qapp, setup, FIRST)
        field = setup.homework_rows[0].name
        assert field.placeholderText() == "e.g. History essay"
        assert field.text() == ""
        ink, muted = darkest_ink(field), QColor(palette["muted"])
        assert gap(ink, muted) <= 30, f"muted is {muted.name()}, the example is drawn in {ink.name()}"
        assert setup.first_homework() == []
        setup._go_next()
        assert setup.step == DONE
        assert setup.summary_text()[4] == "None yet"


def test_a_homework_typed_over_the_example_is_listed_on_done(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        show(qapp, setup, FIRST)
        setup.homework_rows[0].name.setText("Math worksheet")
        setup._go_next()
        assert setup.summary_text()[4] == "Math worksheet"


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("size", SIZES)
def test_a_sports_time_fields_line_up_with_schools(
    qapp: QApplication, size: tuple[int, int], text: str
) -> None:
    with dressed(qapp, size, text) as (setup, _palette):
        show(qapp, setup, WEEK)
        setup._add_activity(title="Band", days=[2], start="16:00", minutes=60)
        qapp.processEvents()
        assert len(setup.activities) == 2
        for row in setup.activities:
            pairs = ((setup.school_times.start, row.times.start), (setup.school_times.end, row.times.end))
            for school, sport in pairs:
                where = (size, text, sport.accessibleName())
                assert sport.mapTo(setup, QPoint(0, 0)).x() == school.mapTo(setup, QPoint(0, 0)).x(), where
                assert sport.width() == school.width(), where


def test_setup_calls_each_design_by_the_one_name_settings_uses(qapp: QApplication) -> None:
    """"Calendar · Today's app" was two names for one design (the audit's T34, for Settings)."""
    with dressed(qapp) as (setup, _palette):
        for card in [*setup.style_cards.values(), *setup.look_cards.values()]:
            assert "·" not in card.accessibleName() + card.accessibleDescription(), card.accessibleName()
        assert setup.look_cards["classic"].accessibleName() == "Today's app"
        assert setup.look_cards["timeline"].accessibleName() == "Timeline"
        assert all("Today's app" not in card.accessibleDescription() for card in setup.style_cards.values())
        # The day screens, offered by name on the colours page.
        chips = [button.text() for button in setup.day_screen.buttons()]
        assert chips == [spec.label for spec in (*layouts_for("day", False), *layouts_for("day", True))]
        setup._show(DONE)
        assert setup.summary_text()[0].startswith("Today's app in "), setup.summary_text()[0]
        assert "·" not in setup.summary_text()[0]


def test_the_hours_chips_still_add_a_row(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        show(qapp, setup, HOMEWORK)
        setup.work_editor.findChild(QPushButton, "workWindowPresetEvenings").click()
        assert len(setup.work_editor.windows()) == 1
