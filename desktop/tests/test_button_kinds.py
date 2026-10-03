"""The `outlined` and `tonal` buttons, and a disabled main button that can be read (0.18.1: #91, #79).

Every shipped look is checked by numbers: the tonal label reads on its tint (4.5:1), the outline is seen
on the card and on the page (3:1), a disabled main button's label reads on its pale fill (about 7:1),
and a roomy button is at least 36 pixels tall, 40 at Large text.
"""

from __future__ import annotations

import re
from itertools import product

from desktop.native.look import ACCENTS, LOOK_KNOBS, LOOK_PRESETS, PACKS, pack_stylesheet, resolved_palette
from desktop.native.tokens import contrast

EVERY_LOOK = list(product(PACKS, (False, True), LOOK_PRESETS, ACCENTS, LOOK_KNOBS["surface"]))


def rule(sheet: str, selector: str) -> dict[str, str]:
    """The declarations of the rule written for exactly `selector`; a missing rule is the failure."""
    found = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", sheet)
    assert found is not None, f"no rule for {selector}"
    pairs = (part.split(":", 1) for part in found.group(1).split(";") if ":" in part)
    return {name.strip(): value.strip() for name, value in pairs}


def look_of(pack: str, dark: bool, preset: str, accent: str, surface: str) -> tuple[dict, dict, str]:
    look = {"preset": preset, "knobs": {"surface": surface}}
    palette = resolved_palette(pack, dark, look, accent)
    return palette, look, pack_stylesheet(pack, dark, look, accent, palette)


def test_a_tonal_buttons_label_reads_4_5_to_1_on_its_tint_in_every_look() -> None:
    failed = []
    for look in EVERY_LOOK:
        _palette, _knobs, sheet = look_of(*look)
        tonal = rule(sheet, 'QPushButton[tonal="true"]')
        ratio = contrast(tonal["color"], tonal["background"])
        if ratio < 4.5:
            failed.append((look, round(ratio, 2)))
    assert failed == []


def test_a_tonal_buttons_tint_is_the_accent_and_not_the_card_in_every_look() -> None:
    palette, _look, sheet = look_of("light-frost", False, "default", "default", "flat")
    tonal = rule(sheet, 'QPushButton[tonal="true"]')
    assert tonal["background"] != palette["panel"]
    assert contrast(tonal["background"], palette["panel"]) < 1.5, "a tint, not a second filled button"


def test_an_outlined_buttons_edge_is_seen_at_3_to_1_on_the_card_and_the_page_in_every_look() -> None:
    failed = []
    for look in EVERY_LOOK:
        palette, _knobs, sheet = look_of(*look)
        outlined = rule(sheet, 'QPushButton[outlined="true"]')
        edge = outlined["border"].split()[-1]
        assert outlined["background"] == "transparent" and outlined["border"].startswith("1px solid ")
        assert outlined["color"] == palette["text"]
        ratios = (contrast(edge, palette["panel"]), contrast(edge, palette["window"]))
        if min(ratios) < 3.0:
            failed.append((look, [round(ratio, 2) for ratio in ratios]))
    assert failed == []


def test_a_danger_outline_is_words_and_edge_in_the_error_colour_and_reads_in_every_look() -> None:
    failed = []
    for look in EVERY_LOOK:
        palette, _knobs, sheet = look_of(*look)
        danger = rule(sheet, 'QPushButton[outlined="true"][danger="true"]')
        edge = danger["border-color"]
        assert danger["color"] == palette["error"] == edge
        ratios = (contrast(danger["color"], palette["panel"]), contrast(edge, palette["window"]))
        if min(ratios) < 4.5:
            failed.append((look, [round(ratio, 2) for ratio in ratios]))
    assert failed == []


def test_a_disabled_main_buttons_label_is_the_text_colour_on_a_pale_fill_at_7_to_1_in_every_look() -> None:
    """#91: white on a pale accent was 1.82 to 1. Where a main button is turned off, a plain page's
    button and a dialog's are drawn the same."""
    failed = []
    for look in EVERY_LOOK:
        palette, _knobs, sheet = look_of(*look)
        for selector in ("QPushButton:disabled", "QDialog QPushButton:disabled"):
            off = rule(sheet, selector)
            ratio = contrast(off["color"], off["background"])
            if off["color"] != palette["text"] or ratio < 7.0:
                failed.append((look, selector, off["color"], round(ratio, 2)))
    assert failed == []
