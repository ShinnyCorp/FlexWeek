"""The toast and the menus in every look (decisions 20 and 22 of 0.17), checked by numbers, and a menu's
shadow and place on screen."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from itertools import product

import pytest

from desktop.native.look import (
    ACCENTS,
    LOOK_KNOBS,
    LOOK_PRESETS,
    PACKS,
    contrast,
    hover_tint,
    luminance,
    pack_stylesheet,
    resolved_palette,
    toast_colours,
)

EVERY_LOOK = list(product(PACKS, (False, True), LOOK_PRESETS, ACCENTS, LOOK_KNOBS["surface"]))


def palette_of(pack: str, dark: bool, preset: str, accent: str, surface: str) -> dict:
    return resolved_palette(pack, dark, {"preset": preset, "knobs": {"surface": surface}}, accent)


def floor(palette: dict) -> float:
    return 7.0 if palette.get("family") == "contrast" else 4.5


def test_the_toast_is_dark_with_light_words_and_undo_reads_on_it_in_every_look() -> None:
    failed = []
    for look in EVERY_LOOK:
        palette = palette_of(*look)
        toast = toast_colours(palette)
        words = contrast(toast["text"], toast["background"])
        undo = contrast(toast["action"], toast["background"])
        dark = luminance(toast["background"]) < luminance(toast["text"])
        if min(words, undo) < floor(palette) or not dark:
            failed.append((look, round(words, 2), round(undo, 2), dark))
    assert failed == []


def test_undo_is_the_accents_light_shade_on_a_light_look_and_the_accent_on_a_dark_one() -> None:
    light = resolved_palette("light-frost", False, None)
    toast = toast_colours(light)
    assert toast["background"] == light["text"] and toast["text"] == light["window"]
    assert toast["action"] != light["accent"]
    assert luminance(toast["action"]) > luminance(light["accent"]), "lighter than the accent"
    dark = resolved_palette("dark-frost", True, None)
    assert toast_colours(dark)["action"] == dark["accent"]
    sheet = pack_stylesheet("light-frost", False, None)
    rule = sheet.split("QFrame#toast {")[1].split("}")[0]
    assert f"background: {light['text']};" in rule and "border-radius: 16px;" in rule


def test_a_row_under_the_pointer_shows_and_keeps_its_words_readable_in_every_look() -> None:
    failed = []
    for look in EVERY_LOOK:
        palette = palette_of(*look)
        hover = hover_tint(palette)
        if hover == palette["panel"] or contrast(palette["text"], hover) < floor(palette):
            failed.append(look)
        if contrast(palette["error"], hover) < 4.5:
            failed.append((look, "delete"))
        # On black, a step of 6 % is black again; High contrast's row stands a visible step off it.
        if palette.get("family") == "contrast" and contrast(hover, palette["panel"]) < 1.5:
            failed.append((look, "unseen"))
    assert failed == []


if importlib.util.find_spec("PySide6") is not None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget

    from desktop.native.look import MENU_EDGE
    from desktop.native.menus import Menu, menu_colours
    from desktop.native.tokens import SHADOW_LARGE


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    pytest.importorskip("PySide6")
    yield QApplication.instance() or QApplication(["flexweek-overlays-test"])


def test_a_menu_casts_the_large_shadow_only_in_a_look_with_depth(qapp: QApplication) -> None:
    light = resolved_palette("light-frost", False, None)
    menu = Menu()
    menu.set_colours(menu_colours(light, lifted=True))
    shadow = menu.graphicsEffect()
    assert isinstance(shadow, QGraphicsDropShadowEffect)
    assert (shadow.offset().y(), shadow.blurRadius()) == (SHADOW_LARGE.y, SHADOW_LARGE.blur)
    inner = menu.add_menu("Undo, copy and save", "pencil")
    assert isinstance(inner.graphicsEffect(), QGraphicsDropShadowEffect), "a submenu too"
    menu.set_colours(menu_colours(light, lifted=False))
    assert menu.graphicsEffect() is None and inner.graphicsEffect() is None


def test_a_menus_panel_opens_where_qt_put_the_menu_with_its_shadow_round_it(qapp: QApplication) -> None:
    """The window is larger than the panel by the shadow's room on every side, so it is moved up and
    left by that room: the panel's corner is where the pointer was."""
    host = QWidget()
    host.setStyleSheet(pack_stylesheet("light-frost", False, None))
    menu = Menu(host)
    menu.add("Open", "pencil")
    menu.popup(QPoint(300, 200))
    qapp.processEvents()
    assert menu.pos() == QPoint(300 - MENU_EDGE, 200 - MENU_EDGE)
    first = menu.actionGeometry(menu.actions()[0])
    assert first.left() >= MENU_EDGE and first.top() >= MENU_EDGE, "the rows sit inside the panel"
    image = menu.grab().toImage()
    assert image.pixelColor(2, 2).alpha() == 0, "clear outside the panel"
    assert image.pixelColor(MENU_EDGE + 12, MENU_EDGE + 12).alpha() == 255, "the panel is solid"
    menu.close()
