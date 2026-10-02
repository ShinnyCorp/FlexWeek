"""Part D of the desk comparisons: the minor review repairs against frozen Python."""

from __future__ import annotations

import json

import pytest

import desk_ref.calendar as ref_calendar
import desk_ref.focus as ref_focus
import desk_ref.look as ref_look
import desktop.native.calendar as live_calendar
import desktop.native.focus as live_focus
import desktop.native.look as live_look
import desktop.tests.test_engine_desk_parity as base


@pytest.mark.parametrize("assignments", [{}, {"a1": None}])
def test_restore_state_treats_a_null_assignment_as_missing(assignments):
    saved = {"phase": "work", "weekStart": "2026-09-28", "cycles": 0,
             "endsAt": 10000, "assignmentId": "a1"}
    assert ref_focus.restore_state(saved, assignments=assignments, blocks=[], now_ms=5000) is None
    base.same(live_focus.restore_state, ref_focus.restore_state, saved,
              assignments=assignments, blocks=[], now_ms=5000)


def test_deleting_a_whole_block_does_not_read_its_days():
    blocks = [{"id": "x", "title": "t"}, {"id": "y"}]
    assert ref_calendar.delete_occurrence(blocks, "x", None) == [{"id": "y"}]
    base.same(live_calendar.delete_occurrence, ref_calendar.delete_occurrence, blocks, "x", None)


@pytest.mark.parametrize("hue", [-0.0, -360.0, 0.0, 360.0])
def test_category_hue_serializes_zero_without_a_sign(hue):
    raw = {"base": "light", "categories": {"class": {"hue": hue}}}
    expected = ref_look.sanitize_custom(raw)
    assert expected[0]["categories"]["class"]["hue"] == 0.0
    assert json.dumps(live_look.sanitize_custom(raw)) == json.dumps(expected)
