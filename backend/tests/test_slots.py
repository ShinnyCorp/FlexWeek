import pytest
from pydantic import ValidationError

from backend.models import TimeBlock


def test_a_blocks_length_is_any_positive_minute() -> None:
    assert TimeBlock(id="short", title="Short", kind="locked", duration_min=7, days=[0], start="17:37")
    with pytest.raises(ValidationError):
        TimeBlock(id="bad", title="Bad", kind="flexible", duration_min=0, days=[0])


def test_days_must_be_in_week() -> None:
    with pytest.raises(ValidationError):
        TimeBlock(
            id="bad",
            title="Bad",
            kind="locked",
            duration_min=15,
            days=[7],
            start="08:00",
        )
