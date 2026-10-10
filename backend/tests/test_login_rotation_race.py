"""A login checked against the old password must not outlive a password rotation (audit finding 1).

The interleaving is forced, not timed: the password check of the login is patched so that, after it
has accepted the old password, the account is recovered (or its password changed) before the login
goes on to create its session.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app as app_module
from backend.app import create_app
from backend.storage import connect

HEADERS = {"X-FlexWeek-Request": "1"}
OLD = "temporary-test-password"
NEW = "a-brand-new-test-password"


def rotate_during_check(monkeypatch: pytest.MonkeyPatch, rotate: Callable[[], None]) -> list[bool]:
    original = app_module.password_matches
    seen: list[bool] = []

    def check_then_rotate(password: str, encoded: str) -> bool:
        matched = original(password, encoded)
        if not seen:
            seen.append(matched)
            rotate()
        return matched

    monkeypatch.setattr(app_module, "password_matches", check_then_rotate)
    return seen


def session_count(path: Path) -> int:
    with connect(path) as db:
        return db.execute("SELECT count(*) FROM sessions").fetchone()[0]


def test_login_with_the_old_password_gets_no_session_after_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "accounts.db"
    with (
        TestClient(create_app(path, "http://testserver"), headers=HEADERS) as owner,
        TestClient(create_app(path, "http://testserver"), headers=HEADERS) as stale,
    ):
        codes = owner.post("/api/auth/register", json={"username": "student", "password": OLD}).json()[
            "recovery_codes"
        ]
        owner.post("/api/auth/logout")

        def recover() -> None:
            result = owner.post(
                "/api/auth/recover", json={"username": "student", "code": codes[0], "password": NEW}
            )
            assert result.status_code == 200

        seen = rotate_during_check(monkeypatch, recover)
        result = stale.post("/api/auth/login", json={"username": "student", "password": OLD})
        assert seen == [True], "the login's check must have accepted the old password"
        assert result.status_code == 401
        assert stale.get("/api/auth/me").status_code == 401
        # Only the session recovery itself opened is left.
        assert session_count(path) == 1
        assert owner.get("/api/auth/me").status_code == 200


def test_login_with_the_old_password_gets_no_session_after_a_password_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "accounts.db"
    with (
        TestClient(create_app(path, "http://testserver"), headers=HEADERS) as owner,
        TestClient(create_app(path, "http://testserver"), headers=HEADERS) as stale,
    ):
        assert (
            owner.post("/api/auth/register", json={"username": "student", "password": OLD}).status_code == 201
        )

        def change() -> None:
            # The change route checks the current password through the same patched function;
            # by then the flag is set, so it runs the real check only.
            result = owner.post("/api/auth/password", json={"current_password": OLD, "new_password": NEW})
            assert result.status_code == 200

        seen = rotate_during_check(monkeypatch, change)
        result = stale.post("/api/auth/login", json={"username": "student", "password": OLD})
        assert seen == [True]
        assert result.status_code == 401
        assert stale.get("/api/auth/me").status_code == 401
        assert session_count(path) == 1
        assert owner.get("/api/auth/me").status_code == 200


def test_login_with_an_unchanged_password_still_signs_in(tmp_path: Path) -> None:
    path = tmp_path / "accounts.db"
    with TestClient(create_app(path, "http://testserver"), headers=HEADERS) as client:
        assert (
            client.post("/api/auth/register", json={"username": "student", "password": OLD}).status_code
            == 201
        )
        client.post("/api/auth/logout")
        assert (
            client.post("/api/auth/login", json={"username": "student", "password": OLD}).status_code == 200
        )
        assert client.get("/api/auth/me").json()["username"] == "student"
