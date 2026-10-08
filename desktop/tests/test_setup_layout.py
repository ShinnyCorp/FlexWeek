"""Setup's pages as one family (roadmap 0.18.3, #5 and the Setup part of #66): one column and left edge,
the same boxes and buttons from page to page, and the footer fading the page out above it."""

from __future__ import annotations

import importlib.util
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPoint, QStandardPaths
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QWidget

    from desktop.native import motion
    from desktop.native.calendar import monday_of
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.look import pack_stylesheet, resolved_palette, sanitize_look
    from desktop.native.setup import (
        DONE,
        FADE_PX,
        FIRST,
        HOMEWORK,
        WEEK,
        SetupPage,
        SetupState,
    )
    from desktop.native.widgets import control_art

SIZES = ((1280, 800), (1100, 720))
STEPS = tuple(range(8))


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    app = QApplication.instance() or QApplication(["flexweek-setup-layout-test"])
    motion.apply_ui_effects("off")
    return app


@contextmanager
def dressed(
    qapp: QApplication,
    size: tuple[int, int] = SIZES[0],
    text: str = "normal",
    blocks: list[dict] | None = None,
) -> Iterator[tuple[SetupPage, dict]]:
    look = sanitize_look({"preset": "default", "knobs": {"text": text}})
    palette = resolved_palette("light-frost", False, look)
    host = QWidget()
    host.setStyleSheet(pack_stylesheet("light-frost", False, look, "default", palette, control_art(palette)))
    setup = SetupPage(host)
    setup.motion = "off"
    setup.set_palette(palette)
    state = SetupState("light-frost", look, sanitize_layout(None), {}, blocks or [], monday_of("2026-09-23"))
    setup.open(state)
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


def left_edge(setup: SetupPage, step: int) -> tuple[int, int]:
    """Where the page's title and its column start, in the page's own window."""
    title = setup.pages[step].findChild(QLabel, "setupTitle")
    return (
        title.mapTo(setup, QPoint(0, 0)).x(),
        title.parentWidget().mapTo(setup, QPoint(0, 0)).x(),
    )


@pytest.mark.parametrize("text", ["normal", "large"])
@pytest.mark.parametrize("size", SIZES)
def test_every_page_starts_at_one_left_edge(qapp: QApplication, size: tuple[int, int], text: str) -> None:
    """A page that scrolls sat 6 px left of one that did not, since the bar took room from the middle;
    and the rail changed width with the bold step."""
    with dressed(qapp, size, text) as (setup, _palette):
        seen: dict[int, tuple[int, int]] = {}
        scrolls = set()
        for step in STEPS:
            setup._show(step)
            qapp.processEvents()
            seen[step] = left_edge(setup, step)
            if setup.pages[step].verticalScrollBar().maximum() > 0:
                scrolls.add(step)
        assert scrolls, "the test needs a page with a scroll bar to mean anything"
        assert len(set(seen.values())) == 1, seen


@pytest.mark.parametrize("size", SIZES)
def test_the_day_pills_are_level_with_the_time_boxes(qapp: QApplication, size: tuple[int, int]) -> None:
    with dressed(qapp, size) as (setup, _palette):
        setup._show(WEEK)
        qapp.processEvents()
        row = setup.activities[0]
        for days, times in ((setup.school_days, setup.school_times), (row.days, row.times)):
            pill = days.buttons[0]
            field = times.start
            pill_mid = pill.mapTo(setup, QPoint(0, pill.height() // 2)).y()
            field_mid = field.mapTo(setup, QPoint(0, field.height() // 2)).y()
            assert abs(pill_mid - field_mid) <= 1, (pill_mid, field_mid)


def test_bedtime_sits_in_a_card_as_wide_as_its_neighbours(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        setup._show(WEEK)
        qapp.processEvents()
        card = setup.cutoff.parentWidget()
        assert isinstance(card, QFrame) and card.objectName() == "setupGroup"
        school = setup.school_times.parentWidget().parentWidget()
        assert card.mapTo(setup, QPoint(0, 0)).x() == school.mapTo(setup, QPoint(0, 0)).x()
        assert card.width() == school.width()


def edge_differs(button: QPushButton) -> bool:
    """Whether the button has an edge drawn: its outermost pixel is not the one just inside it."""
    image = button.grab().toImage()
    middle = button.height() // 2
    return image.pixelColor(0, middle) != image.pixelColor(6, middle)


def test_remove_and_skip_are_outlined_buttons(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        setup._show(WEEK)
        qapp.processEvents()
        removes = [b for b in setup.pages[WEEK].findChildren(QPushButton) if b.text() == "Remove"]
        setup._show(FIRST)
        qapp.processEvents()
        removes += [b for b in setup.pages[FIRST].findChildren(QPushButton) if b.text() == "Remove"]
        assert len(removes) == 2
        for button in [*removes, setup.skip]:
            assert button.property("outline") is True, button.text()
            assert edge_differs(button), button.text()


def test_takes_is_on_the_line_of_its_box(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        setup._show(FIRST)
        qapp.processEvents()
        row = setup.homework_rows[0]
        label = next(child for child in row.findChildren(QLabel) if child.text() == "Takes")
        label_mid = label.mapTo(setup, QPoint(0, label.height() // 2)).y()
        box_mid = row.minutes.mapTo(setup, QPoint(0, row.minutes.height() // 2)).y()
        assert abs(label_mid - box_mid) <= 2, (label_mid, box_mid)


def test_the_summary_says_things_one_way(qapp: QApplication) -> None:
    blocks = [
        {"id": "school", "title": "School", "kind": "locked", "category": "class", "days": [0, 1, 2, 3, 4],
         "start": "08:00", "duration_min": 390},
        {"id": "activity-1", "title": "Soccer", "kind": "locked", "category": "exercise",
         "days": [1, 3], "start": "15:30", "duration_min": 90},
    ]
    with dressed(qapp, blocks=blocks) as (setup, _palette):
        setup._state.pack = "system"
        setup._show(DONE)
        text = setup.summary_text()
        assert text[0] == "Today's app in your system's colours"
        assert all(";" not in line for line in text), text
        assert " · " in text[1] and "Soccer" in text[1], text[1]


def under_footer(setup: SetupPage) -> int:
    return setup.footer.mapTo(setup, QPoint(0, 0)).y()


@pytest.mark.parametrize("size", SIZES)
def test_the_last_card_on_homework_time_ends_above_the_footer(
    qapp: QApplication, size: tuple[int, int]
) -> None:
    with dressed(qapp, size) as (setup, _palette):
        setup._show(HOMEWORK)
        qapp.processEvents()
        for _ in range(9):
            setup.work_editor.add_button.click()
        page = setup.pages[HOMEWORK]
        bar = page.verticalScrollBar()
        # A scroll area learns its page's new height from posted requests, which a busy machine
        # runs later than a fixed 30 ms wait allowed for.
        deadline = time.monotonic() + 5
        while bar.maximum() == 0 and time.monotonic() < deadline:
            qapp.processEvents()
        assert bar.maximum() > 0, "the card does not run past the page, so this proves nothing"
        bar.setValue(bar.maximum())
        qapp.processEvents()
        editor = setup.work_editor
        bottom = editor.mapTo(setup, QPoint(0, editor.height())).y()
        assert bottom <= under_footer(setup), (bottom, under_footer(setup))


def test_the_page_fades_into_the_footer(qapp: QApplication) -> None:
    """Where a card sits under the footer's fade, a row of pixels is the card dissolving into the page's
    colour: not the card's, not yet the page's, and nearer the page's the nearer the buttons."""
    with dressed(qapp, SIZES[1]) as (setup, palette):
        setup._show(WEEK)
        for _ in range(5):
            setup._add_activity()
        qapp.processEvents()
        setup.pages[WEEK].verticalScrollBar().setValue(0)
        qapp.processEvents()
        picture = setup.grab().toImage()
        top = under_footer(setup)
        x = setup.activities[0].mapTo(setup, QPoint(40, 0)).x()
        ground, card = QColor(palette["window"]), QColor(palette["panel"])
        assert ground != card
        above = picture.pixelColor(x, top - 4)
        high = picture.pixelColor(x, top + 3)
        low = picture.pixelColor(x, top + FADE_PX - 3)
        assert above == card, "above the fade the card is as it is"
        assert high not in (card, ground) and low not in (card, ground), (high, low)
        assert abs(low.red() - ground.red()) < abs(high.red() - ground.red()) < abs(card.red() - ground.red())
