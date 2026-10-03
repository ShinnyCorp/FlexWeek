"""Stage 4 notes, links, checklist and study-window subject rules. Occupancy, running late, spread and cluster copy are tested in engine/engine/tests/test_stage4_availability.rs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models import Assignment, StudyWindow


def test_assignment_notes_links_and_checklist_round_trip_and_omit_empties() -> None:
    empty = Assignment.model_validate(
        {
            "id": "hw-essay",
            "title": "Essay",
            "due": "2026-09-15T23:59",
            "estimate_min": 120,
            "revision": 0,
        }
    )
    dumped = empty.model_dump()
    assert "notes" not in dumped
    assert "links" not in dumped
    assert "checklist" not in dumped
    filled = Assignment.model_validate(
        {
            "id": "hw-essay",
            "title": "Essay",
            "due": "2026-09-15T23:59",
            "estimate_min": 120,
            "revision": 1,
            "notes": "Use the primary sources from week 3.",
            "links": [{"label": "Prompt", "url": "https://example.edu/prompt"}],
            "checklist": [{"id": "outline", "text": "Outline", "done": False}],
        }
    )
    assert filled.model_dump()["notes"] == "Use the primary sources from week 3."
    assert filled.model_dump()["links"] == [{"label": "Prompt", "url": "https://example.edu/prompt"}]
    assert filled.model_dump()["checklist"] == [{"id": "outline", "text": "Outline", "done": False}]


def test_assignment_rejects_javascript_urls_and_duplicate_checklist_ids() -> None:
    base = {
        "id": "hw-essay",
        "title": "Essay",
        "due": "2026-09-15T23:59",
        "estimate_min": 120,
        "revision": 0,
    }
    with pytest.raises(ValidationError):
        Assignment.model_validate({**base, "links": [{"label": "Bad", "url": "javascript:alert(1)"}]})
    with pytest.raises(ValidationError):
        Assignment.model_validate(
            {
                **base,
                "checklist": [
                    {"id": "one", "text": "First"},
                    {"id": "one", "text": "Again"},
                ],
            }
        )


@pytest.mark.parametrize("subject", ["   ", "x" * 41])
def test_a_subject_must_be_a_real_name(subject: str) -> None:
    with pytest.raises(ValueError):
        StudyWindow(days=[0], start="15:30", duration_min=60, subject=subject)
