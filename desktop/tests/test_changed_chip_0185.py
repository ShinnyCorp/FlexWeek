"""0.18.5 #94: the look editor's Changed chip reads at 4.5 to 1 on its tint."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("PySide6")

from desktop.native.look import resolved_palette, sanitize_look
from desktop.native.look_editor import editor_rules
from desktop.native.tokens import contrast

PRESETS = ("default", "paper", "ink", "pastel", "terminal", "poster", "high-contrast")
# A pale accent is the case where the plain accent cannot be words on its own tint.
ACCENTS = ("default", "gold", "sand", "#dfff00", "#809dce")


def chip_colours(css: str) -> tuple[str, str]:
    rule = re.search(r"QLabel#lookTag \{ background: (#[0-9a-f]{6}|transparent); color: (#[0-9a-f]{6});", css)
    return rule.group(1), rule.group(2)


@pytest.mark.parametrize("accent", ACCENTS)
@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_the_changed_chip_reads_at_4_5_to_1_on_its_tint(pack: str, accent: str) -> None:
    palette = resolved_palette(pack, False, None, accent)
    tint, words = chip_colours(editor_rules(palette, 6))
    assert contrast(words, tint) >= 4.5, (pack, accent, words, tint)


@pytest.mark.parametrize("preset", PRESETS)
def test_the_changed_chip_reads_in_every_look(preset: str) -> None:
    look = sanitize_look({"preset": preset})
    palette = resolved_palette("light-frost", False, look)
    tint, words = chip_colours(editor_rules(palette, 6))
    ground = palette["panel"] if tint == "transparent" else tint
    assert contrast(words, ground) >= 4.5, (preset, words, ground)
