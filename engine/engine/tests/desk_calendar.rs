//! Rust twin of `desktop/tests/test_calendar.py`: grid math for the native calendar.

mod common;

use common::desk::{fresh_ids, object};
use flexweek_engine::desk::calendar::{days_through, is_series_checked};
use flexweek_engine::desk::grid::{
    apply_block_edit, apply_block_times, create_click_range, due_day_of, due_soon_for, span_clash,
    span_problem, split_occurrence, sunday_due,
};
use flexweek_engine::desk::planning::due_point;
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// `span_problem` in the wrapper: a deadline is a `(day, minute)` tuple or None, and the engine is
/// told which by the name of its Python type.
fn problem(day: i64, start: i64, end: i64, due: Option<(i64, i64)>) -> Option<&'static str> {
    let (due, kind) = match due {
        Some((due_day, minute)) => (json!([due_day, minute]), "tuple"),
        None => (Value::Null, "NoneType"),
    };
    span_problem(day, start, end, &due, kind).expect("a verdict")
}

fn clash(blocks: &[Value], id: &str, day: i64, start: i64, end: i64) -> Option<String> {
    span_clash(&json!(blocks), &json!(id), &json!(day), start, end).expect("a verdict")
}

fn click(begin: i64, occupied: Value) -> Option<Value> {
    create_click_range(begin, &occupied).expect("a verdict")
}

fn retimed(block: &Value, start: i64, end: i64) -> Option<Value> {
    apply_block_times(block, start, end, None).expect("a verdict")
}

fn school(days: Value) -> Value {
    json!({
        "id": "school",
        "kind": "locked",
        "title": "School",
        "duration_min": 60,
        "days": days,
        "start": "10:00",
    })
}

#[test]
fn test_a_click_makes_up_to_an_hour_and_stops_at_the_next_block() {
    assert_eq!(click(900, json!([[930, 960]])), Some(json!([900, 930])));
    assert_eq!(click(900, json!([])), Some(json!([900, 960])));
    assert_eq!(
        click(1425, json!([[1430, 1440]])),
        Some(json!([1425, 1430]))
    );
    assert_eq!(click(1430, json!([[1430, 1440]])), None);
}

#[test]
fn test_a_repeating_locked_block_cannot_be_retimed_from_one_day() {
    let school = school(json!([0, 1, 2]));
    assert!(is_series_checked(&school).expect("a verdict"));
    assert_eq!(retimed(&school, 630, 705), None);
}

#[test]
fn test_a_one_day_block_can_still_be_moved_and_resized() {
    let school = school(json!([0]));
    let moved = retimed(&school, 630, 705).expect("moved");
    assert_eq!(moved["start"], "10:30");
    assert_eq!(moved["duration_min"], 75);
    assert_eq!(moved["days"], json!([0]));
}

#[test]
fn test_a_flexible_task_with_several_candidate_days_is_not_a_series() {
    let essay = json!({
        "id": "essay",
        "kind": "flexible",
        "title": "Essay",
        "duration_min": 60,
        "days": [1, 3],
        "start": "10:00",
    });
    assert!(!is_series_checked(&essay).expect("a verdict"));
    let moved = retimed(&essay, 630, 690).expect("moved");
    assert_eq!(moved["start"], "10:30");
    assert_eq!(moved["days"], json!([1, 3]));
}

#[test]
fn test_editing_one_occurrence_splits_a_new_one_day_block() {
    let school = school(json!([0, 1, 2]));
    let mut edited = school.clone();
    edited["start"] = json!("11:00");
    let result = apply_block_edit(
        &json!([school]),
        &edited,
        &json!("occurrence"),
        &json!(1),
        &mut fresh_ids(),
    )
    .expect("an edit");
    let mut starts: BTreeMap<Vec<i64>, String> = BTreeMap::new();
    for block in &result {
        let days = block["days"]
            .as_array()
            .expect("days")
            .iter()
            .map(|day| day.as_i64().expect("day"))
            .collect();
        starts.insert(days, block["start"].as_str().expect("start").to_string());
    }
    assert_eq!(starts[&vec![0, 2]], "10:00");
    assert_eq!(starts[&vec![1]], "11:00");
    let mut ids: Vec<&str> = result
        .iter()
        .map(|b| b["id"].as_str().expect("id"))
        .collect();
    ids.sort_unstable();
    ids.dedup();
    assert_eq!(ids.len(), 2);
}

#[test]
fn test_split_occurrence_leaves_a_single_day_block_alone() {
    let block = json!({
        "id": "once",
        "kind": "locked",
        "title": "Piano",
        "duration_min": 60,
        "days": [1],
        "start": "17:00",
    });
    let (result, new_id) =
        split_occurrence(&json!([block]), &json!("once"), &json!(1), &mut fresh_ids())
            .expect("a split");
    assert_eq!(new_id, None);
    assert_eq!(result[0]["days"], json!([1]));
}

#[test]
fn test_homework_dragged_on_a_day_is_due_at_the_end_of_that_week() {
    assert_eq!(
        sunday_due("2026-09-07").expect("a date"),
        "2026-09-13T23:59"
    );
}

#[test]
fn test_days_through_a_due_date_start_at_the_first_plannable_day() {
    assert_eq!(
        due_day_of(&json!("2026-09-11T08:10"), "2026-09-07").expect("a day"),
        Some(4)
    );
    assert_eq!(days_through(Some(4), 2), vec![2, 3, 4]);
    assert_eq!(days_through(Some(1), 3), vec![1]);
}

#[test]
fn test_a_time_on_another_block_is_allowed_and_named_but_not_outside_the_day_or_past_due() {
    // As in Daily Scheduler: two blocks may share a time. What cannot stand is time FlexWeek does not
    // plan in, and homework ending after it is due.
    let school = json!({
        "id": "school", "title": "School", "start": "08:00", "duration_min": 390, "days": [0, 1, 2],
    });
    let missed = json!({
        "id": "club", "title": "Club", "start": "16:00", "duration_min": 60, "days": [0, 1, 2],
        "missed_days": [1],
    });
    let done = json!({
        "id": "done", "title": "Done work", "start": "17:00", "duration_min": 390, "days": [1, 2],
        "completed": true, "completed_day": 2,
    });
    let blocks = [school, missed, done];
    let h = |hours: i64, minutes: i64| hours * 60 + minutes;

    assert_eq!(problem(1, h(10, 0), h(11, 0), None), None);
    assert_eq!(
        clash(&blocks, "essay", 1, h(10, 0), h(11, 0)).as_deref(),
        Some("School")
    );
    assert_eq!(
        clash(&blocks, "school", 1, h(10, 0), h(11, 0)),
        None,
        "never beside itself"
    );
    assert_eq!(
        clash(&blocks, "essay", 1, h(14, 30), h(15, 0)),
        None,
        "touching is not sharing"
    );
    assert_eq!(
        clash(&blocks, "essay", 1, h(16, 0), h(17, 0)),
        None,
        "not on a day it was missed"
    );
    assert_eq!(
        clash(&blocks, "essay", 1, h(17, 0), h(18, 0)),
        None,
        "finished work sits on the day it was done"
    );
    assert_eq!(
        clash(&blocks, "essay", 2, h(17, 0), h(18, 0)).as_deref(),
        Some("Done work")
    );
    assert_eq!(problem(1, h(3, 0), h(4, 0), None), None);
    assert_eq!(problem(1, h(22, 30), h(23, 30), None), None);
    assert_eq!(
        problem(1, h(23, 30), h(24, 30), None),
        Some("That is outside the hours FlexWeek plans in, so it stayed where it was.")
    );
    assert_eq!(
        problem(3, h(19, 0), h(20, 0), Some((3, h(19, 30)))),
        Some("That ends after it is due, so it stayed where it was.")
    );
    assert_eq!(problem(3, h(18, 0), h(19, 30), Some((3, h(19, 30)))), None);
}

#[test]
fn test_due_point_and_span_problem_cover_date_only_and_timed_dues() {
    let week = "2026-09-14";
    let date_only = due_point(&json!("2026-09-15"), week).expect("a point");
    let legacy = due_point(&json!("2026-09-15T23:59"), week).expect("a point");
    let timed = due_point(&json!("2026-09-15T09:00"), week).expect("a point");
    assert_eq!(date_only, Some((1, 24 * 60)));
    assert_eq!(legacy, Some((1, 24 * 60)));
    assert_eq!(timed, Some((1, 9 * 60)));
    assert_eq!(
        due_day_of(&json!("2026-09-15"), week).expect("a day"),
        Some(1)
    );
    let after_due = Some("That ends after it is due, so it stayed where it was.");
    assert_eq!(problem(1, 23 * 60, 23 * 60 + 45, date_only), None);
    assert_eq!(problem(1, 23 * 60, 23 * 60 + 45, legacy), None);
    assert_eq!(problem(1, 9 * 60, 9 * 60 + 15, timed), after_due);
    assert_eq!(problem(1, 8 * 60, 9 * 60, timed), None);
    let assignments = object(json!({
        "allday": {"id": "allday", "title": "All day", "due": "2026-09-15", "completed": false},
        "morning": {"id": "morning", "title": "Morning", "due": "2026-09-15T09:00", "completed": false},
    }));
    let ordered = due_soon_for("2026-09-15", &Value::Object(assignments)).expect("items");
    let ids: Vec<&str> = ordered
        .iter()
        .map(|item| item["id"].as_str().expect("id"))
        .collect();
    assert_eq!(ids, ["morning", "allday"]);
}
