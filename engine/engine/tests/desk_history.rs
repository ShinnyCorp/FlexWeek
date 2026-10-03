//! Rust twin of `desktop/tests/test_history.py`: undo snapshots for the native week.

use flexweek_engine::EngineError;
use flexweek_engine::desk::history::{self, HISTORY_LIMIT, capture_step};
use serde_json::{Value, json};
use std::cell::RefCell;

fn ids(names: &[&str]) -> Vec<String> {
    names.iter().map(|name| (*name).to_string()).collect()
}

fn push_step(stack: &mut Vec<Value>, step: Value) {
    let stack = RefCell::new(stack);
    history::push_step(
        step,
        |step| {
            stack.borrow_mut().push(step);
            Ok::<_, EngineError>(())
        },
        || Ok(stack.borrow().len()),
        || {
            stack.borrow_mut().remove(0);
            Ok(())
        },
    )
    .expect("a push");
}

fn mark_stale(steps: &mut [Value], week_start: &str) {
    let items = steps
        .iter_mut()
        .map(|step| Ok::<_, EngineError>((step.clone(), json!(week_start), step)));
    history::mark_stale(
        items,
        |step| {
            step["stale"] = json!(true);
            Ok(())
        },
        |error| error,
    )
    .expect("a verdict");
}

#[test]
fn test_capture_step_records_only_what_changed() {
    let before = json!([{"id": "soccer", "title": "Soccer"}]);
    let after = json!([
        {"id": "soccer", "title": "Soccer"},
        {"id": "piano", "title": "Piano"},
    ]);
    let step = capture_step(
        "editing Piano",
        "2026-09-07",
        &before,
        &after,
        &json!({}),
        &json!({}),
        &ids(&[]),
    )
    .expect("a verdict")
    .expect("a step");
    assert_eq!(step["label"], "editing Piano");
    assert_eq!(step["weeks"][0]["before"], before);
    assert_eq!(step["weeks"][0]["after"], after);
    assert_eq!(step["assignments"], json!([]));
}

#[test]
fn test_capture_step_skips_an_unchanged_week() {
    let blocks = json!([{"id": "soccer", "title": "Soccer"}]);
    assert_eq!(
        capture_step(
            "editing",
            "2026-09-07",
            &blocks,
            &blocks,
            &json!({}),
            &json!({}),
            &ids(&[]),
        )
        .expect("a verdict"),
        None
    );
}

#[test]
fn test_capture_step_records_a_new_assignment() {
    let homework = json!({"id": "lab", "title": "Lab", "due": "2026-09-11T08:10"});
    let step = capture_step(
        "editing Lab",
        "2026-09-07",
        &json!([]),
        &json!([]),
        &json!({}),
        &json!({"lab": homework}),
        &ids(&["lab"]),
    )
    .expect("a verdict")
    .expect("a step");
    assert_eq!(
        step["assignments"],
        json!([{"id": "lab", "before": null, "after": homework}])
    );
}

#[test]
fn test_push_step_drops_the_oldest_past_the_limit() {
    let mut stack: Vec<Value> = Vec::new();
    for index in 0..HISTORY_LIMIT + 2 {
        push_step(
            &mut stack,
            json!({"label": index.to_string(), "weeks": [], "assignments": [], "stale": false}),
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
        json!({"weeks": [{"week_start": "2026-09-07"}], "stale": false}),
        json!({"weeks": [{"week_start": "2026-09-14"}], "stale": false}),
    ];
    mark_stale(&mut steps, "2026-09-07");
    assert_eq!(steps[0]["stale"], json!(true));
    assert_eq!(steps[1]["stale"], json!(false));
}
