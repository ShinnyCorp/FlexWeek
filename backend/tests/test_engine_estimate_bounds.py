"""Estimates beyond signed 64 bits are an accepted port difference, not stored app data."""

from __future__ import annotations

from backend.app import assignment_view
from backend.tests import test_engine_parity as reference


def test_assignment_view_reports_the_accepted_signed_64_bit_limit() -> None:
    body = {"estimate_min": 2**63, "focus_minutes": 0}
    assert reference.ref_assignment_view(body, 1, 0)["unplanned_min"] == 2**63
    seen: type[Exception] | None = None
    try:
        assignment_view(body, 1, 0)
    except Exception as error:
        seen = type(error)
    assert seen is OverflowError
