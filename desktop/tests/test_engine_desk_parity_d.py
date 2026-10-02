"""Part D of the desk comparisons: the minor review repairs against frozen Python."""

from __future__ import annotations

import pytest

import desk_ref.focus as ref_focus
import desktop.native.focus as live_focus
import desktop.tests.test_engine_desk_parity as base


@pytest.mark.parametrize("assignments", [{}, {"a1": None}])
def test_restore_state_treats_a_null_assignment_as_missing(assignments):
    saved = {"phase": "work", "weekStart": "2026-09-28", "cycles": 0,
             "endsAt": 10000, "assignmentId": "a1"}
    assert ref_focus.restore_state(saved, assignments=assignments, blocks=[], now_ms=5000) is None
    base.same(live_focus.restore_state, ref_focus.restore_state, saved,
              assignments=assignments, blocks=[], now_ms=5000)
