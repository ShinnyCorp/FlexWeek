"""The model rule a solver input must keep. The solver itself is tested in engine/engine/tests/test_solver.rs."""

from __future__ import annotations

import pytest

from backend.models import TimeBlock


@pytest.mark.parametrize(
    "block",
    [
        {"kind": "locked", "start": "08:00", "days": [0]},
        {"kind": "flexible", "start": None, "days": [0]},
        {"kind": "flexible", "start": "15:00", "days": [0, 1]},
    ],
)
def test_pinned_is_refused_where_it_means_nothing(block: dict) -> None:
    with pytest.raises(ValueError, match="pinned"):
        TimeBlock(id="x", title="X", duration_min=60, pinned=True, **block)
