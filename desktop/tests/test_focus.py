"""Focus timer math. Expected values match frontend/focus.js."""

from __future__ import annotations

from desktop.native.focus import (
    begin_state,
    break_phase,
    credit_target,
    focus_now,
    format_countdown,
    more_time_choices,
    now_and_next,
    now_next_line,
    pause_state,
    persist_payload,
    phase_duration_ms,
    remaining_ms,
    restore_state,
    set_phase,
)


def test_phase_duration_uses_account_timer_lengths() -> None:
    prefs = {"timer_work_min": 15, "timer_break_min": 15, "timer_long_break_min": 30}
    assert phase_duration_ms("work", prefs) == 15 * 60_000
    assert phase_duration_ms("break", prefs) == 15 * 60_000
    assert phase_duration_ms("long_break", prefs) == 30 * 60_000


def test_countdown_ceils_partial_seconds() -> None:
    assert format_countdown(0) == "00:00"
    assert format_countdown(1) == "00:01"
    assert format_countdown(61_000) == "01:01"


def test_pause_freezes_remaining_wall_clock() -> None:
    state = begin_state(
        {"title": "Essay", "blockId": "sess", "assignmentId": "essay", "weekStart": "2026-09-14"},
        {"timer_work_min": 30},
        now_ms=1_000_000,
    )
    paused = pause_state(state, 1_000_000 + 10_000)
    assert paused["running"] is False
    assert paused["remainingMs"] == 30 * 60_000 - 10_000
    resumed = pause_state(paused, 2_000_000)
    assert resumed["running"] is True
    assert resumed["endsAt"] == 2_000_000 + paused["remainingMs"]


def test_quick_focus_credits_nothing() -> None:
    state = {"blockId": None, "assignmentId": None}
    assert credit_target(state, {"id": "essay"}, {"id": "sess"}, 30) is None


def test_homework_credit_increments_once_on_the_assignment() -> None:
    updated = credit_target(
        {"blockId": "sess", "assignmentId": "essay"},
        {"id": "essay", "focus_minutes": 0, "focus_sessions": 0},
        {"id": "sess", "focus_minutes": 0},
        30,
    )
    assert updated is not None
    assert updated["id"] == "essay"
    assert updated["focus_sessions"] == 1
    assert updated["focus_minutes"] == 30


def test_more_time_stays_on_the_fifteen_minute_grid_under_the_cap() -> None:
    assert more_time_choices(7140) == []
    assert 15 in more_time_choices(60)
    assert 240 not in more_time_choices(7000)


def test_restore_drops_completed_homework_and_keeps_a_running_timer() -> None:
    saved = persist_payload(
        begin_state(
            {
                "title": "Essay",
                "blockId": "sess",
                "assignmentId": "essay",
                "weekStart": "2026-09-14",
                "day": 0,
                "start": "16:00",
            },
            {"timer_work_min": 30},
            1_000_000,
        )
    )
    restored = restore_state(
        saved,
        assignments={"essay": {"id": "essay", "title": "Essay", "completed": False}},
        blocks=[{"id": "sess", "title": "Essay"}],
        now_ms=1_000_000,
    )
    assert restored is not None
    assert restored["running"] is True
    assert (
        restore_state(
            saved,
            assignments={"essay": {"id": "essay", "title": "Essay", "completed": True}},
            blocks=[{"id": "sess", "title": "Essay"}],
            now_ms=1_000_000,
        )
        is None
    )


def test_expired_work_phase_is_flagged_so_credit_can_run() -> None:
    saved = {
        "assignmentId": None,
        "sessionId": "sess",
        "weekStart": "2026-09-14",
        "phase": "work",
        "cycles": 0,
        "endsAt": 50,
        "remainingMs": None,
    }
    restored = restore_state(saved, assignments={}, blocks=[{"id": "sess", "title": "Soccer"}], now_ms=100)
    assert restored is not None
    assert restored["expired"] is True
    assert restored["running"] is False


def test_long_break_follows_the_configured_cadence() -> None:
    prefs = {"timer_long_break_every": 4}
    assert break_phase(1, prefs) == "break"
    assert break_phase(4, prefs) == "long_break"


def test_now_next_line_names_the_current_and_upcoming_block() -> None:
    blocks = [
        {"title": "Soccer", "start": "16:00", "duration_min": 60, "days": [0], "completed": False},
        {"title": "Dinner", "start": "18:00", "duration_min": 30, "days": [0], "completed": False},
    ]
    result = now_and_next(blocks, 0, 16 * 60 + 10)
    assert result["current"]["title"] == "Soccer"
    assert result["next"]["title"] == "Dinner"
    line = now_next_line(result, 16 * 60 + 10)
    assert "Now: Soccer" in line
    assert "Next: Dinner at 18:00" in line


def test_remaining_ms_uses_ends_at_while_running() -> None:
    state = {"running": True, "endsAt": 5_000, "remainingMs": 99}
    assert remaining_ms(state, 4_000) == 1_000
    assert remaining_ms({"running": False, "remainingMs": 12}, 0) == 12


def test_set_phase_restarts_the_wall_clock() -> None:
    state = begin_state({"title": "Quick focus", "weekStart": "2026-09-14"}, {"timer_work_min": 15}, 0)
    nxt = set_phase(state, "break", {"timer_break_min": 15}, 9_000)
    assert nxt["phase"] == "break"
    assert nxt["endsAt"] == 9_000 + 15 * 60_000


def test_focus_now_says_what_the_timer_is_doing() -> None:
    assert focus_now(None) == ""
    assert focus_now({"phase": "ended", "running": False}) == "", "a finished session is not running"
    assert focus_now({"phase": "work", "running": True}) == "focusing"
    assert focus_now({"phase": "work", "running": False}) == "paused"
    assert focus_now({"phase": "break", "running": True}) == "break"
    assert focus_now({"phase": "long_break", "running": False}) == "break"
