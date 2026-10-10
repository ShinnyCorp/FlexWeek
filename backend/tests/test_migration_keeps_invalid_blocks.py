"""Startup migration must not store homework the app's own schema refuses (audit finding 3).

A week may hold a flexible block of any minute length, but homework is planned in quarter hours.
The 17-minute block from the audit is saved, the store is started again, and the account must
still export with the block as the student typed it.
"""

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.storage import initialize

HEADERS = {"X-FlexWeek-Request": "1"}
PASSWORD = "temporary-test-password"
TODAY = date.today()
WEEK = (TODAY - timedelta(days=TODAY.weekday())).isoformat()
READING = {"id": "b17", "title": "Reading", "kind": "flexible", "duration_min": 17, "days": [0]}


def test_a_17_minute_block_survives_a_restart_and_the_account_still_exports(tmp_path: Path) -> None:
    path = tmp_path / "accounts.db"
    with TestClient(create_app(path, "http://testserver"), headers=HEADERS) as client:
        assert (
            client.post("/api/auth/register", json={"username": "student", "password": PASSWORD}).status_code
            == 201
        )
        saved = client.put("/api/week", json={"week_start": WEEK, "blocks": [READING], "revision": 0})
        assert saved.status_code == 200
    initialize(path)
    with TestClient(create_app(path, "http://testserver"), headers=HEADERS) as client:
        assert (
            client.post("/api/auth/login", json={"username": "student", "password": PASSWORD}).status_code
            == 200
        )
        exported = client.post("/api/account-export", json={"password": PASSWORD})
        assert exported.status_code == 200, exported.text
        snapshot = exported.json()
        assert snapshot["assignments"] == []
        [week] = [week for week in snapshot["weeks"] if week["week_start"] == WEEK]
        assert as_typed(week["blocks"]) == [READING]
        shown = client.get("/api/week", params={"week_start": WEEK}).json()
        assert as_typed(shown["blocks"]) == [READING]


def as_typed(blocks: list[dict]) -> list[dict]:
    """The fields the student typed, and no link to homework (the schema's defaults are left out)."""
    assert all(block.get("assignment_id") is None for block in blocks)
    return [{key: block[key] for key in READING} for block in blocks]
