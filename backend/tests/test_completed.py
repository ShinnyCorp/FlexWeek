"""The model rule for a finished flexible block's day. Finished work in solve() is tested in engine/engine/tests/test_completed.rs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models import TimeBlock


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "locked"},
        {"completed": False},
        {"start": None},
        {"completed_day": 3},
    ],
)
def test_completed_day_requires_a_matching_finished_flexible_placement(
    changes: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "id": "done",
        "title": "Done",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0, 1, 2],
        "start": "09:00",
        "completed": True,
        "completed_day": 1,
    }
    values.update(changes)
    with pytest.raises(ValidationError, match="completed_day"):
        TimeBlock.model_validate(values)
