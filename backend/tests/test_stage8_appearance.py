"""Appearance preference fields: pack, accent, chips and motion."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import create_app

PASSWORD = "a-long-test-password"
WRITE = {"X-FlexWeek-Request": "1", "Origin": "http://testserver"}
APPEARANCE_KEYS = ("theme_pack", "accent", "accent_chips", "motion")


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def app(database: Path) -> FastAPI:
    return create_app(database=database, origin="http://testserver")


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def alice(client: TestClient) -> TestClient:
    response = client.post(
        "/api/auth/register", json={"username": "alice", "password": PASSWORD}, headers=WRITE
    )
    assert response.status_code == 201, response.text
    return client


def defaults() -> dict:
    return {
        "theme": "system",
        "reminders_enabled": True,
        "reminder_lead_min": 5,
        "reminder_sound": True,
        "reminder_dnd_override": False,
        "timer_work_min": 30,
        "timer_break_min": 15,
        "timer_long_break_min": 30,
        "timer_long_break_every": 4,
        "auto_split_pomodoro": False,
        "default_spotify_url": None,
        "alarms": [],
    }


def test_fresh_account_omits_appearance_fields(alice: TestClient) -> None:
    body = alice.get("/api/preferences").json()
    assert body == defaults()
    for key in APPEARANCE_KEYS:
        assert key not in body


def test_old_client_round_trip_still_omits_appearance_fields(alice: TestClient) -> None:
    saved = alice.put("/api/preferences", json=defaults(), headers=WRITE)
    assert saved.status_code == 200, saved.text
    assert saved.json() == defaults()
    assert alice.get("/api/preferences").json() == defaults()
    for key in APPEARANCE_KEYS:
        assert key not in saved.json()


def test_unknown_preference_key_is_rejected(alice: TestClient) -> None:
    rejected = alice.put("/api/preferences", json={**defaults(), "linen": "graphite"}, headers=WRITE)
    assert rejected.status_code == 422


def test_accent_outside_the_set_is_rejected(alice: TestClient) -> None:
    rejected = alice.put("/api/preferences", json={**defaults(), "accent": "indigo"}, headers=WRITE)
    assert rejected.status_code == 422


def test_appearance_fields_round_trip(alice: TestClient) -> None:
    payload = {
        **defaults(),
        "theme": "nocturne",
        "theme_pack": "dark-frost",
        "accent": "gold",
        "accent_chips": True,
        "motion": "extra",
    }
    saved = alice.put("/api/preferences", json=payload, headers=WRITE)
    assert saved.status_code == 200, saved.text
    assert saved.json() == payload
    assert alice.get("/api/preferences").json() == payload
    restored = alice.put("/api/preferences", json=defaults(), headers=WRITE)
    assert restored.status_code == 200, restored.text
    assert restored.json() == defaults()
    for key in APPEARANCE_KEYS:
        assert key not in restored.json()


def test_explicit_normal_motion_stays_on_the_wire(alice: TestClient) -> None:
    payload = {**defaults(), "motion": "normal"}
    saved = alice.put("/api/preferences", json=payload, headers=WRITE)
    assert saved.status_code == 200, saved.text
    assert saved.json()["motion"] == "normal"
    loaded = alice.get("/api/preferences").json()
    assert loaded["motion"] == "normal"


def test_a_set_pack_keeps_theme_on_its_axis(alice: TestClient) -> None:
    rejected = alice.put(
        "/api/preferences",
        json={**defaults(), "theme": "slate", "theme_pack": "dark-frost"},
        headers=WRITE,
    )
    assert rejected.status_code == 422
    saved = alice.put(
        "/api/preferences",
        json={**defaults(), "theme": "nocturne", "theme_pack": "dark-frost"},
        headers=WRITE,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["theme_pack"] == "dark-frost"
    assert saved.json()["theme"] == "nocturne"
    light = alice.put(
        "/api/preferences",
        json={**defaults(), "theme": "slate", "theme_pack": "light-frost"},
        headers=WRITE,
    )
    assert light.status_code == 200, light.text
    assert light.json()["theme_pack"] == "light-frost"
    assert (
        alice.put(
            "/api/preferences",
            json={**defaults(), "theme": "nocturne", "theme_pack": "light-frost"},
            headers=WRITE,
        ).status_code
        == 422
    )


SETUP_KEYS = ("alarm_tone", "planning_style", "drag_step_min", "setup")


def test_a_fresh_account_omits_the_setup_preferences(alice: TestClient) -> None:
    """Default values stay off the wire, so a 0.14 client reads an account exactly as before."""
    body = alice.get("/api/preferences").json()
    for key in SETUP_KEYS:
        assert key not in body


def test_the_alarm_tone_planning_style_drag_step_and_setup_progress_round_trip(alice: TestClient) -> None:
    payload = {
        **defaults(),
        "alarm_tone": "glass",
        "planning_style": "manual",
        "drag_step_min": 15,
        "setup": {"version": 1, "step": 3, "finished_at": None},
    }
    saved = alice.put("/api/preferences", json=payload, headers=WRITE)
    assert saved.status_code == 200, saved.text
    assert alice.get("/api/preferences").json() == payload
    finished = {**payload, "setup": {"version": 1, "step": 6, "finished_at": "2026-09-22T16:30"}}
    assert alice.put("/api/preferences", json=finished, headers=WRITE).status_code == 200
    assert alice.get("/api/preferences").json()["setup"]["finished_at"] == "2026-09-22T16:30"


@pytest.mark.parametrize(
    "change",
    [
        {"alarm_tone": "siren"},
        {"planning_style": "sometimes"},
        {"drag_step_min": 10},
        {"drag_step_min": 1},
        {"setup": {"version": 0, "step": 0}},
        {"setup": {"version": 1, "step": 99}},
        {"setup": {"version": 1, "step": 0, "finished_at": "yesterday"}},
        {"setup": {"version": 1, "step": 0, "extra": True}},
    ],
)
def test_a_setup_preference_outside_its_values_is_refused(alice: TestClient, change: dict) -> None:
    refused = alice.put("/api/preferences", json={**defaults(), **change}, headers=WRITE)
    assert refused.status_code == 422
    assert "siren" not in refused.text and "sometimes" not in refused.text


def test_the_clock_is_24_hour_unless_chosen_and_the_default_stays_off_the_wire(alice: TestClient) -> None:
    """A 0.15 client reads an account that never chose a clock exactly as before."""
    assert "clock_24h" not in alice.get("/api/preferences").json()
    twelve = {**defaults(), "clock_24h": False}
    saved = alice.put("/api/preferences", json=twelve, headers=WRITE)
    assert saved.status_code == 200, saved.text
    assert alice.get("/api/preferences").json() == twelve
    back = alice.put("/api/preferences", json={**defaults(), "clock_24h": True}, headers=WRITE)
    assert back.status_code == 200, back.text
    assert "clock_24h" not in alice.get("/api/preferences").json()


def test_a_clock_that_is_not_true_or_false_is_refused(alice: TestClient) -> None:
    refused = alice.put("/api/preferences", json={**defaults(), "clock_24h": "sometimes"}, headers=WRITE)
    assert refused.status_code == 422
