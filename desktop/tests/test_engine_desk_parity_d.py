"""Part D of the desk comparisons: the minor review repairs against frozen Python."""

from __future__ import annotations

import json

import pytest

import desk_ref.calendar as ref_calendar
import desk_ref.focus as ref_focus
import desk_ref.look as ref_look
import desk_ref.tokens as ref_tokens
import desk_ref.weekmodel as ref_week
import desktop.native.calendar as live_calendar
import desktop.native.focus as live_focus
import desktop.native.look as live_look
import desktop.native.tokens as live_tokens
import desktop.native.weekmodel as live_week
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


@pytest.mark.parametrize("grounds, expected", [(('#ffffff',), '#000000'), ((), '#777777')])
def test_nan_contrast_floor_keeps_pythons_comparison(grounds, expected):
    floor = float("nan")
    assert ref_tokens.fit_lightness("#777777", grounds, floor) == expected
    base.same(live_tokens.fit_lightness, ref_tokens.fit_lightness, "#777777", grounds, floor)


def test_week_methods_accept_whole_float_fields():
    def observed(module):
        row = module.Occurrence("b", "Math", "assignments", 1.0, 540.0, 600.0,
                                True, False, False, "a1", None, None)
        waiting = module.Waiting("w", "English", "assignments", 30.0, "a2", "2026-09-29", "")
        model = module.WeekModel("2026-09-28", (row,), (waiting,))
        assert model.on_day(1)[0] is row
        assert model.load_min(1) == 60
        assert model.minutes_left_today(1, 540) == 90

    base.same(lambda: observed(live_week), lambda: observed(ref_week))


@pytest.mark.parametrize("method", ["on_day", "load_min", "open_work"])
def test_unhashable_week_models_use_the_engine_without_caching(method):
    blocks = [{"id": "b1", "title": "HW", "kind": "flexible", "assignment_id": "a1",
               "start": "16:00", "duration_min": 60, "days": [0]}]
    assignments = {"a1": {"due": ["2026-10-05"]}}

    def observed(module):
        model = module.build_week("2026-09-28", blocks, assignments, None)
        if method == "load_min":
            return model.load_min(0)
        rows = model.on_day(0) if method == "on_day" else model.open_work()
        assert rows[0] is model.occurrences[0]
        return [row.block_id for row in rows]

    assert observed(ref_week) == (60 if method == "load_min" else ["b1"])
    base.same(lambda: observed(live_week), lambda: observed(ref_week))
