"""The browser cookie and stored session use the engine's single lifetime."""

from __future__ import annotations

from http.cookies import SimpleCookie
from pathlib import Path

import flexweek_engine  # type: ignore[import-untyped]
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.storage import connect, digest


@pytest.mark.parametrize("endpoint", ["register", "login"])
def test_cookie_age_matches_the_stored_session_lifetime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    opened_at = 1_800_000_000
    monkeypatch.setattr("backend.storage.time.time", lambda: opened_at)
    path = tmp_path / "sessions.db"
    account = {"username": "student", "password": "a-long-test-password"}
    headers = {"X-FlexWeek-Request": "1", "Origin": "http://testserver"}
    with TestClient(create_app(database=path, origin="http://testserver")) as client:
        response = client.post("/api/auth/register", json=account, headers=headers)
        assert response.status_code == 201, response.text
        if endpoint == "login":
            response = client.post("/api/auth/login", json=account, headers=headers)
            assert response.status_code == 200, response.text
        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        token = cookie["flexweek_session"].value
        with connect(path) as db:
            expires = db.execute("SELECT expires FROM sessions WHERE token_hash = ?", (digest(token),)).fetchone()[0]
        lifetime = expires - opened_at
        assert getattr(flexweek_engine, "SESSION_SECONDS", None) == lifetime
        assert int(cookie["flexweek_session"]["max-age"]) == lifetime
