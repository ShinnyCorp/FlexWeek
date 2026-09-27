"""Lucide's icons, the type scale and the two shadows: the pieces every 0.17 screen is drawn with."""

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
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication, QWidget

    from desktop.native import icons
    from desktop.native.elevation import lift
    from desktop.native.tokens import SHADOW_LARGE, SHADOW_SMALL, type_pt


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-icons-test"])


# Decision 7's list, and what the mock-up's screens use on top of it.
PLANNED = (
    "settings",
    "chevron-left",
    "chevron-right",
    "chevron-down",
    "plus",
    "minus",
    "search",
    "book-open",
    "trash",
    "copy",
    "check",
    "eye",
    "eye-off",
    "clock",
    "calendar",
    "bell",
    "palette",
    "laptop",
    "timer",
    "log-out",
    "pin",
    "pencil",
    "undo-2",
    "x",
)


def test_every_icon_the_plan_names_ships_with_its_licence() -> None:
    assert set(PLANNED) <= set(icons.names())
    assert "ISC License" in (icons.ICON_DIR / "LICENSE.txt").read_text(encoding="utf-8")


def test_an_icon_is_drawn_in_the_colour_asked_at_the_systems_stroke(qapp: QApplication) -> None:
    assert b'stroke-width="1.75"' in icons.svg("plus", "#111827")
    drawn = icons.pixmap("plus", "#c42b1c", 20).toImage()
    # A 1.75 stroke on a 24 grid is under two pixels wide at 20, so no pixel is wholly covered.
    inked = [
        drawn.pixelColor(x, y)
        for x in range(drawn.width())
        for y in range(drawn.height())
        if drawn.pixelColor(x, y).alpha() >= 128
    ]
    assert inked, "the plus drew nothing"
    red = QColor("#c42b1c")
    assert all(
        max(abs(seen.red() - red.red()), abs(seen.green() - red.green()), abs(seen.blue() - red.blue())) <= 3
        for seen in inked
    ), {seen.name() for seen in inked}
    assert drawn.pixelColor(0, 0).alpha() == 0, "the corner stays clear"


def test_an_icon_is_sharp_on_a_high_density_screen(qapp: QApplication) -> None:
    drawn = icons.pixmap("clock", "#111827", 16, 2.0)
    assert (drawn.width(), drawn.height()) == (32, 32)
    assert drawn.devicePixelRatio() == 2.0


def test_the_type_scale_is_five_sizes_that_small_and_large_scale_together() -> None:
    roles = ("caption", "body", "heading", "title", "display")
    assert [type_pt(role) for role in roles] == [11, 13, 15, 20, 28]
    assert type_pt("body", "small") < type_pt("body") < type_pt("body", "large")
    assert type_pt("display", "large") / type_pt("display") == pytest.approx(1.2, abs=0.02)
    assert type_pt("body", 1.1) == 14.5


def test_a_lifted_card_casts_the_small_shadow_and_stronger_on_a_dark_look(qapp: QApplication) -> None:
    card = QWidget()
    effect = lift(card, SHADOW_SMALL)
    assert card.graphicsEffect() is effect
    assert (effect.offset().y(), effect.blurRadius()) == (1, 3)
    assert effect.color() == QColor(0, 0, 0, 20)
    dark = lift(card, SHADOW_LARGE, dark=True)
    assert card.graphicsEffect() is dark
    assert (dark.offset().y(), dark.blurRadius(), dark.color().alpha()) == (12, 32, 128)
