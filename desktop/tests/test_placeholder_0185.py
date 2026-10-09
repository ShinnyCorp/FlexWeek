"""0.18.5 #95: every text field's placeholder reads at 4.5 to 1 on its field."""

# ruff: noqa: F811  (pytest fixtures imported by name)

from __future__ import annotations

import re

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QVBoxLayout

from desktop.native.look import pack_stylesheet, resolved_palette, sanitize_look
from desktop.native.tokens import contrast
from desktop.tests.window_support import host, qapp  # noqa: F401

PRESETS = ("default", "paper", "ink", "pastel", "terminal", "poster", "high-contrast")


def placeholder_colour(css: str) -> str:
    rule = re.search(r"QLineEdit, QPlainTextEdit \{ placeholder-text-color: (#[0-9a-f]{6}); \}", css)
    return rule.group(1)


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_a_placeholder_reads_at_4_5_to_1_on_its_field_in_every_look(pack: str, preset: str) -> None:
    look = sanitize_look({"preset": preset})
    palette = resolved_palette(pack, False, look)
    css = pack_stylesheet(pack, False, look, "default", palette)
    for widget in ("QLineEdit", "QPlainTextEdit"):
        colour = placeholder_colour(css)
        assert contrast(colour, palette["field"]) >= 4.5, (pack, preset, widget, colour)
        assert contrast(colour, palette["panel"]) >= 4.5, (pack, preset, widget, colour)


def test_a_placeholder_is_drawn_in_that_colour_not_qts_default(qapp, host) -> None:
    palette = resolved_palette("light-frost", False, None)
    host.setStyleSheet(pack_stylesheet("light-frost", False, None, "default", palette))
    field, notes = QLineEdit(), QPlainTextEdit()
    field.setPlaceholderText("e.g. History essay")
    notes.setPlaceholderText("e.g. History essay")
    box = QVBoxLayout(host)
    box.addWidget(field)
    box.addWidget(notes)
    host.show()
    for _ in range(3):
        qapp.processEvents()
    wanted = QColor(placeholder_colour(host.styleSheet()))
    for widget in (field, notes):
        image = widget.grab().toImage()
        # A glyph's core pixels carry the words' own colour; Qt's default is a different one.
        core = sum(
            1
            for x in range(image.width())
            for y in range(image.height())
            if all(
                abs(a - b) <= 8
                for a, b in zip(image.pixelColor(x, y).getRgb()[:3], wanted.getRgb()[:3], strict=True)
            )
        )
        assert core >= 8, (type(widget).__name__, core)
