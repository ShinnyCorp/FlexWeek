"""Restore-point snapshots. No HTTP, no database."""

from __future__ import annotations

import hashlib
import json


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def state_token(snapshot: dict) -> str:
    return hashlib.sha256(canonical(snapshot).encode()).hexdigest()


def _title(row: dict) -> str:
    body = row["body"]
    if isinstance(body, str):
        body = json.loads(body)
    return str(body["title"])


def _ref(row: dict) -> dict[str, str]:
    return {"id": row["id"], "title": _title(row)}


def diff_snapshots(current: dict, stored: dict) -> dict:
    current_weeks = {row["week_start"]: row["blocks"] for row in current["weeks"]}
    stored_weeks = {row["week_start"]: row["blocks"] for row in stored["weeks"]}
    current_assignments = {row["id"]: row for row in current["assignments"]}
    stored_assignments = {row["id"]: row for row in stored["assignments"]}
    weeks_added = sorted(start for start in stored_weeks if start not in current_weeks)
    weeks_removed = sorted(start for start in current_weeks if start not in stored_weeks)
    weeks_changed = sorted(
        start
        for start in stored_weeks
        if start in current_weeks and canonical(stored_weeks[start]) != canonical(current_weeks[start])
    )
    assignments_added = [
        _ref(stored_assignments[key]) for key in sorted(stored_assignments) if key not in current_assignments
    ]
    assignments_removed = [
        _ref(current_assignments[key]) for key in sorted(current_assignments) if key not in stored_assignments
    ]
    assignments_changed = [
        _ref(stored_assignments[key])
        for key in sorted(stored_assignments)
        if key in current_assignments
        and canonical(stored_assignments[key]["body"]) != canonical(current_assignments[key]["body"])
    ]
    return {
        "weeks": {"added": weeks_added, "changed": weeks_changed, "removed": weeks_removed},
        "assignments": {
            "added": assignments_added,
            "changed": assignments_changed,
            "removed": assignments_removed,
        },
    }


def _routine_core(row: dict) -> dict:
    return {"id": row["id"], "name": row["name"], "blocks": row["blocks"], "revision": row["revision"]}


def diff_transfer(current: dict, incoming: dict) -> dict:
    changes = diff_snapshots(current, incoming)
    current_routines = {row["id"]: row for row in current["routines"]}
    incoming_routines = {row["id"]: row for row in incoming["routines"]}
    changes["routines"] = {
        "added": [
            {"id": key, "name": incoming_routines[key]["name"]}
            for key in sorted(incoming_routines)
            if key not in current_routines
        ],
        "changed": [
            {"id": key, "name": incoming_routines[key]["name"]}
            for key in sorted(incoming_routines)
            if key in current_routines
            and canonical(_routine_core(current_routines[key]))
            != canonical(_routine_core(incoming_routines[key]))
        ],
        "removed": [
            {"id": key, "name": current_routines[key]["name"]}
            for key in sorted(current_routines)
            if key not in incoming_routines
        ],
    }
    changes["preferences_changed"] = canonical(current["preferences"]) != canonical(incoming["preferences"])
    return changes
