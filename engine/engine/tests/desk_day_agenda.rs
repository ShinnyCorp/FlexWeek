//! Rust twin of the two Qt-free tests in `desktop/tests/test_day_agenda.py`.
//!
//! The rest of that file fills a `DayAgenda` widget or a `MonthGrid` and stays Python.

use flexweek_engine::desk::grid::agenda_for;
use serde_json::{Value, json};

fn ids(rows: &Value) -> Vec<&str> {
    rows.as_array()
        .expect("rows")
        .iter()
        .map(|row| row["block"]["id"].as_str().expect("id"))
        .collect()
}

#[test]
fn test_a_block_that_is_not_on_this_day_is_left_out_rather_than_breaking_the_day() {
    // placement_on says "not on this day" with a sentinel compared by identity. Built fresh inside
    // each function it was a different object every call, so the check never matched: the sentinel
    // was stored as a block's start time, sorting those starts raised, and the whole Day view went
    // down with it. The app looked as though Day simply did nothing.
    //
    // A block offered on Monday and Tuesday that the solver put on Monday. Tuesday has to leave it
    // out, and that decision is the one the sentinel makes.
    let blocks = [
        json!({"id": "essay", "title": "Essay", "kind": "flexible", "days": [0, 1], "duration_min": 60}),
        json!({"id": "tue", "title": "Tuesday only", "kind": "locked", "start": "09:00", "days": [1]}),
    ];
    let trace =
        json!({"placed": [{"id": "essay", "start": "16:00", "days": [0], "kind": "flexible"}]});
    let tuesday = agenda_for(
        "2026-09-14",
        "2026-09-15",
        &json!(blocks),
        &json!({}),
        Some(&trace),
        None,
    )
    .expect("an agenda");
    assert_eq!(ids(&tuesday["sessions"]), Vec::<&str>::new());
    assert!(
        tuesday["fixed"]
            .as_array()
            .expect("fixed")
            .iter()
            .all(|row| row["start"].is_string()),
        "{}",
        tuesday["fixed"]
    );
    let monday = agenda_for(
        "2026-09-14",
        "2026-09-14",
        &json!(blocks),
        &json!({}),
        Some(&trace),
        None,
    )
    .expect("an agenda");
    assert_eq!(ids(&monday["sessions"]), ["essay"]);
}

#[test]
fn test_the_day_stays_in_clock_order_when_something_has_no_time() {
    let blocks = [
        json!({"id": "late", "title": "Late", "kind": "locked", "start": "18:00", "days": [0]}),
        json!({"id": "early", "title": "Early", "kind": "locked", "start": "07:00", "days": [0]}),
    ];
    let agenda = agenda_for(
        "2026-09-14",
        "2026-09-14",
        &json!(blocks),
        &json!({}),
        None,
        None,
    )
    .expect("an agenda");
    assert_eq!(ids(&agenda["fixed"]), ["early", "late"]);
}
