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


def test_replan_has_its_own_icon_and_it_ships(qapp: QApplication) -> None:
    """#26: Replan all my homework wore Activity's sparkles. Lucide's calendar-sync is its own."""
    from desktop.native.calendar import CATEGORIES
    from desktop.native.window import MORE_ICONS

    assert "calendar-sync" in icons.names()
    assert MORE_ICONS["replanAll"] == "calendar-sync"
    taken = {name for key, name in MORE_ICONS.items() if key != "replanAll"}
    taken |= {info.get("icon") for info in CATEGORIES.values()}
    assert "calendar-sync" not in taken
    assert set(MORE_ICONS.values()) <= set(icons.names()), "every icon More names has a file"
    drawn = icons.pixmap("calendar-sync", "#111827", 20).toImage()
    inked = [
        (x, y)
        for x in range(drawn.width())
        for y in range(drawn.height())
        if drawn.pixelColor(x, y).alpha() >= 128
    ]
    assert len(inked) > 20, "the SVG loads and draws"
    assert b"<path" in icons.svg("calendar-sync", "#111827") and b"currentColor" not in icons.svg(
        "calendar-sync", "#111827"
    )


def test_school_is_the_school_building_everywhere_it_has_an_icon() -> None:
    """#26: the block and the category were a house while School hours was a school building."""
    from desktop.native import calendar
    from desktop.native.calendar import CATEGORIES

    assert CATEGORIES["class"]["icon"] == "school"
    assert calendar.category_icon("class") == "school", "the engine draws the block with it"
    assert "school" in icons.names()


@pytest.mark.parametrize(("pack", "dark"), [("light-frost", False), ("dark-frost", True)])
def test_the_school_icon_reaches_4_5_to_1_on_its_block_and_its_edge_keeps_its_colour(
    qapp: QApplication, pack: str, dark: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QImage, QPainter

    from desktop.native.hours.canvas import BlockPainter, Drawn
    from desktop.native.hours.geometry import Span
    from desktop.native.look import AA_TEXT, category_paint, contrast, resolved_palette

    palette = resolved_palette(pack, dark, None)
    painter = BlockPainter(palette)
    drawn = Drawn("test", "School", "class", False, Span(0, 480, 660), 0, 1)
    fill, ink, _outline, edge = painter.fills(drawn)
    colour = painter._book_colour(drawn, ink, fill, edge)
    assert colour is not None
    assert contrast(colour.name(), fill.name()) >= AA_TEXT, (pack, colour.name(), fill.name())
    mark = category_paint("class", palette)[1]
    assert edge is None or edge.name() == mark, "the 3 px edge keeps the category's colour"

    used: list[tuple[str, str]] = []
    original = icons.pixmap

    def record(name, colour, *args):
        used.append((name, colour))
        return original(name, colour, *args)

    monkeypatch.setattr(icons, "pixmap", record)
    picture = QImage(500, 300, QImage.Format.Format_ARGB32)
    picture.fill(fill)
    paint = QPainter(picture)
    paint.setFont(QFont("Inter", 12))
    painter.words(paint, QRectF(0, 0, 480, 280), drawn, ink, QRectF(0, 0, 500, 300), fill, edge)
    paint.end()
    drawn_in = [colour for name, colour in used if name == "school"]
    assert drawn_in and all(contrast(seen, fill.name()) >= AA_TEXT for seen in drawn_in), used
