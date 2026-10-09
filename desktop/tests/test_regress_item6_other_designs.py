"""Item 6 in the designs that draw their own hours (Timeline, Mission, Bento, Retro and Clay): a press on
the hours moves the keyboard spot and hides the ring, the sheet it opens gives the keyboard back to that
spot, Shift+F10 asks about it, and a saved new block gets the keyboard. The same steps as
test_regress_item6_keyboard_after_sheet.py, which covers Today's app. Clay is not here: it draws one canvas
for each day, and a press on a side card brings that card to the front before it creates anything."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from desktop.native.hours.canvas import HoursCanvas
from desktop.native.hours.geometry import Axis
from desktop.native.layouts.registry import sanitize_layout
from desktop.native.weekmodel import clock_text
from desktop.tests.grid_support import (  # noqa: F401
    grid,
    key,
    menus,
    qapp,
    server,
    settled,
    signed_in,
    signed_out,
    window,
)
from desktop.tests.test_regress_item6_keyboard_after_sheet import (
    MONDAY,
    SCHOOL,
    THURSDAY,
    click_with_sheet,
    escape,
    name_and_save,
)

DESIGNS = ("timeline", "mission", "bento", "retro")


def in_design(qapp, window, design: str) -> HoursCanvas:
    """The window in `design` on Wednesday noon with School saved, and the hours that show Monday and
    Thursday both."""
    noon = datetime.fromisoformat(window.session.week_start) + timedelta(days=2, hours=12)
    window.session.now_ms = lambda: int(noon.timestamp() * 1000)
    window.session.add_block(dict(SCHOOL))
    window.session.save()
    settled(qapp, window)
    window._layout = sanitize_layout({"main": design, "day": "one"})
    window._apply_appearance()
    window._on_week()
    settled(qapp, window)
    shown = window.planner.currentWidget().hours_surfaces()
    both = [s for s in shown if s.track_for(MONDAY, 9 * 60) and s.track_for(THURSDAY, 19 * 60)]
    assert both, f"{design} shows no hours with Monday and Thursday"
    hours = both[0]
    hours.take_focus(True, ("school", MONDAY, 8 * 60))
    qapp.processEvents()
    assert hours.focus_block() == ("school", MONDAY) and hours.ring_shown
    return hours


@pytest.mark.parametrize("design", DESIGNS)
def test_after_a_click_and_esc_the_spot_is_the_clicked_slot_and_only_it_is_focused(
    qapp, window, menus, design
) -> None:
    hours = in_design(qapp, window, design)
    assert click_with_sheet(qapp, window, hours, THURSDAY, 19 * 60, escape) == ["blockDialog"]
    assert window.focusWidget() is hours, "the keyboard did not come back to the hours"
    assert hours.focus_slot() == (THURSDAY, 19 * 60)
    assert not hours.ring_shown
    assert window.session.selected_block_id is None, "School keeps its outline while the spot is elsewhere"
    key(window, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
    asked = [(shown["name"], shown["rows"][0]) for shown in menus]
    assert asked == [("spotMenu", f"Add fixed time at {clock_text(19 * 60)}")], asked


@pytest.mark.parametrize("design", DESIGNS)
def test_a_saved_new_block_gets_the_keyboard(qapp, window, design) -> None:
    hours = in_design(qapp, window, design)
    assert click_with_sheet(qapp, window, hours, THURSDAY, 19 * 60, name_and_save) == ["blockDialog"]
    settled(qapp, window)
    club = next((b for b in window.session.blocks if b["title"] == "Club"), None)
    assert club is not None, "the new block was not saved"
    shown = window.planner.currentWidget().hours_surfaces()
    spot = [s.focus_block() for s in shown if s.hasFocus()]
    assert spot == [(club["id"], THURSDAY)], spot


@pytest.mark.parametrize("design", DESIGNS)
def test_clicking_school_then_closing_its_sheet_moves_right_from_school(qapp, window, design) -> None:
    hours = in_design(qapp, window, design)
    hours.take_focus(True, ("school", MONDAY, 8 * 60))
    click_with_sheet(qapp, window, hours, MONDAY, 10 * 60, escape)
    # Where time runs across, the days are up and down.
    across = hours.track_for(MONDAY).axis is Axis.ACROSS
    key(window, Qt.Key.Key_Down if across else Qt.Key.Key_Right)
    assert hours.focus_slot()[0] == MONDAY + 1
    assert hours.focus_block() == ("school", MONDAY + 1)

