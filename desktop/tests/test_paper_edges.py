"""0.18.5 #60: Paper and Ink draw a 1 px warm edge on every card, at 3 to 1 on the page and the card."""

from __future__ import annotations

import re

import pytest

from desktop.native.look import pack_stylesheet, resolved_palette
from desktop.native.tokens import contrast
from desktop.tests.test_hours_painter import qapp as qapp

# Worked out from the requirement (mock-up round 3): only the lightness of Paper's strong hairline moves.
EDGES = {"paper": "#8f877a", "ink": "#706c65"}


def sheet(look: dict) -> str:
    return pack_stylesheet("system", False, look)


def card_rule(css: str) -> str:
    """The app-wide rule every card, group and list takes."""
    return re.search(r"QFrame, QGroupBox, QTableWidget, QListWidget \{[^}]*\}", css).group(0)


@pytest.mark.parametrize("preset", ["paper", "ink"])
def test_the_card_edge_is_warm_and_reaches_three_to_one_on_page_and_card(preset: str) -> None:
    palette = resolved_palette("system", False, {"preset": preset})
    assert palette["card_edge"] == EDGES[preset]
    for ground in ("window", "panel"):
        assert contrast(palette["card_edge"], palette[ground]) >= 3.0, (preset, ground)
    if preset == "paper":
        assert contrast(palette["card_edge"], palette["card_2"]) >= 3.0


@pytest.mark.parametrize("preset", ["paper", "ink"])
def test_every_card_in_paper_and_ink_has_the_edge(preset: str) -> None:
    css = sheet({"preset": preset})
    assert f"border: 1px solid {EDGES[preset]};" in card_rule(css)
    # Setup's choice cards and Settings' own cards draw it too, not a soft line or nothing.
    assert re.search(rf"QFrame#setupChoice \{{[^}}]*border: 2px solid {EDGES[preset]}", css)
    assert re.search(rf"QFrame#settingsCard[^{{]*\{{[^}}]*border: 1px solid {EDGES[preset]}", css)


def test_other_flat_looks_keep_no_edge() -> None:
    css = sheet({"preset": "light", "knobs": {"depth": "none"}})
    assert "border: none;" in card_rule(css)
    assert "card_edge" not in resolved_palette("system", False, {"preset": "light"})


def test_paper_keeps_its_flat_look_when_shadows_are_off_and_bold_when_bold() -> None:
    assert "border: 4px" not in card_rule(sheet({"preset": "paper"}))
    assert "border-bottom: 4px" in card_rule(sheet({"preset": "paper", "knobs": {"depth": "bold"}}))


def test_a_countdown_ring_writes_its_figures_at_one_width_so_29_59_and_28_11_agree(qapp) -> None:
    from PySide6.QtGui import QFont

    from desktop.native.fonts import TABULAR
    from desktop.native.ring import CountdownRing

    ring = CountdownRing()
    ring.set_number("29:59")
    number, _unit = ring._fonts()
    assert number.featureValue(QFont.Tag(TABULAR)) == 1


def test_the_focus_timer_line_is_in_the_serif_looks_face_not_mono() -> None:
    def focus_time(css: str) -> str:
        return re.search(r"QLabel#focusTime \{[^}]*\}", css).group(0)

    for preset in ("paper", "ink"):
        rule = focus_time(sheet({"preset": preset}))
        assert "Newsreader" in rule and "Mono" not in rule, preset
    assert "Mono" in focus_time(sheet({"preset": "light"}))


def test_the_settings_focus_timer_keeps_one_width_for_every_figure(qapp) -> None:
    from PySide6.QtGui import QFont

    from desktop.native.fonts import TABULAR
    from desktop.native.settings import FocusPanel

    panel = FocusPanel()
    panel.setStyleSheet(sheet({"preset": "paper"}))
    panel.time.ensurePolished()
    assert panel.time.font().featureValue(QFont.Tag(TABULAR)) == 1
    assert panel.time.font().family() == "Newsreader"
