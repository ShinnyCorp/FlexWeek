//! Rust twin of `desktop/tests/test_history.py`: undo snapshots for the native week.

mod common;

use common::desk::object;
use flexweek_engine::desk::history::{HISTORY_LIMIT, capture_step, mark_stale, push_step};
use serde_json::{Map, Value, json};
use std::collections::HashSet;

fn ids(names: &[&str]) -> HashSet<String> {
    names.iter().map(|name| (*name).to_string()).collect()
}

#[test]
fn test_capture_step_records_only_what_changed() {
    let before = [json!({"id": "soccer", "title": "Soccer"})];
    let after = [
        json!({"id": "soccer", "title": "Soccer"}),
        json!({"id": "piano", "title": "Piano"}),
    ];
    let step = capture_step(
        "editing Piano",
        "2026-09-07",
        &before,
        &after,
        &Map::new(),
        &Map::new(),
        &ids(&[]),
    )
    .expect("a step");
    assert_eq!(step["label"], "editing Piano");
    assert_eq!(step["weeks"][0]["before"], json!(before));
    assert_eq!(step["weeks"][0]["after"], json!(after));
    assert_eq!(step["assignments"], json!([]));
}

#[test]
fn test_capture_step_skips_an_unchanged_week() {
    let blocks = [json!({"id": "soccer", "title": "Soccer"})];
    assert_eq!(
        capture_step(
            "editing",
            "2026-09-07",
            &blocks,
            &blocks,
            &Map::new(),
            &Map::new(),
            &ids(&[]),
        ),
        None
    );
}

#[test]
fn test_capture_step_records_a_new_assignment() {
    let homework = json!({"id": "lab", "title": "Lab", "due": "2026-09-11T08:10"});
    let step = capture_step(
        "editing Lab",
        "2026-09-07",
        &[],
        &[],
        &Map::new(),
        &object(json!({"lab": homework})),
        &ids(&["lab"]),
    )
    .expect("a step");
    assert_eq!(
        step["assignments"],
        json!([{"id": "lab", "before": null, "after": homework}])
    );
}

#[test]
fn test_push_step_drops_the_oldest_past_the_limit() {
    let mut stack: Vec<Map<String, Value>> = Vec::new();
    for index in 0..HISTORY_LIMIT + 2 {
        push_step(
            &mut stack,
            object(
                json!({"label": index.to_string(), "weeks": [], "assignments": [], "stale": false}),
            ),
        );
    }
    assert_eq!(stack.len(), HISTORY_LIMIT);
    assert_eq!(stack[0]["label"], "2");
    assert_eq!(
        stack[stack.len() - 1]["label"],
        (HISTORY_LIMIT + 1).to_string()
    );
}

#[test]
fn test_mark_stale_only_touches_steps_for_that_week() {
    let mut steps = vec![
        object(json!({"weeks": [{"week_start": "2026-09-07"}], "stale": false})),
        object(json!({"weeks": [{"week_start": "2026-09-14"}], "stale": false})),
    ];
    mark_stale(&mut steps, "2026-09-07");
    assert_eq!(steps[0]["stale"], json!(true));
    assert_eq!(steps[1]["stale"], json!(false));
}
