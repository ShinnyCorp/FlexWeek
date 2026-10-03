//! Rust twin of `desktop/tests/test_focus.py`: focus timer math.

use flexweek_engine::desk::focus::{
    begin_state, break_phase, credit_target, focus_now, format_countdown, more_time_choices,
    now_and_next, now_next_line, pause_state, persist_payload, phase_duration_ms, remaining_ms,
    restore_state, set_phase,
};
use serde_json::{Value, json};

#[test]
fn test_phase_duration_uses_account_timer_lengths() {
    let prefs = json!({"timer_work_min": 15, "timer_break_min": 15, "timer_long_break_min": 30});
    let ms = |phase: &str| phase_duration_ms(&json!(phase), &prefs).expect("a duration");
    assert_eq!(ms("work"), 15 * 60_000);
    assert_eq!(ms("break"), 15 * 60_000);
    assert_eq!(ms("long_break"), 30 * 60_000);
}

#[test]
fn test_countdown_ceils_partial_seconds() {
    assert_eq!(format_countdown(0), "00:00");
    assert_eq!(format_countdown(1), "00:01");
    assert_eq!(format_countdown(61_000), "01:01");
}

#[test]
fn test_pause_freezes_remaining_wall_clock() {
    let state = begin_state(
        &json!({"title": "Essay", "blockId": "sess", "assignmentId": "essay", "weekStart": "2026-09-14"}),
        &json!({"timer_work_min": 30}),
        1_000_000,
    )
    .expect("a state");
    let paused = pause_state(&state, 1_000_000 + 10_000).expect("a state");
    assert_eq!(paused["running"], json!(false));
    assert_eq!(paused["remainingMs"], json!(30 * 60_000 - 10_000));
    let resumed = pause_state(&paused, 2_000_000).expect("a state");
    assert_eq!(resumed["running"], json!(true));
    assert_eq!(
        resumed["endsAt"],
        json!(2_000_000 + paused["remainingMs"].as_i64().expect("remainingMs"))
    );
}

#[test]
fn test_quick_focus_credits_nothing() {
    let state = json!({"blockId": null, "assignmentId": null});
    assert_eq!(
        credit_target(&state, &json!({"id": "essay"}), &json!({"id": "sess"}), 30)
            .expect("a verdict"),
        None
    );
}

#[test]
fn test_homework_credit_increments_once_on_the_assignment() {
    let updated = credit_target(
        &json!({"blockId": "sess", "assignmentId": "essay"}),
        &json!({"id": "essay", "focus_minutes": 0, "focus_sessions": 0}),
        &json!({"id": "sess", "focus_minutes": 0}),
        30,
    )
    .expect("a verdict")
    .expect("a credited item");
    assert_eq!(updated["id"], "essay");
    assert_eq!(updated["focus_sessions"], 1);
    assert_eq!(updated["focus_minutes"], 30);
}

#[test]
fn test_more_time_stays_on_the_fifteen_minute_grid_under_the_cap() {
    assert_eq!(more_time_choices(7140), Vec::<i64>::new());
    assert!(more_time_choices(60).contains(&15));
    assert!(!more_time_choices(7000).contains(&240));
}

#[test]
fn test_restore_drops_completed_homework_and_keeps_a_running_timer() {
    let begun = begin_state(
        &json!({
            "title": "Essay",
            "blockId": "sess",
            "assignmentId": "essay",
            "weekStart": "2026-09-14",
            "day": 0,
            "start": "16:00",
        }),
        &json!({"timer_work_min": 30}),
        1_000_000,
    )
    .expect("a state");
    let saved = persist_payload(&begun)
        .expect("a payload")
        .expect("a payload");
    let blocks = json!([{"id": "sess", "title": "Essay"}]);
    let open = json!({"essay": {"id": "essay", "title": "Essay", "completed": false}});
    let restored = restore_state(&saved, &open, &blocks, 1_000_000)
        .expect("a verdict")
        .expect("restored");
    assert_eq!(restored["running"], json!(true));
    let done = json!({"essay": {"id": "essay", "title": "Essay", "completed": true}});
    assert_eq!(
        restore_state(&saved, &done, &blocks, 1_000_000).expect("a verdict"),
        None
    );
}

#[test]
fn test_expired_work_phase_is_flagged_so_credit_can_run() {
    let saved = json!({
        "assignmentId": null,
        "sessionId": "sess",
        "weekStart": "2026-09-14",
        "phase": "work",
        "cycles": 0,
        "endsAt": 50,
        "remainingMs": null,
    });
    let restored = restore_state(
        &saved,
        &json!({}),
        &json!([{"id": "sess", "title": "Soccer"}]),
        100,
    )
    .expect("a verdict")
    .expect("restored");
    assert_eq!(restored["expired"], json!(true));
    assert_eq!(restored["running"], json!(false));
}

#[test]
fn test_long_break_follows_the_configured_cadence() {
    let prefs = json!({"timer_long_break_every": 4});
    assert_eq!(break_phase(1, &prefs).expect("a phase"), "break");
    assert_eq!(break_phase(4, &prefs).expect("a phase"), "long_break");
}

#[test]
fn test_now_next_line_names_the_current_and_upcoming_block() {
    let blocks = json!([
        {"title": "Soccer", "start": "16:00", "duration_min": 60, "days": [0], "completed": false},
        {"title": "Dinner", "start": "18:00", "duration_min": 30, "days": [0], "completed": false},
    ]);
    let result = now_and_next(&blocks, &json!(0), 16 * 60 + 10).expect("a result");
    assert_eq!(result["current"]["title"], "Soccer");
    assert_eq!(result["next"]["title"], "Dinner");
    let line = now_next_line(&result, 16 * 60 + 10).expect("a line");
    assert!(line.contains("Now: Soccer"), "{line}");
    assert!(line.contains("Next: Dinner at 18:00"), "{line}");
}

#[test]
fn test_remaining_ms_uses_ends_at_while_running() {
    let state = json!({"running": true, "endsAt": 5_000, "remainingMs": 99});
    assert_eq!(remaining_ms(&state, 4_000).expect("a time"), 1_000);
    assert_eq!(
        remaining_ms(&json!({"running": false, "remainingMs": 12}), 0).expect("a time"),
        12
    );
}

#[test]
fn test_set_phase_restarts_the_wall_clock() {
    let state = begin_state(
        &json!({"title": "Quick focus", "weekStart": "2026-09-14"}),
        &json!({"timer_work_min": 15}),
        0,
    )
    .expect("a state");
    let nxt = set_phase(
        &state,
        &json!("break"),
        &json!({"timer_break_min": 15}),
        9_000,
    )
    .expect("a state");
    assert_eq!(nxt["phase"], "break");
    assert_eq!(nxt["endsAt"], json!(9_000 + 15 * 60_000));
}

#[test]
fn test_focus_now_says_what_the_timer_is_doing() {
    let now = |state: Value| focus_now(&state).expect("a word");
    assert_eq!(now(Value::Null), "");
    assert_eq!(
        now(json!({"phase": "ended", "running": false})),
        "",
        "a finished session is not running"
    );
    assert_eq!(now(json!({"phase": "work", "running": true})), "focusing");
    assert_eq!(now(json!({"phase": "work", "running": false})), "paused");
    assert_eq!(now(json!({"phase": "break", "running": true})), "break");
    assert_eq!(
        now(json!({"phase": "long_break", "running": false})),
        "break"
    );
}
