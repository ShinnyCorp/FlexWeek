"""Audit finding 10: a file that is not a FlexWeek export is refused in words, whatever is in its header."""

from __future__ import annotations

import importlib.util
import json

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from desktop.native.files import parse_import_payload


@pytest.mark.parametrize("format_", [[], {}, 5, None, True])
def test_a_header_whose_format_is_not_text_is_refused_with_a_complaint(format_: object) -> None:
    raw = json.dumps({"format": format_, "version": 2, "blocks": [], "assignments": []})
    result = parse_import_payload(raw)
    assert result["error"] == "Unrecognized export format."


def test_a_file_nested_too_deep_to_read_is_refused_not_raised() -> None:
    depth = 100_000
    result = parse_import_payload("[" * depth + "]" * depth)
    assert isinstance(result["error"], str) and result["error"]
