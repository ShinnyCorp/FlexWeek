"""Setup's Style page as the round 2 mock-up's option C drew it: one style's picture large in the middle,
the neighbours peeking dimmed, arrows and a dot each below, the name and one note, and the middle is
the chosen style."""

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
    from PySide6.QtCore import QPoint, QStandardPaths, Qt
    from PySide6.QtGui import QColor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QPushButton, QWidget

    from desktop.native import motion
    from desktop.native.calendar import monday_of
    from desktop.native.layouts.registry import LAYOUTS, sanitize_layout
    from desktop.native.look import pack_stylesheet, resolved_palette, sanitize_look
    from desktop.native.setup import (
        EXPERIMENTAL_TAG,
        LOOK,
        PEEK_PX,
        STYLE,
        STYLES,
        WEEK,
        SetupPage,
        SetupState,
        style_layout,
        style_look,
    )
    from desktop.native.widgets import control_art

SIZES = ((1280, 800), (1280, 680))
ORDER = ["plain", "night", "dashboard", "retro"]


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    app = QApplication.instance() or QApplication(["flexweek-setup-carousel-test"])
    motion.apply_ui_effects("off")
    return app


@contextmanager
def dressed(
    qapp: QApplication,
    size: tuple[int, int] = SIZES[0],
    text: str = "normal",
    first_run: bool = True,
    layout: dict | None = None,
    look: dict | None = None,
    pack: str = "light-frost",
) -> Iterator[tuple[SetupPage, dict]]:
    """Setup in this window size, with the window's stylesheet, as a new account sees it."""
    look = sanitize_look(look or {"preset": "default", "knobs": {"text": text}})
    palette = resolved_palette(pack, False, look)
    host = QWidget()
    host.setStyleSheet(pack_stylesheet(pack, False, look, "default", palette, control_art(palette)))
    setup = SetupPage(host)
    setup.motion = "off"
    setup.set_palette(palette)
    state = SetupState(pack, look, sanitize_layout(layout), {}, [], monday_of("2026-09-23"))
    state.first_run = first_run
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


def middle(setup: SetupPage) -> str:
    return setup.carousel.key()


def opacity(slide: QWidget) -> float:
    effect = slide.graphicsEffect()
    assert isinstance(effect, QGraphicsOpacityEffect)
    return effect.opacity()


@pytest.mark.parametrize("size", SIZES)
def test_the_picture_stands_in_the_middle_and_the_neighbours_peek_dimmed(
    qapp: QApplication, size: tuple[int, int]
) -> None:
    with dressed(qapp, size) as (setup, _palette):
        stage = setup.carousel.stage
        slides = setup.style_cards
        front = slides["plain"]
        assert abs((front.x() + front.width() // 2) - stage.width() // 2) <= 1
        following, previous = slides["night"], slides["retro"]
        assert following.x() < stage.width() <= following.x() + following.width()
        assert stage.width() - following.x() >= PEEK_PX, "enough of the next one shows to be seen"
        assert previous.x() < 0 < previous.x() + previous.width()
        assert previous.x() + previous.width() >= PEEK_PX
        assert opacity(front) == 1.0
        assert opacity(following) < 0.8 and opacity(previous) < 0.8
        assert front.width() > 2 * (stage.width() - following.x()), "the middle is the big one"


@pytest.mark.parametrize("size", SIZES)
def test_nothing_on_the_style_page_scrolls(qapp: QApplication, size: tuple[int, int]) -> None:
    with dressed(qapp, size) as (setup, _palette):
        assert setup.pages[STYLE].verticalScrollBar().maximum() == 0


def test_the_default_style_is_chosen_from_the_start_and_next_keeps_it(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, palette):
        assert setup.style_cards["plain"].is_selected()
        assert [key for key, slide in setup.style_cards.items() if slide.is_selected()] == ["plain"]
        assert setup.carousel.dots["plain"].property("chosen") is True
        assert not any(setup.carousel.dots[key].property("chosen") for key in ORDER[1:])
        # The ring is drawn in the accent, not only flagged.
        slide = setup.style_cards["plain"]
        assert slide.grab().toImage().pixelColor(1, slide.height() // 2) == QColor(palette["accent"])
        answer = setup._answer(STYLE)
        assert answer is not None
        assert answer["layout"]["main"] == "classic" and answer["pack"] == "light-frost"


def test_next_uses_whatever_is_in_the_middle(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        kept = []
        setup.left.connect(lambda step, destination, answer: kept.append((step, destination, answer)))
        setup.carousel.step(1)
        setup.next.click()
        step, destination, answer = kept[0]
        assert (step, destination) == (STYLE, WEEK)
        assert answer["layout"]["main"] == "timeline"
        assert answer["look"]["knobs"]["density"] == "compact"


def test_skipping_the_step_keeps_the_look_it_had_even_with_a_style_chosen(qapp: QApplication) -> None:
    with dressed(qapp, pack="system") as (setup, _palette):
        kept = []
        setup.left.connect(lambda step, destination, answer: kept.append(answer))
        setup.carousel.step(1)
        setup.skip.click()
        assert kept == [None]
        assert setup._pack == "system"


def test_left_and_right_move_the_middle_and_wrap_round(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        seen = []
        setup.previewed.connect(lambda shown: seen.append(shown["layout"]["main"]))
        setup.carousel.setFocus()
        QTest.keyClick(setup.carousel, Qt.Key.Key_Right)
        assert middle(setup) == "night"
        assert setup.style_cards["night"].is_selected() and not setup.style_cards["plain"].is_selected()
        QTest.keyClick(setup.carousel, Qt.Key.Key_Left)
        QTest.keyClick(setup.carousel, Qt.Key.Key_Left)
        assert middle(setup) == "retro", "the last style stands left of the first"
        assert seen == ["timeline", "classic", "retro"], "each move shows the look as it is picked"
        QTest.keyClick(setup.carousel, Qt.Key.Key_Right)
        assert middle(setup) == "plain"


def test_the_arrows_and_the_dots_move_it_too(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        setup.carousel.following.click()
        assert middle(setup) == "night"
        setup.carousel.previous.click()
        setup.carousel.previous.click()
        assert middle(setup) == "retro"
        setup.carousel.dots["dashboard"].click()
        assert middle(setup) == "dashboard"
        assert setup.carousel.dots["dashboard"].property("chosen") is True
        assert setup.carousel.dots["retro"].property("chosen") is False


def test_a_click_on_a_peeking_card_brings_it_to_the_middle(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        peeking = setup.style_cards["night"]
        stage = setup.carousel.stage
        # A point in the part of it that shows, in its own coordinates.
        visible = QPoint(stage.width() - 10 - peeking.x(), peeking.height() // 2)
        QTest.mouseClick(peeking, Qt.MouseButton.LeftButton, pos=visible)
        assert middle(setup) == "night"
        assert setup.style_cards["night"].is_selected()
        assert abs(peeking.x() + peeking.width() // 2 - stage.width() // 2) <= 1
        assert opacity(peeking) == 1.0


def test_the_name_and_one_note_belong_to_the_middle_one(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        assert (setup.carousel.name.text(), setup.carousel.note.text()) == (
            "Plain calendar",
            "Your week as a timetable grid",
        )
        setup.carousel.step(2)
        assert setup.carousel.name.text() == "Dashboard"
        assert setup.carousel.note.text() == "Next up and due soon, as tiles"


def test_no_note_repeats_the_name_of_the_layout(qapp: QApplication) -> None:
    for style in STYLES:
        if style.key == "retro":
            continue  # its note is the mock-up's own words; "Retro" is both the style and the design
        assert LAYOUTS[style.main].label.casefold() not in style.note.casefold(), style.key
        assert "·" not in style.note


def test_only_the_experimental_styles_carry_the_tag_and_they_come_last(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        assert list(setup.style_cards) == ORDER
        tagged = [key for key, slide in setup.style_cards.items() if slide.tag is not None]
        assert tagged == ["dashboard", "retro"]
        for key in tagged:
            assert setup.style_cards[key].tag.text() == EXPERIMENTAL_TAG


def test_running_setup_again_opens_on_the_style_in_use_and_a_custom_look_chooses_nothing(
    qapp: QApplication,
) -> None:
    night = next(style for style in STYLES if style.key == "night")
    with dressed(
        qapp,
        first_run=False,
        layout=style_layout(night, sanitize_layout(None)),
        look=style_look(night),
        pack=night.pack,
    ) as (setup, _palette):
        assert middle(setup) == "night" and setup.style_cards["night"].is_selected()
    with dressed(qapp, first_run=False, layout={"main": "mission"}) as (setup, _palette):
        assert not any(slide.is_selected() for slide in setup.style_cards.values())
        assert setup._answer(STYLE) is None, "Next on a look of their own keeps it"


def test_the_own_look_button_is_outlined(qapp: QApplication) -> None:
    with dressed(qapp) as (setup, _palette):
        own = setup.pages[STYLE].findChild(QPushButton, "setupOwnLook")
        assert own.property("outline") is True
        image = own.grab().toImage()
        assert image.pixelColor(0, own.height() // 2) != image.pixelColor(6, own.height() // 2)
        own.click()
        assert setup.step == LOOK


def _middle_slot(setup: SetupPage) -> tuple[int, int]:
    stage, front = setup.carousel.stage, setup.style_cards[middle(setup)]
    return front.width() // 4, stage.width() - front.width() // 4


@pytest.mark.parametrize("delta", [1, -1])
def test_a_step_slides_to_the_same_places_a_jump_puts_them(qapp: QApplication, delta: int) -> None:
    """Sliding, including the card that wraps from one end to the other, ends where setting it at once
    does, and the neighbours are dimmed and the middle is bright when it stops."""
    with dressed(qapp) as (setup, _palette):
        setup.motion = "normal"
        for _ in range(6):
            setup.carousel.step(delta)
            QTest.qWait(450)
            seen = {key: slide.geometry() for key, slide in setup.style_cards.items()}
            setup.carousel._arrange(delta=0)
            for key, slide in setup.style_cards.items():
                if slide.x() + slide.width() > 0 and slide.x() < setup.carousel.stage.width():
                    assert slide.geometry() == seen[key], key
                assert (opacity(slide) == 1.0) == (key == middle(setup)), key


@pytest.mark.parametrize("delta", [1, -1])
def test_no_card_crosses_the_middle_while_the_others_slide(qapp: QApplication, delta: int) -> None:
    """A card wrapping from one end to the other leaves by the edge it was heading for, and a card that
    has just done so does not come back across the stage on the next step."""
    with dressed(qapp) as (setup, _palette):
        setup.motion = "normal"
        for _ in range(6):
            before = middle(setup)
            setup.carousel.step(delta)
            after = middle(setup)
            low, high = _middle_slot(setup)
            for _frame in range(40):
                QTest.qWait(10)
                for key, slide in setup.style_cards.items():
                    if key not in (before, after):
                        centre = slide.x() + slide.width() // 2
                        assert not low < centre < high, (key, slide.geometry())
            QTest.qWait(300)
