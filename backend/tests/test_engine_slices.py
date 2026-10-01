"""The engine and the original Python agree on snapshots, recovery codes, and plan sentences."""

from __future__ import annotations

import json

from backend import explain as engine_explain
from backend import recovery as engine_recovery
from backend import restore as engine_restore
from backend import transfer as engine_transfer
from backend.tests.engine_ref import explain as py_explain
from backend.tests.engine_ref import recovery as py_recovery
from backend.tests.engine_ref import restore as py_restore
from backend.tests.engine_ref import transfer as py_transfer

SNAPSHOT = {
    "weeks": [{"week_start": "2026-09-07", "blocks": [{"id": "a", "title": "Lab"}]}],
    "assignments": [{"id": "hw", "body": {"title": "Essay"}}],
    "routines": [],
    "preferences": {"theme": "system"},
}
OTHER = {
    "weeks": [{"week_start": "2026-09-14", "blocks": []}],
    "assignments": [{"id": "hw", "body": {"title": "Essay draft"}}],
    "routines": [{"id": "r", "name": "Morning", "blocks": [], "revision": 1}],
    "preferences": {"theme": "slate"},
}


def test_canonical_and_token_match():
    assert engine_restore.canonical(SNAPSHOT) == py_restore.canonical(SNAPSHOT)
    assert engine_restore.state_token(SNAPSHOT) == py_restore.state_token(SNAPSHOT)


def test_diffs_match():
    assert engine_restore.diff_snapshots(SNAPSHOT, OTHER) == py_restore.diff_snapshots(SNAPSHOT, OTHER)
    assert engine_restore.diff_transfer(SNAPSHOT, OTHER) == py_restore.diff_transfer(SNAPSHOT, OTHER)


def test_transfer_size_matches():
    assert engine_transfer.transfer_apply_bytes(SNAPSHOT) == py_transfer.transfer_apply_bytes(SNAPSHOT)
    assert engine_transfer.transfer_fits(SNAPSHOT) is py_transfer.transfer_fits(SNAPSHOT)
    huge = {"blob": "x" * 300_000}
    assert engine_transfer.transfer_fits(huge) is py_transfer.transfer_fits(huge)


def test_recovery_format_and_hash_match():
    raw = "0011223344556677"
    assert engine_recovery.format_recovery_code(raw) == py_recovery.format_recovery_code(raw)
    code = engine_recovery.format_recovery_code(raw)
    assert engine_recovery.hash_recovery_code(code) == py_recovery.hash_recovery_code("00 11-2233 4455.6677")
    assert engine_recovery.recovery_code_matches(code, py_recovery.hash_recovery_code(code))


def test_sentences_match():
    for code in py_explain.REASON_COPY:
        assert engine_explain.sentence(code) == py_explain.sentence(code)
        assert engine_explain.slack_sentence(29, "danger") == py_explain.slack_sentence(29, "danger")
        assert engine_explain.slack_sentence(0, "ok") == py_explain.slack_sentence(0, "ok")


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

