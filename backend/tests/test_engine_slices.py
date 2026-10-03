"""Restore-point canonical text and the saved-look and placement rules, on fixed expectations."""

from __future__ import annotations

import json

from backend import restore as engine_restore


def test_canonical_sorts_keys_like_python_json():
    value = {"b": 1, "a": {"d": True, "c": None}}
    assert engine_restore.canonical(value) == json.dumps(value, sort_keys=True, separators=(",", ":"))


def test_saved_look_names_and_a_clash_match_the_rules():
    import flexweek_engine  # type: ignore[import-untyped]

    assert flexweek_engine.free_name(json.dumps([{"name": "My look", "base": "light"}]), "My look") == "My look 2"
    assert json.loads(flexweek_engine.delete_look(json.dumps([{"name": "My look", "base": "light"}]), "My look")) == []

    blocks = [
        {
            "id": "school",
            "kind": "locked",
            "title": "School",
            "start": "09:00",
            "duration_min": 60,
            "days": [0],
        },
        {
            "id": "hw",
            "kind": "flexible",
            "title": "Essay",
            "start": "09:30",
            "duration_min": 30,
            "days": [0],
            "assignment_id": "a",
        },
    ]
    assignments = {"a": {"id": "a", "due": "2026-09-07T18:00", "title": "Essay"}}
    kept, lost = flexweek_engine.settle_placements(
        json.dumps(blocks),
        json.dumps(assignments),
        "2026-09-07",
        [],
    )
    kept = json.loads(kept)
    lost = json.loads(lost)
    assert kept[1]["id"] == "hw"
    assert "start" not in kept[1]
    assert "Essay no longer fits" in lost[0]["message"]
    assert "School is there now" in lost[0]["message"]
